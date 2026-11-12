"""Every connector listens on a default port of its own, so that two started side by side from
their READMEs do not collide. An image takes its port from the chart or the compose file, which
pass `--port`; the default is what a person running one from the checkout gets."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "connectors" / "taktus_connectors"
DEFAULT = re.compile(
    r"serving\.arguments\([^)]*?,\s*(\d+)\s*\)|\"--port\",\s*type=int,\s*default=(\d+)", re.S
)


def defaults() -> dict[str, int]:
    found: dict[str, int] = {}
    for main in sorted(ROOT.glob("*/__main__.py")):
        match = DEFAULT.search(main.read_text(encoding="utf-8"))
        assert match, f"{main.parent.name}: no default port found"
        found[main.parent.name] = int(match.group(1) or match.group(2))
    return found


def test_every_connector_has_a_default_port_of_its_own() -> None:
    by_port: dict[int, list[str]] = defaultdict(list)
    for name, port in defaults().items():
        by_port[port].append(name)
    shared = {port: names for port, names in by_port.items() if len(names) > 1}
    assert shared == {}, f"connectors that share a default port: {shared}"


def test_each_readme_names_the_connector_s_own_default_port() -> None:
    for name, port in defaults().items():
        readme = ROOT / name / "README.md"
        text = readme.read_text(encoding="utf-8")
        named = {
            int(p) for p in re.findall(rf"taktus_connectors\.{name}\b[^\n]*--port (\d+)", text)
        }
        assert named <= {port}, f"{name}: README starts it on {named}, its default is {port}"
