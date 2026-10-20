"""The suite against a vendor's MCP server behind the vendor connector (ADR-0117, issue #410).

The vendor's server is third-party code: the MCP project's reference time server
(`mcp-server-time`), installed from the lock file and served over streamable HTTP by
`tests/fakes/vendor_time_server.py`. Each runs as a process of its own, the connector in front
of it as another, and nothing reaches the network.

- **Without a manifest** the time server is served read only, its tools as reads, and passes
  every check the suite can run; C-05 passes as not applicable, C-10 stays pending.
- **With a manifest** it passes the same way under the operation names the manifest gives.
- The time server has no tool that writes. The stand-in under `tests/fakes/vendor_notes_server.py`
  has: with its manifest, a write the vendor recognises as a repeat passes C-05 for real, and
  every fault the connector can inject fails exactly the check it breaks.
- A write nobody declared is refused before the vendor's server is reached.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from fakes.identity import added_by_command_line
from fakes.ports import free_port
from mcp import Client

from taktus.conformance import Status
from taktus.conformance.connector.rules import CHECKS
from taktus.conformance.contracts import first_error

from .conftest import VENDOR, VENDOR_NOTES, StartConnector, _wait_listening, stop_all

TIME_MANIFEST = VENDOR / "time-manifest.json"
NOTES_MANIFEST = VENDOR / "notes-manifest.json"
NOTES_FAULTS = [
    ("C-01", "C-01"),
    ("C-02", "C-02"),
    ("C-03", "C-03"),
    ("C-04-result", "C-04"),
    ("C-04-log", "C-04"),
    ("C-05", "C-05"),
    ("C-06", "C-06"),
    ("C-09", "C-09"),
]


CONTEXT = {
    "tenant": "default",
    "identity": "idn_vendor",
    "run_id": "run_vendor",
    "step_id": "act",
    "attempt": 1,
    "idempotency_key": "run_vendor:act:1:abcdef",
    "credentials": [{"name": "VENDOR_TOKEN", "injected_as": "env"}],
    "autonomy_level": 1,
}


def passes(report_text: str, statuses: dict[str, Status]) -> None:
    assert statuses.pop("C-10") is Status.PENDING, report_text
    assert set(statuses.values()) == {Status.PASSED}, report_text


async def _declaration(endpoint: str) -> dict[str, object]:
    async with Client(endpoint, read_timeout_seconds=10.0) as client:
        resource = await client.read_resource("taktus://connector/v1/capabilities")
    text = getattr(resource.contents[0], "text", "")
    document: dict[str, object] = json.loads(text)
    return document


async def test_a_vendors_server_without_a_manifest_passes_read_only(
    start_vendor_connector: StartConnector,
) -> None:
    connector = start_vendor_connector(server="time")
    report = await connector.run_suite()
    assert report.failed == [] and report.inconclusive == [], report.render()
    statuses = {c.id: c for c in report.checks}
    c05 = statuses["C-05"]
    assert "not applicable" in c05.observed + " ".join(c05.details), report.render()
    passes(report.render(), {c.id: c.status for c in report.checks})
    declaration = await _declaration(connector.endpoint)
    assert declaration["wrapped"] == {}
    operations = declaration["operations"]
    assert isinstance(operations, list)
    assert {op["name"] for op in operations} == {
        "time.clock.get_current_time",
        "time.clock.convert_time",
    }
    assert {op["effect"] for op in operations} == {"read"}
    text = report.to_json() + connector.log.read_text()
    for value in connector.credential_values.values():
        assert value not in text


async def test_a_vendors_server_with_a_manifest_passes_under_its_names(
    start_vendor_connector: StartConnector,
) -> None:
    connector = start_vendor_connector(
        server="time", manifest=TIME_MANIFEST, scenario=VENDOR / "time-manifest-scenario.json"
    )
    report = await connector.run_suite()
    assert report.failed == [] and report.inconclusive == [], report.render()
    passes(report.render(), {c.id: c.status for c in report.checks})
    declaration = await _declaration(connector.endpoint)
    wrapped = declaration["wrapped"]
    assert isinstance(wrapped, dict) and str(wrapped["manifest"]).startswith("sha256:")


async def test_a_manifest_write_the_vendor_recognises_passes_c05(
    start_vendor_connector: StartConnector,
) -> None:
    """The stand-in's write takes the key as its request identifier: the repeat returns the
    original with `replayed: true`, a new key creates a second note, and the vendor saw the
    connector's bearer token and nothing else."""
    connector = start_vendor_connector(server="notes", manifest=NOTES_MANIFEST)
    report = await connector.run_suite()
    assert report.failed == [] and report.inconclusive == [], report.render()
    passes(report.render(), {c.id: c.status for c in report.checks})
    async with httpx.AsyncClient(timeout=5.0) as client:
        state = (await client.get(f"{connector.service_url}/_fake/state")).json()
    assert state["calls"]["create_note"] == 3
    assert state["notes"] == 2
    assert state["tokens"] == list(connector.credential_values.values())
    text = report.to_json() + connector.log.read_text()
    for value in connector.credential_values.values():
        assert value not in text


