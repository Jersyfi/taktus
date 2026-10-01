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
        "narrowed-hosts",
        "stopped",
        "resumed",
        "over-limit",
        "tight",
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
    assert [c["id"] for c in document["checks"]] == [f"W-{n:02d}" for n in range(1, 15)]
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


@pytest.mark.parametrize("profile", ["quick", "longrun"])
async def test_an_underestimating_worker_halts_at_the_limit(
    start_worker: StartWorker, profile: str
) -> None:
    """The worker estimates half of what it uses. Under a compute limit equal to its estimate
    it starts — the estimate fits — and halts at the boundary where the next step would carry
    the running total across the limit: stopped, with the checkpoint and the limit named."""
    worker = start_worker(profile=profile, estimate_factor=0.5)
    report = await worker.run_suite()
    w14 = next(c for c in report.checks if c.id == "W-14")
    assert w14.status is Status.PASSED, report.render()
    assert "halted at the boundary" in w14.observed and "'compute'" in w14.observed
    runs = {r.purpose: r for r in report.runs}
    assert runs["tight"].outcome == "stopped"
    assert runs["tight"].events < runs["main"].events


async def test_a_worker_that_never_overruns_leaves_w14_inconclusive(
    start_worker: StartWorker,
) -> None:
    """A worker whose actual stays within its estimate cannot be made to cross a limit its
    estimate fits. The suite says so, with the numbers, instead of claiming a pass."""
    worker = start_worker(estimate_factor=2.0)
    report = await worker.run_suite()
    w14 = next(c for c in report.checks if c.id == "W-14")
    assert w14.status is Status.INCONCLUSIVE, report.render()
    assert "never exceeded the estimate" in w14.observed
    assert "compute_seconds" in w14.observed
    assert report.failed == []
    assert "tight" not in {r.purpose for r in report.runs}
