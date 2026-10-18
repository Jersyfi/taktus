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
            ["static", "decisions", "test", "rehearse"],
        ),
        (
            ["src/taktus/adapters/driven/connectors/mcp/actions.py"],
            ["static", "decisions", "conformance", "test", "rehearse"],
        ),
        (
            ["blueprints/dev-orchestration/processes/P-03-implementation.yaml"],
            ["static", "decisions", "test", "rehearse"],
        ),
        (
            ["tests/rehearsal/recordings/p02-refinement/recording.json"],
            ["static", "decisions", "test", "rehearse"],
        ),
        (["tools/record_rehearsal.py"], ["static", "decisions", "test", "rehearse"]),
        (["tests/components/run/test_engine.py"], ["static", "decisions", "test"]),
        (["workers/claudecode/worker.py"], ["static", "decisions", "conformance", "test"]),
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