async def test_a_write_nobody_declared_is_refused_before_the_vendor(
    start_vendor_connector: StartConnector,
) -> None:
    """`delete_note` is in the vendor's listing and in no manifest: the connector does not
    declare it and does not serve it. A call by its name or by a name it could have had is
    refused, and the vendor's tool is never called. Without a manifest `create_note` is
    withheld in the same way."""
    for manifest, capability in ((NOTES_MANIFEST, None), (None, "notes.pages")):
        connector = start_vendor_connector(
            server="notes", manifest=manifest, capability=capability, admits="anyone"
        )
        declaration = await _declaration(connector.endpoint)
        operations = declaration["operations"]
        assert isinstance(operations, list)
        names = {op["name"] for op in operations}
        assert not any("delete" in name for name in names)
        if manifest is None:
            assert {op["effect"] for op in operations} == {"read"}
            assert not any("create" in name for name in names)
        async with Client(connector.endpoint, read_timeout_seconds=10.0) as client:
            for tool in ("delete_note", "notes.pages.delete_note", "notes.pages.create_note"):
                try:
                    answer = await client.call_tool(tool, {"context": CONTEXT, "input": {}})
                except Exception:  # noqa: S112 — a refusal as a protocol error is a refusal too
                    continue
                assert answer.is_error, tool
        async with httpx.AsyncClient(timeout=5.0) as client:
            state = (await client.get(f"{connector.service_url}/_fake/state")).json()
        assert "delete_note" not in state["calls"]
        assert "create_note" not in state["calls"]
        assert "withheld delete_note" in connector.log.read_text()


