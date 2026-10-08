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


async def test_reference_connector_passes_as_the_app(start_connector: StartConnector) -> None:
    """The same suite, the connector acting as Taktus's own app (ADR-0033): it mints its
    tokens from a key, and every check passes as in the token mode — C-03 included, because the
    app serves the one name the scenario references and is no fallback for a call without it."""
    connector = start_connector(app=True)
    report = await connector.run_suite()
    statuses = {c.id: c.status for c in report.checks}
    assert report.failed == [], report.render()
    assert report.inconclusive == [], report.render()
    assert statuses.pop("C-10") is Status.PENDING
    assert set(statuses.values()) == {Status.PASSED}


async def test_as_the_app_no_token_or_statement_appears_anywhere(
    start_connector: StartConnector,
) -> None:
    """C-04 as the suite runs it knows only the values it was handed — here the app's key. The
    tokens and signed statements the connector minted are known to the fake alone; they are
    looked for here, in the report and the connector's log, line by line of the key as well."""
    connector = start_connector(app=True)
    report = await connector.run_suite()
    assert report.failed == [], report.render()
    async with httpx.AsyncClient(timeout=5.0) as client:
        seen = (await client.get(f"{connector.service_url}/_fake/app")).json()
    assert seen["issued"] and seen["statements"]
    text = report.to_json() + connector.log.read_text()
    for value in (*seen["issued"], *seen["statements"]):
        assert value not in text
    key = connector.credential_values["REPOSITORY_APP_KEY"]
    for line in key.splitlines():
        if line and "-----" not in line:
            assert line not in text
