"""The suite against the ML bench, honest and with every fault.

The ML bench is the second proof case of the worker contract (ADR-0007): progress in epochs, a
model artifact with metrics at the end. Its task here trains a real classifier on a dataset a
file server in the test serves, from a host the frame allows; the epochs are held for a fifth of
a second each so that the suite's stop lands while it trains. What it trains, and that the
training is reproducible, is `tests/workers/test_mlbench.py`.
"""

from __future__ import annotations

import json

import pytest

from taktus.conformance import Status
from taktus.conformance.rules import CHECKS

from .conftest import RunningWorker, StartWorker, mlbench_faults

FAULTS = mlbench_faults()


# The extensions this worker does not offer (ADR-0139): W-19 and W-20 hold it to refusing
# them, and the reference worker's faults prove both checks; W-21 is the outbound binding,
# which this worker does not offer either.
NOT_OFFERED = {"W-19", "W-20", "W-21"}


def test_every_runtime_check_has_a_fault() -> None:
    broken = {check for _, check in FAULTS}
    assert broken == set(CHECKS) - {"W-12", *NOT_OFFERED}


async def test_the_ml_bench_passes_the_suite(start_mlbench_worker: StartWorker) -> None:
    worker: RunningWorker = start_mlbench_worker()
    report = await worker.run_suite()
    statuses = {c.id: c.status for c in report.checks}
    assert report.failed == [], report.render()
    assert report.inconclusive == [], report.render()
    assert statuses.pop("W-12") is Status.PENDING
    assert statuses.pop("W-21") is Status.PENDING, "reached at an endpoint"
    assert set(statuses.values()) == {Status.PASSED}
    runs = {r.purpose: r for r in report.runs}
    assert runs["main"].outcome == "succeeded"
    assert runs["stopped"].outcome == "stopped" and runs["resumed"].outcome == "succeeded"
    assert runs["tight"].outcome == "stopped", "the epochs overrun the estimate; the limit halts"
    assert worker.credential_value not in report.to_json()
    assert worker.credential_value not in worker.log.read_text()
    assert json.loads(report.to_json())["endpoint"] == worker.endpoint


@pytest.mark.parametrize(("fault", "check"), FAULTS, ids=[f for f, _ in FAULTS])
async def test_fault_fails_exactly_its_check(
    start_mlbench_worker: StartWorker, fault: str, check: str
) -> None:
    worker = start_mlbench_worker(fault=fault)
    report = await worker.run_suite()
    failed = {c.id for c in report.failed}
    assert failed == {check}, report.render()
    for other in report.checks:
        if other.id != check:
            assert other.status in {Status.PASSED, Status.INCONCLUSIVE, Status.PENDING}
    assert report.exit_code == 1
