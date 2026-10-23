"""Which lanes a change selects (ADR-0096 §3, #390): the code CI and `make verify` share."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import lanes  # noqa: E402 — a script under tools/, found through the line above


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        (["docs/adr/ADR-0001-language.md"], ["static", "decisions"]),
        (["CLAUDE.md", "docs/status.md"], ["static", "decisions"]),
        (["web/src/routes/+page.svelte"], ["static", "decisions", "web"]),
        (["api/openapi.yaml"], ["static", "decisions", "contracts"]),
        (
            ["src/taktus/components/run/domain/service/budget.py"],
            ["static", "decisions", "test", "rehearse", "timing"],
        ),
        (
            ["src/taktus/adapters/driven/connectors/mcp/actions.py"],
            ["static", "decisions", "conformance", "test", "rehearse", "timing"],
        ),
        (
            ["blueprints/dev-orchestration/processes/P-03-implementation.yaml"],
            ["static", "decisions", "test", "rehearse", "timing"],
        ),
        (
            ["tests/rehearsal/recordings/p02-refinement/recording.json"],
            ["static", "decisions", "test", "rehearse", "timing"],
        ),
        (["tools/record_rehearsal.py"], ["static", "decisions", "test", "rehearse"]),
        (["tools/check_status.py"], ["static", "decisions", "test", "selftest"]),
        (
            ["tests/architecture/test_core_is_technology_free.py"],
            ["static", "decisions", "test", "selftest", "timing"],
        ),
        (["tests/components/run/test_engine.py"], ["static", "decisions", "test", "timing"]),
        (
            ["workers/claudecode/worker.py"],
            ["static", "decisions", "conformance", "test", "timing"],
        ),
        (["tests/conformance/test_worker_v1_coding.py"], ["static", "decisions", "conformance"]),
        (["uv.lock"], list(lanes.LANES)),
        ([".github/workflows/ci.yml"], list(lanes.LANES)),
        (["contracts/worker/v1/Worker.json"], list(lanes.LANES)),
        (["src/taktus/shared/v1/step.py"], list(lanes.LANES)),
    ],
)
def test_a_change_selects_the_lanes_of_its_paths(paths: list[str], expected: list[str]) -> None:
    assert lanes.select(paths) == expected


def test_documentation_is_read_by_the_always_on_checks_alone() -> None:
    assert lanes.holes(["docs/runs/first-run.md", "README.md", "LICENSE"]) == []


def test_a_path_no_lane_claims_is_a_hole() -> None:
    assert lanes.holes(["scripts/deploy.sh"]) == ["scripts/deploy.sh"]


def test_every_lane_runs_something() -> None:
    assert set(lanes.COMMANDS) == set(lanes.LANES)
    assert all(lanes.COMMANDS[lane] for lane in lanes.LANES)


def test_every_module_the_replay_imports_selects_the_replay() -> None:
    """The lane `rehearse` (ADR-0108) is selected by every module the replay reaches through
    the composition root, as the import graph says, so that a change to the engine or to a
    component it runs cannot merge without being replayed. The graph is read in a process of
    its own, where nothing but the replay was imported."""
    import json
    import subprocess

    root = Path(__file__).resolve().parents[2]
    script = (
        "import importlib, json, sys; importlib.import_module('taktus.composition.replay'); "
        "print(json.dumps(sorted(m.__file__ for n, m in list(sys.modules.items()) "
        "if n.startswith('taktus') and getattr(m, '__file__', None))))"
    )
    found = subprocess.run(  # noqa: S603 — this interpreter, a fixed script
        [sys.executable, "-c", script], capture_output=True, text=True, check=True, cwd=root
    ).stdout
    files = [str(Path(f).resolve().relative_to(root)) for f in json.loads(found)]
    assert files
    assert [f for f in files if "rehearse" not in lanes.select([f])] == []


# --- Selection of tests inside the lane `test` (#394) ---


def _graph(edges: dict[str, set[str]]) -> dict[str, set[str]]:
    nodes = set(edges) | {t for targets in edges.values() for t in targets}
    return {node: set(edges.get(node, ())) for node in nodes}


def test_a_change_selects_the_tests_of_every_module_that_depends_on_it() -> None:
    graph = _graph(
        {
            "tests/components/a/test_a.py": {"src/taktus/components/a/service.py"},
            "tests/components/b/test_b.py": {"src/taktus/components/b/service.py"},
            "tests/composition/test_wiring.py": {"src/taktus/composition/wiring.py"},
            "src/taktus/composition/wiring.py": {"src/taktus/components/a/service.py"},
            "src/taktus/components/a/service.py": {"src/taktus/ports/store.py"},
            "src/taktus/components/b/service.py": {"src/taktus/shared/v1/step.py"},
        }
    )
    assert lanes.select_tests(["src/taktus/ports/store.py"], graph) == [
        "tests/components/a/test_a.py",
        "tests/composition/test_wiring.py",
    ]
    assert lanes.select_tests(["src/taktus/components/b/service.py"], graph) == [
        "tests/components/b/test_b.py"
    ]


def test_a_changed_test_selects_itself_and_a_change_nothing_tests_selects_nothing() -> None:
    graph = _graph({"tests/x/test_x.py": set(), "src/taktus/components/c/__init__.py": set()})
    assert lanes.select_tests(["tests/x/test_x.py"], graph) == ["tests/x/test_x.py"]
    assert lanes.select_tests(["src/taktus/components/c/__init__.py"], graph) == []


@pytest.mark.parametrize(
    "path",
    [
        "pyproject.toml",
        "uv.lock",
        "contracts/worker/v1/Worker.json",
        "src/taktus/shared/v1/step.py",
        # reached by a string, not by an import: selected by path
        "tests/rehearsal/recordings/p02-refinement/recording.json",
        "blueprints/dev-orchestration/processes/P-03-implementation.yaml",
        "tools/record_rehearsal.py",
        "src/taktus/composition/removed_module.py",
    ],
)
def test_what_the_graph_cannot_see_selects_every_test(path: str) -> None:
    assert lanes.select_tests([path], _graph({"tests/x/test_x.py": set()})) == [lanes.ALL_TESTS]


def test_documentation_selects_no_test() -> None:
    assert lanes.select_tests(["docs/status.md"], _graph({"tests/x/test_x.py": set()})) == []


def test_a_module_named_by_a_string_is_an_edge() -> None:
    graph = lanes.import_graph()
    launched = {
        node: targets
        for node, targets in graph.items()
        if node.startswith("tests/integration/test_launched_process")
    }
    assert launched
    assert any(
        target.startswith("src/taktus/") for targets in launched.values() for target in targets
    )


def test_a_change_to_a_component_selects_the_tests_of_each_component_that_depends_on_it() -> None:
    """On the real graph: every component's tests import the component, so a change to it
    selects them, and the tests of everything above it — the adapters, the composition root —
    that reach it through imports."""
    graph = lanes.import_graph()
    root = Path(__file__).resolve().parents[2]
    for component in sorted((root / "tests" / "components").iterdir()):
        package = f"src/taktus/components/{component.name}/__init__.py"
        if not component.is_dir() or package not in graph:
            continue
        own = {
            str(f.relative_to(root))
            for f in component.rglob("test_*.py")
            if any(
                t.startswith(f"src/taktus/components/{component.name}/")
                for t in graph[str(f.relative_to(root))]
            )
        }
        selected = set(lanes.select_tests([package], graph))
        assert own <= selected, component.name
        dependents = {
            n
            for n, targets in graph.items()
            if package in targets and n.startswith("tests/") and Path(n).name.startswith("test_")
        }
        assert dependents <= selected, component.name


def test_check_verify_and_ci_read_one_implementation() -> None:
    makefile = (Path(__file__).resolve().parents[2] / "Makefile").read_text(encoding="utf-8")
    assert makefile.count("tools/lanes.py") >= 2
    assert "--tests" in makefile
