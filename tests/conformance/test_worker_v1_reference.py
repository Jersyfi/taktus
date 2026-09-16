"""The suite against the reference worker: both profiles pass every check the suite can run.

W-12 stays pending by design — the removal test needs processes, and none exist yet. Nothing
here marks the worker *verified* (docs/architecture/contracts.md §3).
"""

from __future__ import annotations

import json

import pytest

from taktus.conformance import Status

from .conftest import StartWorker


@pytest.mark.parametrize("profile", ["quick", "longrun"])
async def test_reference_worker_passes(start_worker: StartWorker, profile: str) -> None:
    worker = start_worker(profile=profile)
    report = await worker.run_suite()
    statuses = {c.id: c.status for c in report.checks}
    assert report.failed == [], report.render()
    assert report.inconclusive == [], report.render()
    assert statuses.pop("W-12") is Status.PENDING
    assert set(statuses.values()) == {Status.PASSED}
    assert report.exit_code == 0
    assert {r.purpose for r in report.runs} == {
        "main",
        "narrowed",
        "stopped",
        "resumed",
        "over-limit",
    }


async def test_report_is_machine_readable_and_claims_no_verification(
    start_worker: StartWorker,
) -> None:
    worker = start_worker()
    report = await worker.run_suite()
    document = json.loads(report.to_json())
    assert document["contract"] == "worker/v1"
    assert document["maturity"]["verified"] is False
    assert document["maturity"]["removal_test"] == "pending"
    assert document["maturity"]["conformance_suite"] == "passed"
    assert [c["id"] for c in document["checks"]] == [f"W-{n:02d}" for n in range(1, 13)]
    for check in document["checks"]:
        assert check["requirement"] and check["section"].startswith("contracts/worker/v1/README.md")
    assert worker.credential_value not in report.to_json()
    assert worker.credential_value not in worker.log.read_text()


async def test_longrun_stops_mid_run_and_resumes(start_worker: StartWorker) -> None:
    worker = start_worker(profile="longrun")
    report = await worker.run_suite()
    runs = {r.purpose: r for r in report.runs}
    assert runs["stopped"].outcome == "stopped"
    assert runs["resumed"].outcome == "succeeded"
    assert 0 < runs["stopped"].events < runs["main"].events
