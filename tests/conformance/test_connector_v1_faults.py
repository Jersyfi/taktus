"""The meta-test for the connector suite: it fails where it should, and only there.

For every fault the reference connector can inject, the suite runs against a connector started
with that fault and must report exactly the check the fault breaks as failed. A check that
becomes unprovable because an earlier one failed may be inconclusive; nothing else may fail.

The suite runs the way the instance runs it (ADR-0044): against `connector.channel.repo` as
the instance's configuration resolves it, with the connector's own scenario, recorded by the
catalog. So every fault is also recorded as not passed, naming exactly that check.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taktus.conformance import Status
from taktus.conformance.connector.rules import CHECKS

from .conftest import StartConnector, connector_faults, record_connector

FAULTS = connector_faults()


def test_every_runtime_check_has_a_fault() -> None:
    broken = {check for _, check in FAULTS}
    assert broken == set(CHECKS) - {"C-10"}, "C-10 is the only check without a runtime fault"


@pytest.mark.parametrize(("fault", "check"), FAULTS, ids=[f for f, _ in FAULTS])
async def test_fault_fails_exactly_its_check(
    start_connector: StartConnector, fault: str, check: str, tmp_path: Path
) -> None:
    connector = start_connector(fault=fault)
    recorded = await record_connector(connector, tmp_path)
    report = recorded.report
    assert recorded.failed() == {check}, report["checks"]
    result = next(c for c in report["checks"] if c["id"] == check)
    assert result["section"].startswith("contracts/connector/v1/README.md §")
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


async def test_an_app_that_serves_a_call_without_a_credential_fails_c03(
    start_connector: StartConnector,
) -> None:
    """The app mode's own risk is that the app becomes a fallback: a call that references no
    credential served with a token the connector minted. The suite catches it as it catches the
    token mode's (ADR-0033)."""
    connector = start_connector(fault="C-03", app=True)
    report = await connector.run_suite()
    assert {c.id for c in report.failed} == {"C-03"}, report.render()
