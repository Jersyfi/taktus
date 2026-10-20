"""The vendor connector: a vendor's MCP server behind the connector contract (ADR-0117, #410).

In-process, over MCP, as an instance reaches a connector: the vendor's server is the MCP
project's reference time server (`mcp-server-time`) or the stand-in with tools that write
(`tests/fakes/vendor_notes_server.py`), and the connector in front of it is reached through the
core's own port (`McpActionConnector`). The conformance suite runs against both as processes in
`tests/conformance/test_connector_v1_vendor.py`; here are the rules it cannot see.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any

import pytest
from fakes.vendor_notes_server import State
from fakes.vendor_notes_server import create_server as notes_server
from mcp_server_time.server import create_server as time_server
from pydantic import ValidationError

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.serving import Call, TargetError
from taktus.adapters.driven.connectors.vendor.manifest import (
    Manifest,
    ManifestError,
    load,
)
from taktus.adapters.driven.connectors.vendor.server import build_server, prepare
from taktus.adapters.driven.connectors.vendor.upstream import Upstream, VendorTool
from taktus.adapters.driven.connectors.vendor.wrapping import (
    PlanError,
    Wrapper,
    operation_segment,
    with_manifest,
    without_manifest,
)
from taktus.ports.connector import CallContext, CallFailed, Capabilities, idempotency_key
from taktus.ports.worker import CredentialReference

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "contracts" / "connector" / "v1" / "examples" / "manifest"
NOTES_MANIFEST = ROOT / "tests" / "conformance" / "vendor" / "notes-manifest.json"
TOKEN = "vtk-" + secrets.token_hex(8)


@pytest.fixture(autouse=True)
def credential(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "vendor_token"
    path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_VENDOR_TOKEN_FILE", str(path))


def context(step: str = "act", attempt: int = 1) -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_vendor",
        run_id="run_vendor",
        step_id=step,
        attempt=attempt,
        idempotency_key=idempotency_key("run_vendor", step, attempt),
        credentials=(CredentialReference(name="VENDOR_TOKEN", injected_as="env"),),
        autonomy_level=1,
    )


def manifest_file(tmp_path: Path, document: dict[str, Any]) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def notes_manifest() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(NOTES_MANIFEST.read_text(encoding="utf-8"))
    return document


# --- the manifest's binding --------------------------------------------------------------------


@pytest.mark.parametrize(
    "path", sorted(EXAMPLES.glob("*/*.json")), ids=lambda p: f"{p.parent.name}/{p.name}"
)
def test_the_manifest_binding_reads_the_contracts_examples(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    if path.parent.name == "valid":
        assert Manifest.model_validate(document).document() == document
    else:
        with pytest.raises(ValidationError):
            Manifest.model_validate(document)


def test_a_manifest_names_each_operation_by_a_declared_capability(tmp_path: Path) -> None:
    document = notes_manifest()
    document["operations"][0]["capability"] = "notes.other"
    document["operations"][0]["name"] = "notes.other.list"
    with pytest.raises(ManifestError, match="undeclared capability"):
        load(manifest_file(tmp_path, document))
    document = notes_manifest()
    document["operations"][1]["tool"] = document["operations"][0]["tool"]
    with pytest.raises(ManifestError, match="a tool is declared twice"):
        load(manifest_file(tmp_path, document))


def test_the_digest_is_of_the_bytes(tmp_path: Path) -> None:
    path = manifest_file(tmp_path, notes_manifest())
    _, first = load(path)
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    _, second = load(path)
    assert first != second and first.startswith("sha256:")


# --- without a manifest: read only -------------------------------------------------------------


def tool(name: str, read_only: bool | None, destructive: bool | None = None) -> VendorTool:
    return VendorTool(name, None, read_only, destructive)


def test_without_a_manifest_only_the_tools_marked_as_reading_are_served() -> None:
    plan = without_manifest(
        [
            tool("get_note", True),
            tool("search", None),
            tool("create_note", False),
            tool("wipe", True, destructive=True),
        ],
        "notes.pages",
    )
    assert [op.name for op in plan.operations] == ["notes.pages.get_note"]
    assert {op.effect for op in plan.operations} == {"read"}
    assert {w.tool for w in plan.withheld} == {"search", "create_note", "wipe"}
    declaration = plan.declaration()
    assert declaration["wrapped"] == {}
    Capabilities.model_validate(declaration)


def test_without_a_manifest_two_tools_that_give_one_name_are_both_withheld() -> None:
    plan = without_manifest(
        [tool("Get-Note", True), tool("get-note", True), tool("list", True)], "notes.pages"
    )
    assert [op.name for op in plan.operations] == ["notes.pages.list"]
    assert {w.tool for w in plan.withheld} == {"Get-Note", "get-note"}


def test_without_a_manifest_and_without_a_reading_tool_nothing_starts() -> None:
    with pytest.raises(PlanError, match="nothing to serve"):
        without_manifest([tool("create_note", False)], "notes.pages")


def test_a_tool_name_becomes_an_operation_segment() -> None:
    assert operation_segment("get_current_time") == "get_current_time"
    assert operation_segment("Repo.Search") == "repo_search"
    assert operation_segment("2fa-check") == "t2fa-check"


def test_the_core_refuses_a_write_from_a_server_without_a_manifest() -> None:
    """Defence in depth: whatever a connector serves, the port does not believe a write from a
    vendor's server that no manifest declares."""
    declaration = without_manifest([tool("get_note", True)], "notes.pages").declaration()
    declaration["operations"][0]["effect"] = "write"
    declaration["operations"][0]["idempotency"] = "none"
    with pytest.raises(ValidationError, match="declares only reads"):
        Capabilities.model_validate(declaration)


