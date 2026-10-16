"""The guard and the automaton that keep `main` green (ADR-0096 §5, #391), against what a
stubbed host answers: the files the workflows fetch with their token and hand to the tool."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import ci_watch  # noqa: E402 — a script under tools/, found through the line above


def runs(*listed: dict[str, Any]) -> dict[str, Any]:
    return {"total_count": len(listed), "workflow_runs": list(listed)}


def run(conclusion: str | None, at: str, *, status: str = "completed") -> dict[str, Any]:
    return {
        "id": 1,
        "status": status,
        "conclusion": conclusion,
        "created_at": at,
        "head_sha": "a1b2c3d4e5f6a7b8",
        "html_url": "https://host/run/1",
    }


def guarded(tmp_path: Path, answer: object, title: str = "fix: x", body: str = "") -> int:
    path = tmp_path / "runs.json"
    if answer is not None:
        path.write_text(answer if isinstance(answer, str) else json.dumps(answer), "utf-8")
    (tmp_path / "body.md").write_text(body, encoding="utf-8")
    return ci_watch.main(
        ["guard", "--runs", str(path), "--title", title, "--body-file", str(tmp_path / "body.md")]
    )


def test_a_green_main_lets_a_pull_request_merge(tmp_path: Path) -> None:
    assert guarded(tmp_path, runs(run("success", "2026-10-16T10:00:00Z"))) == 0


def test_a_red_main_holds_a_pull_request(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    newest_red = runs(
        run("success", "2026-10-16T09:00:00Z"), run("failure", "2026-10-16T10:00:00Z")
    )
    assert guarded(tmp_path, newest_red) == 1
    assert "main is red at a1b2c3d4e5f6" in capsys.readouterr().out


def test_the_newest_completed_run_decides_and_one_in_progress_does_not(tmp_path: Path) -> None:
    answer = runs(
        run(None, "2026-10-16T11:00:00Z", status="in_progress"),
        run("success", "2026-10-16T10:00:00Z"),
        run("failure", "2026-10-16T09:00:00Z"),
    )
    assert guarded(tmp_path, answer) == 0


@pytest.mark.parametrize(
    ("title", "body"),
    [
        ('Revert "feat: something that broke main"', ""),
        ("revert: the change that broke main", ""),
        ("fix(tests): main's failure is mended", "## What this is about\n\nMends main: a1b2c3d\n"),
    ],
    ids=["revert", "revert-conventional", "mends"],
)
def test_a_red_main_lets_its_repair_merge(tmp_path: Path, title: str, body: str) -> None:
    assert guarded(tmp_path, runs(run("failure", "2026-10-16T10:00:00Z")), title, body) == 0


def test_a_mention_of_mending_inside_a_line_is_not_a_repair(tmp_path: Path) -> None:
    body = "This does not say Mends main: a1b2c3d at the start of a line.\n"
    assert guarded(tmp_path, runs(run("failure", "2026-10-16T10:00:00Z")), body=body) == 1


@pytest.mark.parametrize("answer", [None, "", "not json", {"message": "Bad credentials"}])
def test_no_answer_from_the_host_holds_every_pull_request(tmp_path: Path, answer: object) -> None:
    assert guarded(tmp_path, answer) == 1


def test_a_main_without_a_completed_run_holds_nothing(tmp_path: Path) -> None:
    assert guarded(tmp_path, runs()) == 0


def test_the_failed_tests_are_read_from_the_log_once_each() -> None:
    prefix = "test\tUNKNOWN STEP\t2026-10-16T10:00:00Z"
    log = "\n".join(
        [
            f"{prefix} FAILED tests/integration/test_a.py::test_x - AssertionError",
            f"{prefix} ERROR tests/integration/test_b.py::test_y",
            f"{prefix} FAILED tests/integration/test_a.py::test_x - AssertionError",
            f"{prefix} 1 failed, 235 passed",
        ]
    )
    assert ci_watch.failed_tests(log) == [
        "tests/integration/test_a.py::test_x",
        "tests/integration/test_b.py::test_y",
    ]


@pytest.mark.parametrize(
    ("conclusion", "attempt", "branch", "event", "expected"),
    [
        ("failure", 1, "main", "push", "rerun"),
        ("failure", 1, "feat/x", "pull_request", "rerun"),
        ("failure", 2, "main", "push", "main-red"),
        ("failure", 2, "feat/x", "pull_request", "none"),
        ("success", 2, "main", "push", "flake"),
        ("success", 2, "feat/x", "pull_request", "flake"),
        ("success", 1, "main", "push", "main-green"),
        ("success", 1, "feat/x", "pull_request", "none"),
        ("cancelled", 1, "feat/x", "pull_request", "none"),
    ],
)
def test_what_follows_a_finished_run(
    conclusion: str, attempt: int, branch: str, event: str, expected: str
) -> None:
    finished = {
        "conclusion": conclusion,
        "run_attempt": attempt,
        "head_branch": branch,
        "event": event,
    }
    assert ci_watch.decide(finished) == expected
