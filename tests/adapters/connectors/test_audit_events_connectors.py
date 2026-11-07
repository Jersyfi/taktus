"""The two audit connectors read privileged actions in one shape — when, which action, by which
account, on what, and whether it grants rights — and count per action, never per actor
(ADR-0209, UC-03 B-5.04, principle 14).

Against the fakes under `tests/fakes/audit_log_service.py` (an organisation's audit log) and
`tests/fakes/workspace_reports_service.py` (a workspace's activity reports and its token
endpoint), each in a thread of this process. The connectors are served in-process over MCP.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fakes import audit_log_service, workspace_reports_service
from fakes.ports import free_port
from taktus_connectors.githubaudit.operations import Config as LogConfig
from taktus_connectors.githubaudit.server import build_server as log_server
from taktus_connectors.googleworkspace.operations import Config as ReportsConfig
from taktus_connectors.googleworkspace.server import build_server as reports_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "tok-" + secrets.token_hex(8)
ACCOUNT = f"audit-{secrets.token_hex(4)}@project.iam.example"
CREDENTIAL = "AUDIT_TOKEN"


def service_account_key(email: str) -> str:
    """A service account's key file, as the service hands one out: compact JSON."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return json.dumps(
        {"type": "service_account", "client_email": email, "private_key": pem},
        separators=(",", ":"),
    )


KEY = service_account_key(ACCOUNT)


def _credential(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    path = tmp_path / "audit"
    path.write_text(value, encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(path))


def _serving(server: Any) -> Iterator[str]:
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def audit_log() -> Iterator[str]:
    yield from _serving(audit_log_service.make_server("127.0.0.1", 0, {TOKEN}))


@pytest.fixture
def reports() -> Iterator[str]:
    yield from _serving(workspace_reports_service.make_server("127.0.0.1", 0, {ACCOUNT}))


def replace(url: str, records: list[dict[str, Any]]) -> None:
    httpx.post(url, content=json.dumps(records), timeout=5.0).raise_for_status()


def fake_state(url: str) -> dict[str, Any]:
    found: dict[str, Any] = httpx.get(f"{url}/_fake/state", timeout=5.0).json()
    return found


def context() -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_ops",
        run_id="run_read",
        step_id="read",
        attempt=1,
        idempotency_key=idempotency_key("run_read", "read", 1),
        credentials=(CredentialReference(name=CREDENTIAL, injected_as="env"),),
    )


def of_the_log(url: str, organization: str = "example") -> McpActionConnector:
    return McpActionConnector(log_server(LogConfig(url, organization, timeout=5.0)))


def of_the_reports(url: str) -> McpActionConnector:
    config = ReportsConfig(url, "admin@org.example", f"{url}/token", timeout=5.0)
    return McpActionConnector(reports_server(config))


# --- an organisation's audit log -------------------------------------------------------------


