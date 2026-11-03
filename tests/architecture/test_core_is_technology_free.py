"""The adapter obligation and the component boundaries, as tests (ADR-0003, ADR-0016).

`import-linter` (.importlinter, run by `make gate-arch`) holds the import graph: no component
imports another, the core imports no driver, adapters import no component. What it cannot see
is here: a product name anywhere in the core or in the contracts, a direct call to the clock or
to randomness, an import outside the allowed set, a domain model that is not frozen and closed,
a worker that reaches into the control plane.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
import re
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "taktus"
CONTRACTS = ROOT / "contracts"
CORE = ("components", "ports", "shared", "wire")
# The one product name the contracts may carry: where to clone this repository from.
REPOSITORY_URL = "github.com/Jersyfi/taktus"

# The sharpest test in the project (ADR-0003): a product name in the core is a finding, even in
# a comment. Names are matched as whole words, case-insensitively.
PRODUCT_NAMES = (
    "anthropic",
    "claude",
    "openai",
    "chatgpt",
    "gemini",
    "copilot",
    "codex",
    "ollama",
    "mistral",
    "huggingface",
    "slack",
    "discord",
    "github",
    "gitlab",
    "bitbucket",
    "jira",
    "confluence",
    "bookstack",
    "notion",
    "postgres",
    "postgresql",
    "redis",
    "kafka",
    "rabbitmq",
    "sqlalchemy",
    "alembic",
    "fastapi",
    "httpx",
    "uvicorn",
    "psycopg",
    "grafana",
    "datadog",
    "sentry",
    "prometheus",
    "aws",
    "amazon",
    "stripe",
    "litellm",
)
PRODUCT = re.compile(r"\b(" + "|".join(PRODUCT_NAMES) + r")\b", re.IGNORECASE)

# What the core may import: the standard library, pydantic (the domain types), and itself.
ALLOWED_TOP_LEVEL = frozenset({"pydantic", "taktus", "typing_extensions"})

# Time, identifiers and randomness come from ports (docs/architecture/project-structure.md §4).
FORBIDDEN_MODULES = frozenset({"random", "secrets", "uuid", "time"})
FORBIDDEN_CALLS = frozenset(
    {
        "datetime.now",
        "datetime.utcnow",
        "datetime.today",
        "date.today",
        "time.time",
        "time.monotonic",
        "time.perf_counter",
        "time.sleep",
        "asyncio.sleep",
        "uuid.uuid4",
        "uuid.uuid1",
        "uuid.uuid7",
        "random.random",
        "secrets.token_hex",
        "secrets.token_bytes",
        "secrets.token_urlsafe",
    }
)


def core_files() -> list[Path]:
    return sorted(path for area in CORE for path in (SRC / area).rglob("*.py"))


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def imported_modules(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return names


@pytest.mark.parametrize("path", core_files(), ids=rel)
def test_no_product_name_in_the_core(path: Path) -> None:
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = PRODUCT.search(line)
        assert match is None, f"{rel(path)}:{number}: product name {match.group(0)!r}"


def contract_files() -> list[Path]:
    return sorted(p for p in CONTRACTS.rglob("*") if p.suffix in {".json", ".yaml", ".md"})


@pytest.mark.parametrize("path", contract_files(), ids=rel)
def test_no_product_name_in_the_contracts(path: Path) -> None:
    """A contract names capabilities, never products (ADR-0003): a schema, an example or a
    README that mentions one has smuggled a product back in. The only exception is the address
    of this repository in the instructions for cloning it."""
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = PRODUCT.search(line.replace(REPOSITORY_URL, ""))
        assert match is None, f"{rel(path)}:{number}: product name {match.group(0)!r}"


@pytest.mark.parametrize("path", core_files(), ids=rel)
def test_the_core_imports_only_the_standard_library_pydantic_and_itself(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    foreign = [
        name
        for name in imported_modules(tree)
        if name.split(".")[0] not in sys.stdlib_module_names
        and name.split(".")[0] not in ALLOWED_TOP_LEVEL
    ]
    assert foreign == [], f"{rel(path)} imports {foreign}"


@pytest.mark.parametrize("path", core_files(), ids=rel)
def test_time_identifiers_and_randomness_come_from_ports(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    findings = [
        f"{rel(path)}:{node.lineno}: imports {name}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for name in (
            [alias.name for alias in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""]
        )
        if name.split(".")[0] in FORBIDDEN_MODULES
    ]
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            dotted = _dotted(node.func)
            if dotted in FORBIDDEN_CALLS:
                findings.append(f"{rel(path)}:{node.lineno}: calls {dotted}()")
    assert findings == []


def _dotted(node: ast.expr) -> str:
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value)
        return f"{head}.{node.attr}" if head else node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def domain_modules() -> list[str]:
    names = []
    for area in ("shared", "components"):
        package = importlib.import_module(f"taktus.{area}")
        for info in pkgutil.walk_packages(package.__path__, f"taktus.{area}."):
            if area == "shared" or ".domain.model" in info.name:
                names.append(info.name)
    return sorted(names)


@pytest.mark.parametrize("module_name", domain_modules())
def test_domain_models_are_frozen_and_closed(module_name: str) -> None:
    module = importlib.import_module(module_name)
    for name, model in inspect.getmembers(module, inspect.isclass):
        if not issubclass(model, BaseModel) or model.__module__ != module_name:
            continue
        config = model.model_config
        assert config.get("frozen") is True, f"{module_name}.{name} is not frozen"
        assert config.get("extra") == "forbid", f"{module_name}.{name} accepts unknown fields"


@pytest.mark.parametrize("path", sorted((ROOT / "workers").rglob("*.py")), ids=lambda p: rel(p))
def test_workers_import_nothing_from_the_control_plane(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert [n for n in imported_modules(tree) if n.split(".")[0] == "taktus"] == []


def test_every_component_of_the_structure_exists_as_a_package() -> None:
    documented = {
        "identity",
        "command",
        "process",
        "run",
        "governance",
        "decision",
        "catalog",
        "accounting",
        "knowledge",
        "value",
        "ledger",
        "reporting",
    }
    present = {p.name for p in (SRC / "components").iterdir() if (p / "__init__.py").is_file()}
    assert present == documented


CONTROL_PLANE_IMAGE = ROOT / "deploy" / "docker" / "Dockerfile"


def test_the_control_plane_image_carries_no_worker_code() -> None:
    """A worker executes foreign code and is a separate deployable with its own image
    (DEC-0011). The control plane image copies nothing from workers/ and never the whole
    checkout, so that a compromised control plane finds no execution primitive ready to hand;
    deploy/docker/verify.sh checks the built image the same way."""
    lines = CONTROL_PLANE_IMAGE.read_text(encoding="utf-8").splitlines()
    copies = [
        (number, line.split())
        for number, line in enumerate(lines, 1)
        if line.strip().upper().startswith(("COPY", "ADD"))
    ]
    assert copies, "the Dockerfile copies nothing at all"
    for number, words in copies:
        sources = [w for w in words[1:-1] if not w.startswith("--")]
        for source in sources:
            assert "workers" not in source, f"deploy/docker/Dockerfile:{number}: {' '.join(words)}"
            assert source not in (".", "./"), (
                f"deploy/docker/Dockerfile:{number}: copies the whole checkout, workers included"
            )


# --- connectors: separate deployables with images of their own (ADR-0158, issue #339) --------

CONNECTORS = ROOT / "connectors"
CONNECTOR_PACKAGE = "taktus_connectors"
CONNECTOR_DOCKERFILE = CONNECTORS / "Dockerfile"
PORT_SIDE = SRC / "adapters" / "driven" / "connectors"
IN_PROCESS = frozenset({"directory", "loopback"})
"""The two connectors that run inside the control plane, because what they reach is the
instance itself and the files on its own volume; with them only the MCP client of the port."""


def shipped_connectors() -> list[str]:
    return sorted(p.parent.name for p in (CONNECTORS / CONNECTOR_PACKAGE).glob("*/__main__.py"))


@pytest.mark.parametrize("path", sorted(CONNECTORS.rglob("*.py")), ids=lambda p: rel(p))
def test_connectors_import_nothing_from_the_control_plane(path: Path) -> None:
    """A connector is a separate deployable, as a worker is (DEC-0011): its image carries no
    control plane, so nothing of it can import one."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert [n for n in imported_modules(tree) if n.split(".")[0] == "taktus"] == []


