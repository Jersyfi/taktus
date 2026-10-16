"""The CI workflow runs its lanes in parallel under one required check, never lets a job run
without a bound, and never cancels a run on `main` (ADR-0096, issue #388)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
CI = WORKFLOWS / "ci.yml"
# The check the ruleset of `main` requires. Renaming it would leave the ruleset waiting for a
# check that no longer reports.
REQUIRED = "gates"


def load(path: Path) -> dict[str, Any]:
    document: dict[Any, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    # YAML 1.1 reads the key `on` as true.
    document["on"] = document.pop(True, document.get("on"))
    return document


def test_every_job_of_every_workflow_has_a_timeout() -> None:
    # A job without one runs for GitHub's default of six hours when a test hangs.
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for name, job in load(path)["jobs"].items():
            if "uses" in job:  # a reusable workflow carries its own
                continue
            assert isinstance(job.get("timeout-minutes"), int), f"{path.name}: {name}"


def test_the_required_check_needs_every_other_job_and_always_reports() -> None:
    jobs = load(CI)["jobs"]
    gates = jobs[REQUIRED]
    assert gates["if"] == "always()", "a skipped aggregate would satisfy the ruleset"
    assert set(gates["needs"]) == set(jobs) - {REQUIRED}, gates["needs"]
    lanes = next(step for step in gates["steps"] if step.get("name") == "every lane passed")
    assert 'all(.[]; .result == "success")' in lanes["run"], lanes


def test_the_last_step_on_a_pull_request_is_the_guard_of_main() -> None:
    """While `main` is red only its repair merges (ADR-0096 §5, #391); the guard decides from
    what the host answers, and fails when it answers nothing (tests/tools/test_ci_watch.py)."""
    gates = load(CI)["jobs"][REQUIRED]
    last = gates["steps"][-1]
    assert last["if"] == "github.event_name == 'pull_request'", last
    assert "tools/ci_watch.py guard" in last["run"], last
    assert gates["permissions"]["actions"] == "read", "the guard reads the runs on main"


def test_every_finished_run_of_ci_is_followed() -> None:
    """The automaton after every run: a repeat, the flake register, 'main is red' (#391)."""
    watch = load(WORKFLOWS / "ci-watch.yml")
    assert watch["on"] == {"workflow_run": {"workflows": ["ci"], "types": ["completed"]}}
    assert watch["permissions"] == {}, "every permission is the job's own"
    names = [step.get("name") for step in watch["jobs"]["follow"]["steps"]]
    for step in ("repeat once, and wait for the repeat", "the flake register", "main is red"):
        assert step in names, names


def test_a_superseded_run_is_cancelled_and_a_run_on_main_never() -> None:
    concurrency = load(CI)["concurrency"]
    assert "github.sha" in concurrency["group"], "every commit on main keeps a group of its own"
    assert concurrency["cancel-in-progress"] == "${{ github.ref != 'refs/heads/main' }}"


def test_the_slow_suites_run_in_lanes_of_their_own() -> None:
    jobs = load(CI)["jobs"]
    runs = {
        name: " ".join(step.get("run", "") for step in job["steps"]) for name, job in jobs.items()
    }
    assert "make gate-conformance" in runs["conformance"]
    assert "make test" in runs["test"]
    for name, text in runs.items():
        if name not in {"conformance", "test"}:
            assert "make gate-conformance" not in text and "make test" not in text, name
