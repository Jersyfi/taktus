"""The suite against the connectors over open standards, and the meta-test that it fails where
it should (ADR-0111, issue #441).

Each connector runs as a process of its own against a local server in a process of its own:
the mail connector against a fake mail server that speaks IMAP and SMTP, the metrics connector
against a fake store that answers the query API, the check connector against a fake service.
Every check the suite can run passes; the metrics and the check connector only read, so C-05
passes as not applicable, and neither has an intake, so C-07 and C-08 pass as not applicable
too. C-10 stays pending. Then, for every fault a connector can inject, the suite must fail on
exactly the check the fault breaks (README §8).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from taktus.conformance import Status
from taktus.conformance.connector.rules import CHECKS

from .conftest import CONNECTORS, StartConnector, open_standard_faults

MAIL_FAULTS = open_standard_faults("mail")
METRICS_FAULTS = open_standard_faults("prometheus")
CHECK_FAULTS = open_standard_faults("httpcheck")


def passes(report_text: str, statuses: dict[str, Status]) -> None:
    assert statuses.pop("C-10") is Status.PENDING, report_text
    assert set(statuses.values()) == {Status.PASSED}, report_text


async def test_the_mail_connector_passes(start_mail_connector: StartConnector) -> None:
    connector = start_mail_connector()
    report = await connector.run_suite()
    assert report.failed == [] and report.inconclusive == [], report.render()
    passes(report.render(), {c.id: c.status for c in report.checks})
    assert report.exit_code == 0
    purposes = {c.purpose for c in report.calls}
    assert {"read", "write", "write repeated", "write with a new key", "invalid"} <= purposes
    text = report.to_json() + connector.log.read_text()
    for value in connector.credential_values.values():
        assert value not in text


async def test_the_suite_sent_one_message_per_key(start_mail_connector: StartConnector) -> None:
    """What the fake holds after a run: each of the two writes sent two messages — one for the
    first key, one for the new key — and none for the repeat; each has its copy in the sent
    folder, under the identifier its key gives."""
    connector = start_mail_connector()
    report = await connector.run_suite()
    assert report.failed == [], report.render()
    async with httpx.AsyncClient(timeout=5.0) as client:
        state = (await client.get(f"{connector.service_url}/_fake/state")).json()
        sent = (await client.get(f"{connector.service_url}/_fake/messages?mailbox=Sent")).json()
    assert state["submitted"] == 4
    assert state["mailboxes"]["Sent"] == 4
    assert len({m["message_id"] for m in sent}) == 4
    assert all(m["message_id"].endswith(".taktus@mail.example>") for m in sent)


async def test_a_mail_scenario_without_its_writes_is_inconclusive(
    start_mail_connector: StartConnector, tmp_path: Path
) -> None:
    """A scenario that names no write for a connector that can repeat one proves nothing about
    C-05, and the suite says so instead of passing it."""
    scenario = json.loads((CONNECTORS / "mail" / "scenario.json").read_text(encoding="utf-8"))
    scenario["writes"] = []
    path = CONNECTORS / "mail" / "scenario.json"
    copy = tmp_path / "scenario.json"
    copy.write_text(json.dumps(scenario), encoding="utf-8")
    (tmp_path / "payloads").symlink_to(path.parent / "payloads")
    report = await start_mail_connector(scenario=copy).run_suite()
    assert report.failed == [], report.render()
    assert [c.id for c in report.inconclusive] == ["C-05"], report.render()
    assert report.exit_code == 2


@pytest.mark.parametrize("start", ["start_metrics_connector", "start_check_connector"])
async def test_a_connector_that_only_reads_passes(
    start: str, request: pytest.FixtureRequest
) -> None:
    connector = request.getfixturevalue(start)()
    report = await connector.run_suite()
    assert report.failed == [] and report.inconclusive == [], report.render()
    statuses = {c.id: c for c in report.checks}
    c05 = statuses["C-05"]
    assert "not applicable" in c05.observed + " ".join(c05.details), report.render()
    passes(report.render(), {c.id: c.status for c in report.checks})
    text = report.to_json() + connector.log.read_text()
    for value in connector.credential_values.values():
        assert value not in text


def test_every_runtime_check_has_a_fault() -> None:
    assert {check for _, check in MAIL_FAULTS} == set(CHECKS) - {"C-10"}
    for faults in (METRICS_FAULTS, CHECK_FAULTS):
        assert {check for _, check in faults} == set(CHECKS) - {"C-05", "C-07", "C-08", "C-10"}, (
            "C-05 needs an outward operation and C-07, C-08 an intake, which a connector that "
            "only reads has not; C-10 has no runtime fault"
        )


async def _fails_exactly(connector_start: StartConnector, fault: str, check: str) -> None:
    report = await connector_start(fault=fault).run_suite()
    assert {c.id for c in report.failed} == {check}, report.render()
    for other in report.checks:
        if other.id != check:
            assert other.status in {Status.PASSED, Status.INCONCLUSIVE, Status.PENDING}
    assert report.exit_code == 1


@pytest.mark.parametrize(("fault", "check"), MAIL_FAULTS, ids=[f for f, _ in MAIL_FAULTS])
async def test_a_mail_fault_fails_exactly_its_check(
    start_mail_connector: StartConnector, fault: str, check: str
) -> None:
    await _fails_exactly(start_mail_connector, fault, check)


@pytest.mark.parametrize(("fault", "check"), METRICS_FAULTS, ids=[f for f, _ in METRICS_FAULTS])
async def test_a_metrics_fault_fails_exactly_its_check(
    start_metrics_connector: StartConnector, fault: str, check: str
) -> None:
    await _fails_exactly(start_metrics_connector, fault, check)


@pytest.mark.parametrize(("fault", "check"), CHECK_FAULTS, ids=[f for f, _ in CHECK_FAULTS])
async def test_a_check_fault_fails_exactly_its_check(
    start_check_connector: StartConnector, fault: str, check: str
) -> None:
    await _fails_exactly(start_check_connector, fault, check)
