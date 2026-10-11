"""The suite against the wiki connector, and the meta-test that it fails where it should.

The connector runs against the fake of the wiki as a process of its own, with the scenario in
its own directory, exactly as the repository and the chat connector do. Every check the suite
can run passes; the connector has no intake, so C-07 and C-08 pass as not applicable, and C-10
stays pending. Then, for every fault the connector can inject, the suite must fail on exactly
the check the fault breaks (README §8).
"""

from __future__ import annotations

import httpx
import pytest

from taktus.conformance import Status
from taktus.conformance.connector.rules import CHECKS

from .conftest import StartConnector, knowledge_connector_faults

FAULTS = knowledge_connector_faults()


async def test_the_wiki_connector_passes(start_knowledge_connector: StartConnector) -> None:
    connector = start_knowledge_connector()
    report = await connector.run_suite()
    statuses = {c.id: c.status for c in report.checks}
    assert report.failed == [], report.render()
    assert report.inconclusive == [], report.render()
    assert statuses.pop("C-10") is Status.PENDING
    assert set(statuses.values()) == {Status.PASSED}
    assert report.exit_code == 0
    purposes = {c.purpose for c in report.calls}
    assert {"read", "read without credential", "write", "write repeated", "invalid"} <= purposes
    text = report.to_json() + connector.log.read_text()
    for value in connector.credential_values.values():
        assert value not in text


async def test_the_suite_wrote_one_page_per_key(start_knowledge_connector: StartConnector) -> None:
    """What the fake holds after a run: the write of the scenario made two pages — one for the
    first key, one for the new key — and none for the repeat. The wiki changed the text it
    stored, and each page kept the digest of what was written beside it."""
    connector = start_knowledge_connector()
    report = await connector.run_suite()
    assert report.failed == [], report.render()
    async with httpx.AsyncClient(timeout=5.0) as client:
        state = (await client.get(f"{connector.service_url}/_fake/state")).json()
        pages = (await client.get(f"{connector.service_url}/_fake/pages")).json()["pages"]
    assert state["pages"]["Conformance"] == 2 + 2  # the two seeded pages, two written
    written = [p for p in pages if p["name"].startswith("Page ")]
    assert len(written) == 2
    for page in written:
        tags = {t["name"]: t["value"] for t in page["tags"]}
        assert tags["taktus-digest"] != tags["taktus-stored"], "the fake changed the text"


def test_every_runtime_check_has_a_fault() -> None:
    broken = {check for _, check in FAULTS}
    assert broken == set(CHECKS) - {"C-07", "C-08", "C-10"}, (
        "C-07 and C-08 are about an intake, which the connector has not; C-10 has no runtime fault"
    )


@pytest.mark.parametrize(("fault", "check"), FAULTS, ids=[f for f, _ in FAULTS])
async def test_fault_fails_exactly_its_check(
    start_knowledge_connector: StartConnector, fault: str, check: str
) -> None:
    connector = start_knowledge_connector(fault=fault)
    report = await connector.run_suite()
    failed = {c.id for c in report.failed}
    assert failed == {check}, report.render()
    for other in report.checks:
        if other.id != check:
            assert other.status in {Status.PASSED, Status.INCONCLUSIVE, Status.PENDING}
    assert report.exit_code == 1
