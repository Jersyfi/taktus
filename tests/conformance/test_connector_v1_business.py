"""The suite against the connectors for the systems a business names, and the meta-test that it
fails where it should (ADR-0150, issue #447).

Each connector runs as a process of its own against a fake of its product's API in a process
of its own: cloud billing, a model provider's costs, error tracking and a payment provider.
Every one only reads, so C-05 passes as not applicable, and none has an intake, so C-07 and
C-08 pass as not applicable too. C-10 stays pending. Then, for every fault a connector can
inject, the suite must fail on exactly the check the fault breaks (README §8).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from taktus.conformance import Status
from taktus.conformance.connector.rules import CHECKS

from .conftest import BUSINESS, CONNECTORS, RunningConnector, open_standard_faults

type Start = Callable[..., RunningConnector]
FAULTS = [
    (module, fault, check)
    for module in sorted(BUSINESS)
    if (CONNECTORS / module).is_dir()  # a missing one fails the tests above, not the collection
    for fault, check in open_standard_faults(module)
]


@pytest.mark.parametrize("module", sorted(BUSINESS))
async def test_a_business_connector_passes(module: str, start_business_connector: Start) -> None:
    connector = start_business_connector(module)
    report = await connector.run_suite()
    assert report.failed == [] and report.inconclusive == [], report.render()
    statuses = {c.id: c.status for c in report.checks}
    assert statuses.pop("C-10") is Status.PENDING, report.render()
    assert set(statuses.values()) == {Status.PASSED}, report.render()
    c05 = next(c for c in report.checks if c.id == "C-05")
    assert "not applicable" in c05.observed + " ".join(c05.details), report.render()
    text = report.to_json() + connector.log.read_text()
    for value in connector.credential_values.values():
        assert value not in text
        for part in value.split(":")[1:]:  # the secret half of a key pair never shows either
            assert part not in text


@pytest.mark.parametrize("module", sorted(BUSINESS))
def test_every_runtime_check_has_a_fault(module: str) -> None:
    assert {check for _, check in open_standard_faults(module)} == set(CHECKS) - {
        "C-05",
        "C-07",
        "C-08",
        "C-10",
    }, "C-05 needs an outward operation and C-07, C-08 an intake; C-10 has no runtime fault"


@pytest.mark.parametrize(
    ("module", "fault", "check"), FAULTS, ids=[f"{m}-{f}" for m, f, _ in FAULTS]
)
async def test_a_fault_fails_exactly_its_check(
    module: str, fault: str, check: str, start_business_connector: Start
) -> None:
    report = await start_business_connector(module, fault=fault).run_suite()
    assert {c.id for c in report.failed} == {check}, report.render()
    for other in report.checks:
        if other.id != check:
            assert other.status in {Status.PASSED, Status.INCONCLUSIVE, Status.PENDING}
    assert report.exit_code == 1