def test_without_a_manifest_a_listing_that_needs_a_credential_refuses_the_start(
    tmp_path: Path,
) -> None:
    """Without a manifest only the vendor's listing says which tools read. A server that lists
    them only to a client with a credential cannot be served that way: the connector has no
    credential of its own, and does not start."""
    port = free_port()
    vendor = subprocess.Popen(  # noqa: S603 — a script of the gate, fixed arguments
        [sys.executable, str(VENDOR_NOTES), "--port", str(port)],
        env={**os.environ, "FAKE_VENDOR_TOKENS": "only-this"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_listening(vendor, port, tmp_path / "vendor.log", "vendor's notes server")
        refused = subprocess.run(  # noqa: S603 — our own module, fixed arguments
            [
                sys.executable, "-m", "taktus.adapters.driven.connectors.vendor",
                "--upstream", f"http://127.0.0.1:{port}/mcp", "--capability", "notes.pages",
            ],
            capture_output=True, text=True, timeout=60, check=False,
        )  # fmt: skip
    finally:
        stop_all([vendor])
    assert refused.returncode == 2, refused.stderr
    assert "refused to start" in refused.stderr
    assert "answered 401" in refused.stderr


async def test_a_credential_the_vendor_does_not_accept_is_unauthenticated(
    start_vendor_connector: StartConnector,
) -> None:
    """The requesting identity's token goes to the vendor; one it refuses ends the call with
    `unauthenticated` and no effect, read or write."""
    connector = start_vendor_connector(
        server="notes", manifest=NOTES_MANIFEST, admits="another token"
    )
    async with Client(connector.endpoint, read_timeout_seconds=10.0) as client:
        for operation, input in (
            ("notes.pages.list", {}),
            ("notes.pages.create", {"title": "t", "body": "b"}),
        ):
            answer = await client.call_tool(operation, {"context": CONTEXT, "input": input})
            assert answer.is_error, operation
            error = answer.structured_content or {}
            assert error.get("cause") == "unauthenticated", error
            assert error.get("effect") == "none", error


def test_every_runtime_check_has_a_fault_for_the_notes_manifest() -> None:
    assert {check for _, check in NOTES_FAULTS} == set(CHECKS) - {"C-07", "C-08", "C-10"}, (
        "a vendor's server has no intake, and C-10 has no runtime fault"
    )


@pytest.mark.parametrize(("fault", "check"), NOTES_FAULTS, ids=[f for f, _ in NOTES_FAULTS])
async def test_a_vendor_fault_fails_exactly_its_check(
    start_vendor_connector: StartConnector, fault: str, check: str
) -> None:
    report = await start_vendor_connector(
        server="notes", manifest=NOTES_MANIFEST, fault=fault
    ).run_suite()
    assert {c.id for c in report.failed} == {check}, report.render()
    for other in report.checks:
        if other.id != check:
            assert other.status in {Status.PASSED, Status.INCONCLUSIVE, Status.PENDING}
    assert report.exit_code == 1


def test_the_scenarios_and_manifests_are_the_contracts_shapes() -> None:
    """Each file the gate runs validates against `Connector.json`, as an operator's would."""
    for path in sorted(VENDOR.glob("*.json")):
        definition = "Manifest" if path.stem.endswith("manifest") else "Scenario"
        document = json.loads(path.read_text(encoding="utf-8"))
        assert first_error(definition, document, "connector/v1") is None, path.name


def test_the_catalogue_lists_a_vendors_server_with_its_maturity(
    start_vendor_connector: StartConnector, tmp_path: Path
) -> None:
    """Issue #410: until the catalogue of #339 and #348 exists, `taktusctl conformance list`
    is where maturity is shown. A vendor's server without a manifest passes the suite and stays
    experimental, read only, and says why; one with a manifest names its digest."""
    bare = start_vendor_connector(server="time")
    declared = start_vendor_connector(
        server="time", manifest=TIME_MANIFEST, scenario=VENDOR / "time-manifest-scenario.json"
    )
    taktusctl = shutil.which("taktusctl")
    assert taktusctl is not None
    env = {
        **os.environ,
        "NO_COLOR": "1",
        "TERM": "dumb",
        "TAKTUS_STATE_DIR": str(tmp_path / "state"),
        "TAKTUS_CONNECTORS": f"time.clock={bare.endpoint},time.zones={declared.endpoint}",
        "TAKTUS_CONFORMANCE_CONNECTOR_TIME_CLOCK_SCENARIO": str(bare.scenario),
        "TAKTUS_CONFORMANCE_CONNECTOR_TIME_ZONES_SCENARIO": str(declared.scenario),
        "TAKTUS_CREDENTIAL_VENDOR_TOKEN": bare.credential_values["VENDOR_TOKEN"],
    }
    added_by_command_line(taktusctl, "idn_test", env)
    recorded = subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl, "conformance", "record", "connector.time.clock", "--identity", "idn_test"],
        capture_output=True, text=True, env=env, check=False,
    )  # fmt: skip
    assert recorded.returncode == 0, recorded.stdout + recorded.stderr
    listed = subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl, "conformance", "list"],
        capture_output=True, text=True, env=env, check=False,
    )  # fmt: skip
    assert listed.returncode == 0, listed.stdout + listed.stderr
    lines = listed.stdout.splitlines()
    bare_at = next(i for i, line in enumerate(lines) if line.startswith("connector.time.clock "))
    assert "experimental" in lines[bare_at] and "serves time.clock" in lines[bare_at]
    block = "\n".join(lines[bare_at : bare_at + 6])
    assert "a vendor's MCP server without a manifest: read only" in block
    assert "without a manifest of its effects, which keeps it experimental" in block
    assert "conformance suite has not been recorded" not in block
    declared_at = next(
        i for i, line in enumerate(lines) if line.startswith("connector.time.zones ")
    )
    assert "a vendor's MCP server, under the manifest sha256:" in lines[declared_at + 1]
    assert any(line.startswith("connector.loopback ") for line in lines)
    for value in bare.credential_values.values():
        assert value not in listed.stdout + listed.stderr
