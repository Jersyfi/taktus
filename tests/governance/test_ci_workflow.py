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
    script = gates["steps"][-1]["run"]
    assert 'all(.[]; .result == "success")' in script, script


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
