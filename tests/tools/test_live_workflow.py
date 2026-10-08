"""Live tests run where DEC-0048 puts them, and their secrets reach no other workflow.

A test that needs a credential never runs on a pull request: the repository is public, and a
secret in a pull request's pipeline is reachable from every workflow that names it. It runs on a
schedule or by dispatch, on `main`, never in a fork, in the environment `live`, under a cap. The
environment's own rule — it admits `main` alone — is set by the owner at the hosting service
(NEED-0012, NEED-0013) and cannot be seen from here; everything the workflows say can.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
LIVE = WORKFLOWS / "live.yml"
ENVIRONMENT = "live"
LIVE_SECRETS = {"LIVE_REPOSITORY_TOKEN", "CODING_AGENT_API_KEY"}
"""The secrets of the live tests (NEED-0012; the connector's scratch repository is reached through
Taktus's own app, NEED-0013)."""
SPENDING_SECRETS = {"CODING_AGENT_API_KEY"}
"""Secrets whose use costs money: a job that reads one carries the cap."""
CAP = "vars.LIVE_SPEND_CAP_USD"
TRIGGERS = {"schedule", "workflow_dispatch"}
GUARD = ("github.repository == 'Jersyfi/taktus'", "github.ref == 'refs/heads/main'")
SECRET = re.compile(r"secrets\.([A-Z0-9_]+)")


def load(path: Path) -> dict[str, Any]:
    data: dict[Any, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    # YAML 1.1 reads the key `on` as the boolean true.
    if True in data:
        data["on"] = data.pop(True)
    return data


def environment(job: dict[str, Any]) -> str | None:
    env = job.get("environment")
    return env.get("name") if isinstance(env, dict) else env


def test_live_tests_run_on_a_schedule_or_by_dispatch_only() -> None:
    triggers = load(LIVE)["on"]
    assert set(triggers) == TRIGGERS, (
        f"live.yml runs on {sorted(triggers)}; DEC-0048 allows {sorted(TRIGGERS)}"
    )


def test_every_live_job_is_guarded_to_main_and_this_repository_and_runs_in_the_environment() -> (
    None
):
    for name, job in load(LIVE)["jobs"].items():
        assert environment(job) == ENVIRONMENT, (
            f"job {name} runs outside the environment {ENVIRONMENT!r}"
        )
        condition = str(job.get("if", ""))
        for part in GUARD:
            assert part in condition, f"job {name} is not guarded by {part}"
        assert job.get("timeout-minutes"), f"job {name} has no time limit"


def test_live_tests_run_monthly() -> None:
    """DEC-0058: monthly and by dispatch; weekly was more than the interfaces need."""
    for entry in load(LIVE)["on"]["schedule"]:
        _minute, _hour, day, month, weekday = str(entry["cron"]).split()
        assert day.isdigit() and month == "*" and weekday == "*", (
            f"live.yml runs on {entry['cron']!r}, not once a month (DEC-0058)"
        )


def spends(job: dict[str, Any]) -> bool:
    return bool(SPENDING_SECRETS & set(SECRET.findall(yaml.safe_dump(job))))


def test_a_job_that_spends_money_carries_the_cap() -> None:
    for name, job in load(LIVE)["jobs"].items():
        if spends(job):
            assert CAP in yaml.safe_dump(job), (
                f"job {name} reads a secret that costs money and no {CAP}"
            )


def test_a_job_that_spends_money_refuses_to_start_without_the_cap() -> None:
    """Its first step fails when the cap is not set, before anything is checked out, installed
    or handed a secret (NEED-0012 §4, step 6)."""
    for name, job in load(LIVE)["jobs"].items():
        if not spends(job):
            continue
        first = job["steps"][0]
        assert f"{CAP} == ''" in str(first.get("if", "")), (
            f"job {name}: its first step does not run exactly when {CAP} is unset"
        )
        assert "exit 1" in str(first.get("run", "")), f"job {name}: its first step does not fail"


def test_the_coding_worker_runs_live_and_keeps_its_evidence() -> None:
    """The live test of the coding worker (#68) runs in the job `coding`, required — a missing
    credential fails it rather than skipping — and the job keeps what the run left whatever
    happened."""
    job = load(LIVE)["jobs"]["coding"]
    text = yaml.safe_dump(job)
    assert "tests/workers/test_coding_worker_live.py" in text
    assert "TAKTUS_REQUIRE_LIVE" in text
    kept = [s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/upload-artifact")]
    assert kept and kept[0].get("if") == "always()", "the evidence is kept whatever happened"


@pytest.mark.parametrize("path", sorted(WORKFLOWS.glob("*.yml")), ids=lambda p: p.name)
def test_no_other_workflow_reaches_the_live_secrets(path: Path) -> None:
    if path == LIVE:
        return
    text = path.read_text(encoding="utf-8")
    named = LIVE_SECRETS & set(SECRET.findall(text))
    assert not named, f"{path.name} names the live secrets {sorted(named)}; only live.yml may"
    for name, job in load(path).get("jobs", {}).items():
        assert environment(job) != ENVIRONMENT, (
            f"{path.name}: job {name} names the environment {ENVIRONMENT!r}"
        )