async def test_the_audit_log_is_read_in_the_capability_s_shape(
    audit_log: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _credential(tmp_path, monkeypatch, TOKEN)
    result = await of_the_log(audit_log).call("audit.events.list", context(), {})
    assert result.effect.kind.value == "read"
    events = result.output["events"]
    assert [e["action"] for e in events] == [
        "org.add_billing_manager", "repo.create", "repo.create", "repo.create", "team.add_member",
    ]  # fmt: skip
    first = events[0]
    assert set(first) == {"id", "at", "hour", "action", "actor", "target", "escalation"}
    assert first["id"] == "doc-1" and first["target"] == "new-billing"
    assert first["escalation"] is True and events[1]["escalation"] is False
    assert 0 <= first["hour"] <= 23 and first["at"].endswith("Z")
    assert result.output["actions"][0] == {"action": "repo.create", "count": 3}
    assert result.output["complete"] is True
    assert "Germany" not in json.dumps(result.output), "the actor's location is never copied"
    assert all(set(a) == {"action", "count"} for a in result.output["actions"]), "never per actor"


async def test_the_audit_log_is_read_since_the_hours_asked_and_page_by_page(
    audit_log: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _credential(tmp_path, monkeypatch, TOKEN)
    events = [audit_log_service.audit_event(n, "repo.create", n) for n in range(1, 251)]
    events.append(audit_log_service.audit_event(999, "org.add_member", 60 * 30))
    replace(f"{audit_log}/_fake/events", events)
    result = await of_the_log(audit_log).call("audit.events.list", context(), {"hours": 24})
    assert len({e["id"] for e in result.output["events"]}) == 250, "the event 30 hours ago is out"
    assert result.consumption.quota_units == 3, "three pages of at most 100"
    bounded = await of_the_log(audit_log).call("audit.events.list", context(), {"limit": 120})
    assert len(bounded.output["events"]) == 120 and bounded.output["complete"] is False


@pytest.mark.parametrize("input", [{"hours": 0}, {"hours": 5000}, {"limit": True}])
async def test_a_period_the_log_cannot_answer_is_invalid(
    audit_log: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, input: dict[str, Any]
) -> None:
    _credential(tmp_path, monkeypatch, TOKEN)
    with pytest.raises(CallFailed) as failed:
        await of_the_log(audit_log).call("audit.events.list", context(), input)
    assert failed.value.error.cause.value == "invalid"


async def test_an_organisation_without_an_audit_log_is_invalid_and_a_wrong_token_unauthenticated(
    audit_log: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _credential(tmp_path, monkeypatch, TOKEN)
    with pytest.raises(CallFailed) as failed:
        await of_the_log(audit_log, "missing").call("audit.events.list", context(), {})
    assert failed.value.error.cause.value == "invalid"
    assert "refused by the fake" not in (failed.value.error.detail or "")
    _credential(tmp_path, monkeypatch, "not-the-token")
    with pytest.raises(CallFailed) as failed:
        await of_the_log(audit_log).call("audit.events.list", context(), {})
    assert failed.value.error.cause.value == "unauthenticated"


# --- a workspace's activity reports ----------------------------------------------------------


async def test_the_reports_are_read_with_a_signed_assertion_in_the_capability_s_shape(
    reports: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _credential(tmp_path, monkeypatch, KEY)
    result = await of_the_reports(reports).call("audit.events.list", context(), {})
    events = result.output["events"]
    assert [e["action"] for e in events] == [
        "ASSIGN_ROLE", "CREATE_GROUP", "CHANGE_GROUP_SETTING",
    ]  # fmt: skip
    assert events[0]["escalation"] is True and events[1]["escalation"] is False
    assert events[0]["target"] == "someone@org.example"
    assert events[0]["actor"] == "admin@org.example"
    assert set(events[0]) == {"id", "at", "hour", "action", "actor", "target", "escalation"}
    assert result.consumption.quota_units == 2, "the token and one page"
    text = json.dumps(result.output)
    assert "203.0.113" not in text, "the IP address is never copied"
    assert "PRIVATE KEY" not in text and "ya29" not in text
    state = fake_state(reports)
    assert state["seen_accounts"] == [ACCOUNT]


async def test_the_reports_are_read_since_the_hours_asked_and_page_by_page(
    reports: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _credential(tmp_path, monkeypatch, KEY)
    activity = workspace_reports_service.activity
    items = [activity(n, "GROUP_SETTINGS", "CREATE_GROUP", n / 10) for n in range(1, 1501)]
    items.append(activity(9999, "GROUP_SETTINGS", "CREATE_GROUP", 60 * 48))
    replace(f"{reports}/_fake/activities", items)
    result = await of_the_reports(reports).call(
        "audit.events.list", context(), {"hours": 24, "limit": 5000}
    )
    assert len(result.output["events"]) == 1500 and result.output["complete"] is True
    assert result.output["actions"] == [{"action": "CREATE_GROUP", "count": 1500}]


async def test_a_credential_that_is_not_a_key_file_or_a_stranger_s_key_is_unauthenticated(
    reports: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for value in ("tok-not-a-key", service_account_key("stranger@project.iam.example")):
        _credential(tmp_path, monkeypatch, value)
        with pytest.raises(CallFailed) as failed:
            await of_the_reports(reports).call("audit.events.list", context(), {})
        assert failed.value.error.cause.value == "unauthenticated"
        assert "PRIVATE KEY" not in (failed.value.error.detail or "")


async def test_an_application_outside_the_list_is_invalid(
    reports: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _credential(tmp_path, monkeypatch, KEY)
    with pytest.raises(CallFailed) as failed:
        await of_the_reports(reports).call(
            "audit.events.list", context(), {"application": "everything"}
        )
    assert failed.value.error.cause.value == "invalid"


@pytest.mark.parametrize("which", ["log", "reports"])
async def test_a_service_that_does_not_answer_is_unavailable_and_retryable(
    which: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = f"http://127.0.0.1:{free_port()}"
    _credential(tmp_path, monkeypatch, TOKEN if which == "log" else KEY)
    connector = of_the_log(url) if which == "log" else of_the_reports(url)
    started = time.monotonic()
    with pytest.raises(CallFailed) as failed:
        await connector.call("audit.events.list", context(), {})
    assert failed.value.error.cause.value == "unavailable"
    assert failed.value.error.retryable is True
    assert time.monotonic() - started < 10
