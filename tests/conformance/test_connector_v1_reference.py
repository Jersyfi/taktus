"""The suite against the reference connector: every check the suite can run passes.

C-10 stays pending by design — the removal test needs processes that use a connector, and none
does yet. Nothing here marks the connector *verified* (docs/architecture/contracts.md §3).
"""

from __future__ import annotations

import json

import httpx

from taktus.conformance import Status

from .conftest import StartConnector


async def test_reference_connector_passes(start_connector: StartConnector) -> None:
    connector = start_connector()
    report = await connector.run_suite()
    statuses = {c.id: c.status for c in report.checks}
    assert report.failed == [], report.render()
    assert report.inconclusive == [], report.render()
    assert statuses.pop("C-10") is Status.PENDING
    assert set(statuses.values()) == {Status.PASSED}
    assert report.exit_code == 0
    purposes = {c.purpose for c in report.calls}
    assert {"read", "read without credential", "write", "write repeated", "invalid"} <= purposes
    assert {"signed", "unsigned", "wrongly signed", "unsupported", "own action"} <= purposes


async def test_the_suite_acted_once_per_key_on_the_target(start_connector: StartConnector) -> None:
    """What the fake service holds after a run: every write of the scenario acted exactly
    twice — once for the first key, once for the new key — and never for the repeat."""
    connector = start_connector()
    report = await connector.run_suite()
    assert report.failed == [], report.render()
    async with httpx.AsyncClient(timeout=5.0) as client:
        state = (await client.get(f"{connector.service_url}/_fake/state")).json()
    counts = state["conformance/target"]
    assert counts["pulls"] == 2
    assert counts["comments"] == 2
    assert counts["issues"] == 1 + 2  # the seed issue, then two conformance issues


async def test_report_is_machine_readable_and_claims_no_verification(
    start_connector: StartConnector,
) -> None:
    connector = start_connector()
    report = await connector.run_suite()
    document = json.loads(report.to_json())
    assert document["contract"] == "connector/v1"
    assert document["maturity"]["verified"] is False
    assert document["maturity"]["removal_test"] == "pending"
    assert document["maturity"]["conformance_suite"] == "passed"
    assert [c["id"] for c in document["checks"]] == [f"C-{n:02d}" for n in range(1, 11)]
    for check in document["checks"]:
        assert check["requirement"]
        assert check["section"].startswith("contracts/connector/v1/README.md")
    text = report.to_json() + connector.log.read_text()
    for value in connector.credential_values.values():
        assert value not in text
