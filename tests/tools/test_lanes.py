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
        (["src/taktus/components/run/domain/service/budget.py"], ["static", "decisions", "test"]),
        (
            ["src/taktus/adapters/driven/connectors/mcp/actions.py"],
            ["static", "decisions", "conformance", "test"],
        ),
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
