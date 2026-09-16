"""The meta-test: the suite fails where it should, and only there.

For every fault the reference worker can inject, the suite is run against a worker started with
that fault, and must report exactly the check the fault breaks as failed. A check that becomes
unprovable because an earlier one failed is allowed to be inconclusive; nothing else may fail.
Without this test a suite that always passes would tell nobody anything.
"""

from __future__ import annotations

import pytest

from taktus.conformance import Status
from taktus.conformance.rules import CHECKS

from .conftest import StartWorker, faults

FAULTS = faults()


def test_every_runtime_check_has_a_fault() -> None:
    broken = {check for _, check in FAULTS}
    assert broken == set(CHECKS) - {"W-12"}, "W-12 is the only check without a runtime fault"


@pytest.mark.parametrize(("fault", "check"), FAULTS, ids=[f for f, _ in FAULTS])
async def test_fault_fails_exactly_its_check(
    start_worker: StartWorker, fault: str, check: str
) -> None:
    worker = start_worker(fault=fault)
    report = await worker.run_suite()
    failed = {c.id for c in report.failed}
    assert failed == {check}, report.render()
    result = next(c for c in report.checks if c.id == check)
    assert result.section.startswith("contracts/worker/v1/README.md §")
    assert result.observed
    for other in report.checks:
        if other.id != check:
            assert other.status in {Status.PASSED, Status.INCONCLUSIVE, Status.PENDING}
    assert report.exit_code == 1
