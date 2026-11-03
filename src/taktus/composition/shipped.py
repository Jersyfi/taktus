"""The list of what a release ships: its workers and connectors, with the capabilities and
operations each offers (ADR-0118).

The list is data the release carries, `shipped.json` beside this module, inside the package.
The instance reads it with `load`, and the rule that tells a product's lack from a project's
classifies every lack against it (`reporting/domain/service/findings.py`).

`build` makes the list from the repository: every connector's own declaration — the connectors
under `connectors/`, each shipped as an image of its own, and the two that run inside the
control plane under `adapters/driven/connectors` (ADR-0158) — and every worker's `CAPABILITIES`
under `workers/`, read from its source without importing it. A connector of its own image is
listed with that image's name; one that runs inside the control plane with none.
`make generate` writes it, and `tests/composition/test_shipped.py` fails when the file is not
what `build` makes, so the list cannot drift from what ships.

Two adapters are left out. The vendor connector serves whatever a vendor's server offers under
a manifest its operator writes, so it ships no capability of its own (ADR-0117). The MCP client
is the connector port's adapter, not a connector.

`build` runs where the repository is — `make generate` and its test. The control plane image
carries no connector, so the connectors' package is named here as text and imported only then;
nothing the instance runs imports it (`tests/architecture`).
"""

from __future__ import annotations

import ast
import importlib
import json
import pkgutil
from pathlib import Path
from typing import Any

from taktus.components.reporting.domain.model import Shipped, ShippedAdapter

LIST = Path(__file__).with_name("shipped.json")
CONNECTORS = "taktus_connectors"
"""The connectors of images of their own (ADR-0158), as text: see the module's last paragraph."""
IN_PROCESS = "taktus.adapters.driven.connectors"
"""The connectors that run inside the control plane: the instance itself and its own files."""
LEFT_OUT = frozenset({"mcp", "vendor"})
"""Packages under the connectors that are no connector the release ships with capabilities."""
IMAGE = "taktus-connector-{name}"
"""The name of a connector's image, as `.github/workflows/images.yml` pushes it and the chart
and `deploy/docker/connectors.py` pull it: the connector's directory under `connectors/`."""


def load(path: Path = LIST) -> Shipped:
    """The list the release carries."""
    return Shipped.model_validate_json(path.read_text(encoding="utf-8"))


def _declared(package: str, name: str) -> dict[str, Any] | None:
    try:
        module = importlib.import_module(f"{package}.{name}.declaration")
        declared: dict[str, Any] = module.capabilities()
        return declared
    except ModuleNotFoundError:
        found = importlib.import_module(f"{package}.{name}")
        declaration = getattr(found, "DECLARATION", None)
        return None if declaration is None else declaration.model_dump(mode="json")


def connectors() -> tuple[ShippedAdapter, ...]:
    found: list[ShippedAdapter] = []
    for package, imaged in ((CONNECTORS, True), (IN_PROCESS, False)):
        members = importlib.import_module(package)
        for info in pkgutil.iter_modules(members.__path__):
            if not info.ispkg or info.name in LEFT_OUT:
                continue
            declared = _declared(package, info.name)
            if declared is None:
                continue
            found.append(
                ShippedAdapter(
                    name=info.name,
                    capabilities=tuple(sorted(declared["capabilities"])),
                    operations=tuple(sorted(o["name"] for o in declared["operations"])),
                    image=IMAGE.format(name=info.name) if imaged else None,
                )
            )
    return tuple(sorted(found, key=lambda adapter: adapter.name))


def _constants(tree: ast.Module) -> dict[str, Any]:
    """Every module-level name bound to a string, or to a list of strings and such names."""
    known: dict[str, Any] = {}

    def value(node: ast.expr) -> Any:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name) and node.id in known:
            return known[node.id]
        if isinstance(node, ast.List | ast.Tuple):
            items = [value(element) for element in node.elts]
            return None if any(i is None for i in items) else items
        return None

    for statement in tree.body:
        if not isinstance(statement, ast.Assign | ast.AnnAssign):
            continue
        targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
        if statement.value is None:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                found = value(statement.value)
                if found is not None:
                    known[target.id] = found
            elif isinstance(target, ast.Tuple) and isinstance(statement.value, ast.Tuple):
                for name, each in zip(target.elts, statement.value.elts, strict=False):
                    found = value(each)
                    if isinstance(name, ast.Name) and found is not None:
                        known[name.id] = found
    return known


def workers(root: Path) -> tuple[ShippedAdapter, ...]:
    found: list[ShippedAdapter] = []
    for source in sorted((root / "workers").glob("*/worker.py")):
        capabilities = _constants(ast.parse(source.read_text(encoding="utf-8"))).get("CAPABILITIES")
        if not isinstance(capabilities, list):
            raise ValueError(f"{source} states no CAPABILITIES as a list of strings")
        found.append(
            ShippedAdapter(name=source.parent.name, capabilities=tuple(sorted(capabilities)))
        )
    return tuple(found)


def build(root: Path) -> Shipped:
    """The list, from the repository at `root`."""
    return Shipped(workers=workers(root), connectors=connectors())


def text(shipped: Shipped) -> str:
    """The list as the file holds it."""
    return json.dumps(shipped.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
