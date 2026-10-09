"""The suite against the chat connector, and the meta-test that it fails where it should.

The connector runs against the fake of its service as a process of its own, with the scenario in
its own directory, exactly as the repository connector does. Every check the suite can run
passes; C-10 stays pending. Then, for every fault the connector can inject, the suite must fail
on exactly the check the fault breaks — the stale delivery among them, which only a timestamped
signature scheme has (README §7).
"""

from __future__ import annotations

import httpx
import pytest

from taktus.conformance import Status
from taktus.conformance.connector.rules import CHECKS

from .conftest import StartConnector, chat_connector_faults

FAULTS = chat_connector_faults()


async def test_the_chat_connector_passes(start_chat_connector: StartConnector) -> None:
    connector = start_chat_connector()
    report = await connector.run_suite()
    statuses = {c.id: c.status for c in report.checks}
    assert report.failed == [], report.render()
    assert report.inconclusive == [], report.render()
    assert statuses.pop("C-10") is Status.PENDING
    assert set(statuses.values()) == {Status.PASSED}
    assert report.exit_code == 0
    purposes = {c.purpose for c in report.calls}
    assert {"read", "read without credential", "write", "write repeated", "invalid"} <= purposes
    assert {"signed", "unsigned", "wrongly signed", "stale", "unsupported", "own action"} <= (
        purposes
    )
    text = report.to_json() + connector.log.read_text()
    for value in connector.credential_values.values():
        assert value not in text


async def test_the_suite_posted_once_per_key(start_chat_connector: StartConnector) -> None:
    """What the fake holds after a run: each write of the scenario posted exactly twice — once
    for the first key, once for the new key — and never for the repeat."""
    connector = start_chat_connector()
    report = await connector.run_suite()
    assert report.failed == [], report.render()
    async with httpx.AsyncClient(timeout=5.0) as client:
        state = (await client.get(f"{connector.service_url}/_fake/state")).json()
        listed = await client.get(
            f"{connector.service_url}/_fake/messages", params={"channel": "C0000000001"}
        )
    messages = listed.json()["messages"]
    assert state["C0000000001"] == 1 + 2 + 2  # the seed, two replies, two top-level messages
    replies = [m for m in messages if m.get("thread_ts") == "1700000000.000100"]
    assert len(replies) == 2


def test_every_runtime_check_has_a_fault() -> None:
    broken = {check for _, check in FAULTS}
    assert broken == set(CHECKS) - {"C-10"}, "C-10 is the only check without a runtime fault"


@pytest.mark.parametrize(("fault", "check"), FAULTS, ids=[f for f, _ in FAULTS])
async def test_fault_fails_exactly_its_check(
    start_chat_connector: StartConnector, fault: str, check: str
) -> None:
    connector = start_chat_connector(fault=fault)
    report = await connector.run_suite()
    failed = {c.id for c in report.failed}
    assert failed == {check}, report.render()
    for other in report.checks:
        if other.id != check:
            assert other.status in {Status.PASSED, Status.INCONCLUSIVE, Status.PENDING}
    assert report.exit_code == 1
