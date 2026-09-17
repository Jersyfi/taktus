"""The meta-test for the connector suite: it fails where it should, and only there.

For every fault the reference connector can inject, the suite runs against a connector started
with that fault and must report exactly the check the fault breaks as failed. A check that
becomes unprovable because an earlier one failed may be inconclusive; nothing else may fail.
"""

from __future__ import annotations

import pytest

from taktus.conformance import Status
from taktus.conformance.connector.rules import CHECKS

from .conftest import StartConnector, connector_faults

FAULTS = connector_faults()


def test_every_runtime_check_has_a_fault() -> None:
    broken = {check for _, check in FAULTS}
    assert broken == set(CHECKS) - {"C-10"}, "C-10 is the only check without a runtime fault"


@pytest.mark.parametrize(("fault", "check"), FAULTS, ids=[f for f, _ in FAULTS])
async def test_fault_fails_exactly_its_check(
    start_connector: StartConnector, fault: str, check: str
) -> None:
    connector = start_connector(fault=fault)
    report = await connector.run_suite()
    failed = {c.id for c in report.failed}
    assert failed == {check}, report.render()
    result = next(c for c in report.checks if c.id == check)
    assert result.section.startswith("contracts/connector/v1/README.md §")
    assert result.observed
    for other in report.checks:
        if other.id != check:
            assert other.status in {Status.PASSED, Status.INCONCLUSIVE, Status.PENDING}
    assert report.exit_code == 1
