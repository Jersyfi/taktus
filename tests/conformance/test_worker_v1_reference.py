"""The suite against the reference worker: both profiles pass every check the suite can run.

W-12 stays pending by design — the removal test needs processes, and none exist yet. Nothing
here marks the worker *verified* (docs/architecture/contracts.md §3).
"""

from __future__ import annotations

import json

import pytest

from taktus.conformance import Status, run_suite

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
        "held",
        "repeated",
        "after-command",
        "after-command-failing",
    }
    held = [r for r in report.runs if r.purpose == "held"]
    assert len(held) == 4, "the reference worker declares four places by default"
    w15 = next(c for c in report.checks if c.id == "W-15")
    assert "answered one more with 503" in w15.observed and "recorded nothing" in w15.observed
    w16 = next(c for c in report.checks if c.id == "W-16")
    assert "never posted, answered 404" in w16.observed
    w17 = next(c for c in report.checks if c.id == "W-17")
    repeats = [w17.observed, *w17.details]
    assert any("while it was running answered 409" in line for line in repeats), repeats
    assert any("while it was finished answered 409" in line for line in repeats), repeats
    w18 = next(c for c in report.checks if c.id == "W-18")
    assert "byte for byte" in w18.observed and "exited with 1" in w18.observed


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
    assert [c["id"] for c in document["checks"]] == [f"W-{n:02d}" for n in range(1, 19)]
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


async def test_a_capacity_beyond_what_the_suite_fills_leaves_w15_inconclusive(
    start_worker: StartWorker,
) -> None:
    """The reference worker declares four places. A suite that fills at most two says what to
    do instead of claiming a pass, and posts no assignment for the probe."""
    worker = start_worker()
    options = worker.options()
    options.max_held = 2
    report = await run_suite(options)
    w15 = next(c for c in report.checks if c.id == "W-15")
    assert w15.status is Status.INCONCLUSIVE, report.render()
    assert "declares 4 places" in w15.observed and "2 or fewer" in w15.observed
    assert report.failed == []
    assert "held" not in {r.purpose for r in report.runs}
