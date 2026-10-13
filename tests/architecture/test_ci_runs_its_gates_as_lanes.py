"""CI runs its gates as parallel jobs under one aggregate check (issue #388).

The ruleset requires one check, `gates`. It is a job that needs every other job of `ci`, always
reports, and passes when each of them passed or was skipped; so the lanes may change without the
ruleset changing. Every job has a time limit, so that a hung step fails its lane instead of
holding the run for the platform's six hours. A newer push cancels the run it supersedes, and a
run on `main` is never cancelled.

A run of Taktus may not write the repository's pipeline; a person changes it. Until `ci.yml` is
split into lanes — its job `gates` needs others — these tests are expected to fail; from then on
they hold, and the marker no longer applies.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def workflow() -> dict[str, Any]:
    document: dict[Any, Any] = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # YAML 1.1 reads the key `on` as true.
    document["on"] = document.pop(True, document.get("on"))
    return document


def split() -> bool:
    return "needs" in workflow()["jobs"].get("gates", {})


pytestmark = pytest.mark.xfail(
    not split(), reason="ci.yml is not split into lanes yet (issue #388)", strict=True
)


def test_every_job_has_a_time_limit() -> None:
    missing = [
        name
        for name, job in workflow()["jobs"].items()
        if not isinstance(job.get("timeout-minutes"), int)
    ]
    assert not missing, f"jobs of ci.yml without timeout-minutes: {missing}"


def test_the_aggregate_check_needs_every_lane_and_always_reports() -> None:
    jobs = workflow()["jobs"]
    gates = jobs["gates"]
    needs = gates["needs"]
    assert set([needs] if isinstance(needs, str) else needs) == set(jobs) - {"gates"}
    assert "always()" in gates["if"]
    # Passed or skipped is green; anything else — failure, cancelled — fails the check.
    script = " ".join(step.get("run", "") for step in gates["steps"])
    assert "success" in script
    assert "skipped" in script


def test_a_superseded_run_is_cancelled_and_a_run_on_main_never_is() -> None:
    concurrency = workflow()["concurrency"]
    assert concurrency["cancel-in-progress"] is True
    group = concurrency["group"]
    # On main the group is the run's own id, which no later run shares.
    assert "refs/heads/main" in group
    assert "github.run_id" in group
