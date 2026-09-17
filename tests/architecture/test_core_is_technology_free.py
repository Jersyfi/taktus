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
    }
    present = {p.name for p in (SRC / "components").iterdir() if (p / "__init__.py").is_file()}
    assert present == documented
