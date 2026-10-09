"""The meta-test: the suite fails where it should, and only there.

For every fault the reference worker can inject, the suite is run against a worker started with
that fault, and must report exactly the check the fault breaks as failed. A check that becomes
unprovable because an earlier one failed is allowed to be inconclusive; nothing else may fail.
Without this test a suite that always passes would tell nobody anything.

The suite runs the way the instance runs it (ADR-0044): against `worker.endpoint` as the
instance's configuration resolves it, recorded by the catalog. So every fault is also recorded
as not passed, naming exactly that check.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taktus.conformance import Status
from taktus.conformance.rules import CHECKS

from .conftest import StartWorker, faults, record_worker

FAULTS = faults()


def test_every_runtime_check_has_a_fault() -> None:
    broken = {check for _, check in FAULTS}
    assert broken == set(CHECKS) - {"W-12"}, "W-12 is the only check without a runtime fault"


@pytest.mark.parametrize(("fault", "check"), FAULTS, ids=[f for f, _ in FAULTS])
async def test_fault_fails_exactly_its_check(
    start_worker: StartWorker, fault: str, check: str, tmp_path: Path
) -> None:
    worker = start_worker(fault=fault)
    recorded = await record_worker(worker, tmp_path)
    report = recorded.report
    assert recorded.failed() == {check}, report["checks"]
    result = next(c for c in report["checks"] if c["id"] == check)
    assert result["section"].startswith("contracts/worker/v1/README.md §")
    assert result["observed"]
    for other in report["checks"]:
        if other["id"] != check:
            assert other["status"] in {Status.PASSED, Status.INCONCLUSIVE, Status.PENDING}
    assert report["summary"]["exit_code"] == 1
    conformance = recorded.maturity.conformance
    assert conformance is not None and conformance.outcome == "failed"
    assert conformance.failed == (check,)
    assert recorded.entry.outcome == "failed"
    assert check in recorded.maturity.missing(recorded.current)[0]
