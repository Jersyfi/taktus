"""Live tests run where DEC-0048 puts them, and their secrets reach no other workflow.

A test that needs a credential never runs on a pull request: the repository is public, and a
secret in a pull request's pipeline is reachable from every workflow that names it. It runs on a
schedule or by dispatch, on `main`, never in a fork, in the environment `live`, under a cap. The
environment's own rule — it admits `main` alone — is set by the owner at the hosting service
(NEED-0011, NEED-0012) and cannot be seen from here; everything the workflows say can.
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
"""The secrets the owner provides for live tests (NEED-0011, NEED-0012)."""
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


def test_a_job_that_spends_money_carries_the_cap() -> None:
    for name, job in load(LIVE)["jobs"].items():
        text = yaml.safe_dump(job)
        if SPENDING_SECRETS & set(SECRET.findall(text)):
            assert CAP in text, f"job {name} reads a secret that costs money and no {CAP}"


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