@pytest.mark.parametrize("path", sorted(SRC.rglob("*.py")), ids=rel)
def test_the_control_plane_imports_no_shipped_connector(path: Path) -> None:
    """The control plane reaches a connector over MCP only; adding one changes no control plane
    code. `composition/shipped.py` names the package as text to list it when the repository is
    there (`make generate`), never as an import."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = [n for n in imported_modules(tree) if n.split(".")[0] == CONNECTOR_PACKAGE]
    assert found == [], f"{rel(path)} imports {found}"


def test_only_the_ports_side_of_the_connectors_stays_in_the_control_plane() -> None:
    """Under the control plane's connectors: the MCP client, the pool, and the two connectors
    that run in its process. Every other connector lives under connectors/ (ADR-0158)."""
    present = {p.name for p in PORT_SIDE.iterdir() if p.name != "__pycache__"}
    assert present == {"__init__.py", "pool.py", "mcp", *IN_PROCESS}, present


def test_the_control_plane_image_carries_no_connector_code() -> None:
    """The control plane image copies nothing from connectors/; a connector's image copies
    only connectors/, the lock file it installs from and its project file (ADR-0158)."""
    lines = CONTROL_PLANE_IMAGE.read_text(encoding="utf-8").splitlines()
    for number, line in enumerate(lines, 1):
        if not line.strip().upper().startswith(("COPY", "ADD")):
            continue
        words = line.split()
        for source in (w for w in words[1:-1] if not w.startswith("--")):
            assert source.split("/")[0] != "connectors", f"deploy/docker/Dockerfile:{number}"


def _stages() -> dict[str, list[str]]:
    stages: dict[str, list[str]] = {}
    current = ""
    for line in CONNECTOR_DOCKERFILE.read_text(encoding="utf-8").splitlines():
        words = line.split()
        if not words or words[0].startswith("#"):
            continue
        if words[0].upper() == "FROM":
            current = words[-1]
            stages[current] = []
        elif current:
            stages[current].append(line.strip())
    return stages


def test_every_connector_is_an_image_of_its_own_that_carries_only_itself() -> None:
    """One stage per connector, built on the shared base: it copies its own directory and no
    other connector's, and runs its own module. The base copies the serving library and no
    connector, and nothing copies src/."""
    stages = _stages()
    assert set(stages) - {"build", "base"} == set(shipped_connectors())
    for name in shipped_connectors():
        copies = [line for line in stages[name] if line.upper().startswith("COPY")]
        assert copies == [
            f"COPY --chown=connector:connector connectors/{CONNECTOR_PACKAGE}/{name} "
            f"/app/{CONNECTOR_PACKAGE}/{name}"
        ], name
        assert f'ENTRYPOINT ["python", "-m", "{CONNECTOR_PACKAGE}.{name}"]' in stages[name]
    for stage in ("build", "base"):
        for line in stages[stage]:
            if line.upper().startswith("COPY") and "--from=" not in line:
                sources = line.split()[1:-1]
                assert all(s.split("/")[0] != "src" for s in sources), line
                assert all(
                    s.removeprefix(f"connectors/{CONNECTOR_PACKAGE}/")
                    in ("__init__.py", "serving.py")
                    for s in sources
                    if s.startswith("connectors/")
                ), line


CLUSTER_ADAPTER = SRC / "adapters" / "driven" / "execution" / "kubernetes"
CLUSTER_CLIENT = "taktus.adapters.driven.execution.kubernetes.api"
CLUSTER_LIBRARIES = frozenset({"kubernetes", "kubernetes_asyncio", "lightkube", "kr8s", "pykube"})


@pytest.mark.parametrize("path", sorted(SRC.rglob("*.py")), ids=rel)
def test_no_cluster_client_outside_the_cluster_adapter(path: Path) -> None:
    """The cluster's API is reached by the cluster execution adapter alone: its own client
    (`kubernetes/api.py`, over httpx) is imported nowhere else, and no cluster client library
    anywhere. The composition root wires the adapter, never the client; tests may."""
    if CLUSTER_ADAPTER in path.parents:
        return
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = [
        name
        for name in imported_modules(tree)
        if name == CLUSTER_CLIENT or name.split(".")[0] in CLUSTER_LIBRARIES
    ]
    assert found == [], f"{rel(path)} imports {found}"
