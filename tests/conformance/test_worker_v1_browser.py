"""The suite against the browser worker (ADR-0218): a web page served in the test, checked in
headless Chromium three times — a search typed and clicked, its answer read. The page's host is
allowed in the main run and withdrawn in the narrowed one (W-13).

The worker's contract around its steps is the reference worker's; its faults are that worker's
and are proven there (`test_worker_v1_faults.py`). Two of them run here, to show that the
browser worker keeps the checks they break.
"""

from __future__ import annotations

import json

import pytest

from taktus.conformance import Status

from .conftest import RunningWorker, StartWorker


async def test_the_browser_worker_passes_the_suite(start_browser_worker: StartWorker) -> None:
    worker: RunningWorker = start_browser_worker()
    report = await worker.run_suite()
    statuses = {c.id: c.status for c in report.checks}
    assert report.failed == [], report.render()
    assert report.inconclusive == [], report.render()
    assert statuses.pop("W-12") is Status.PENDING
    assert statuses.pop("W-21") is Status.PENDING, "reached at an endpoint"
    assert set(statuses.values()) == {Status.PASSED}
    runs = {r.purpose: r for r in report.runs}
    assert runs["main"].outcome == "succeeded"
    assert worker.credential_value not in report.to_json()
    assert worker.credential_value not in worker.log.read_text()
    assert json.loads(report.to_json())["endpoint"] == worker.endpoint


@pytest.mark.parametrize(("fault", "check"), [("W-07", "W-07"), ("W-13", "W-13")])
async def test_a_fault_of_the_frame_fails_exactly_its_check(
    start_browser_worker: StartWorker, fault: str, check: str
) -> None:
    worker = start_browser_worker(fault=fault)
    report = await worker.run_suite()
    assert {c.id for c in report.failed} == {check}, report.render()