async def test_the_reference_time_server_is_served_read_only_through_the_port() -> None:
    upstream = Upstream(time_server("UTC"), timeout=10.0)
    plan = await prepare(upstream, capability="time.clock")
    connector = McpActionConnector(build_server(Wrapper(upstream, plan)), timeout=10.0)
    declaration = await connector.capabilities()
    assert declaration.wrapped is not None and declaration.wrapped.manifest is None
    names = {op.name for op in declaration.operations}
    assert names == {"time.clock.get_current_time", "time.clock.convert_time"}
    result = await connector.call(
        "time.clock.get_current_time", context(), {"timezone": "Europe/Berlin"}
    )
    assert result.effect.kind.value == "read"
    assert result.output["timezone"] == "Europe/Berlin"
    with pytest.raises(CallFailed) as failed:
        await connector.call("time.clock.get_current_time", context(), {"timezone": "Mars/Base"})
    assert failed.value.error.cause.value == "invalid"


# --- with a manifest ---------------------------------------------------------------------------


async def test_a_manifest_write_reaches_the_vendor_once_per_key(tmp_path: Path) -> None:
    state = State()
    upstream = Upstream(notes_server(state), timeout=10.0)
    plan = await prepare(upstream, manifest=manifest_file(tmp_path, notes_manifest()))
    connector = McpActionConnector(build_server(Wrapper(upstream, plan)), timeout=10.0)
    declaration = await connector.capabilities()
    assert declaration.wrapped is not None and declaration.wrapped.manifest is not None
    create = declaration.operation("notes.pages.create")
    assert create is not None and create.outward and create.repeatable
    archive = declaration.operation("notes.pages.archive")
    assert archive is not None and archive.outward and not archive.repeatable
    first = await connector.call("notes.pages.create", context(), {"title": "a", "body": "b"})
    again = await connector.call("notes.pages.create", context(), {"title": "a", "body": "b"})
    other = await connector.call(
        "notes.pages.create", context("act", 2), {"title": "a", "body": "b"}
    )
    assert first.effect.replayed is False and again.effect.replayed is True
    assert first.effect.records == again.effect.records != other.effect.records
    assert first.effect.records[0].url == "https://notes.example/n/n1"
    assert state.calls["create_note"] == 3 and len(state.notes) == 2
    archived = await connector.call("notes.pages.archive", context("archive"), {"id": "n1"})
    assert archived.effect.kind.value == "write" and archived.effect.replayed is False


async def test_the_caller_cannot_name_the_key_argument(tmp_path: Path) -> None:
    state = State()
    upstream = Upstream(notes_server(state), timeout=10.0)
    plan = await prepare(upstream, manifest=manifest_file(tmp_path, notes_manifest()))
    connector = McpActionConnector(build_server(Wrapper(upstream, plan)), timeout=10.0)
    with pytest.raises(CallFailed) as failed:
        await connector.call(
            "notes.pages.create", context(), {"title": "a", "body": "b", "request_id": "mine"}
        )
    assert failed.value.error.cause.value == "invalid"
    assert state.calls["create_note"] == 0


async def test_a_manifest_that_calls_a_destructive_tool_a_read_refuses_the_start(
    tmp_path: Path,
) -> None:
    document = notes_manifest()
    document["operations"][0]["tool"] = "delete_note"
    upstream = Upstream(notes_server(State()), timeout=10.0)
    with pytest.raises(PlanError, match="declared a read"):
        await prepare(upstream, manifest=manifest_file(tmp_path, document))
    document = notes_manifest()
    document["operations"][0]["tool"] = "no_such_tool"
    with pytest.raises(PlanError, match="does not list the tool"):
        await prepare(upstream, manifest=manifest_file(tmp_path, document))


async def test_a_contradiction_found_at_the_call_is_refused_before_the_tool(
    tmp_path: Path,
) -> None:
    """Where the listing was not read at the start, each call checks it: a tool declared a read
    that its vendor marks as destroying is refused as `unexpected` and not called."""
    document = notes_manifest()
    document["operations"][0]["tool"] = "delete_note"
    manifest, digest = load(manifest_file(tmp_path, document))
    state = State()
    upstream = Upstream(notes_server(state), timeout=10.0)
    connector = McpActionConnector(
        build_server(Wrapper(upstream, with_manifest(manifest, digest, None))), timeout=10.0
    )
    with pytest.raises(CallFailed) as failed:
        await connector.call("notes.pages.list", context(), {"id": "n1"})
    assert failed.value.error.cause.value == "unexpected"
    assert failed.value.error.effect == "none"
    assert "delete_note" not in state.calls


async def test_an_answer_that_names_no_record_is_an_unknown_effect(tmp_path: Path) -> None:
    """The vendor acted, or may have, and the record cannot be named: the effect is unknown,
    and the call may be repeated only because the vendor recognises a repeat."""
    document = notes_manifest()
    document["operations"][2]["record"]["id"] = "/nothing/here"
    manifest, digest = load(manifest_file(tmp_path, document))
    upstream = Upstream(notes_server(State()), timeout=10.0)
    wrapper = Wrapper(upstream, with_manifest(manifest, digest, None))
    planned = next(op for op in wrapper.plan.operations if op.name == "notes.pages.create")
    with pytest.raises(TargetError) as failed:
        await wrapper.invoke(planned, Call(token=TOKEN, key="k" * 20), {"title": "a", "body": "b"})
    assert (failed.value.cause, failed.value.effect, failed.value.retryable) == (
        "unknown",
        "unknown",
        True,
    )
