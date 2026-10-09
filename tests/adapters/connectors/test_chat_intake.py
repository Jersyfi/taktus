"""The chat connector's intake as a function: recorded deliveries in, intake commands or
refusals out.

No endpoint, no network. The payloads under the connector's `payloads/` are deliveries in the
service's shape with every identifier replaced by a placeholder; the secret is any value, because
the test signs with the same one the connector verifies with. The order the contract fixes —
refuse before reading — is pinned by the unsigned, wrongly signed and stale cases: a body that
is not even JSON is refused for its signature, never for its content.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

import pytest
from mcp import Client

from taktus.adapters.driven.connectors.slack import intake
from taktus.adapters.driven.connectors.slack.declaration import INTAKE_CREDENTIAL, INTAKE_EVENTS
from taktus.adapters.driven.connectors.slack.server import Config, build_server
from taktus.conformance.contracts import first_error

PAYLOADS = (
    Path(__file__).resolve().parents[3] / "src/taktus/adapters/driven/connectors/slack/payloads"
)
SHARED = "any-shared-value-0123456789"  # not a secret: the test signs and verifies with it
RECEIVED = "2026-09-16T08:15:02Z"
MOMENT = 1789546502  # RECEIVED in seconds since the epoch

type Json = dict[str, Any]


def recorded(name: str) -> tuple[dict[str, str], str]:
    headers = json.loads((PAYLOADS / f"{name}.headers.json").read_text())
    body = (PAYLOADS / f"{name}.body.json").read_text()
    return headers, body


def signed(
    headers: dict[str, str], body: str, shared: str = SHARED, moment: int = MOMENT
) -> dict[str, str]:
    base = f"v0:{moment}:{body}".encode()
    digest = hmac.new(shared.encode(), base, hashlib.sha256).hexdigest()
    return {
        **headers,
        "X-Slack-Request-Timestamp": str(moment),
        "X-Slack-Signature": f"v0={digest}",
    }


def test_the_moment_is_the_moment_received() -> None:
    from datetime import datetime

    assert int(datetime.fromisoformat(RECEIVED).timestamp()) == MOMENT


def test_every_recorded_payload_carries_only_placeholders() -> None:
    for path in PAYLOADS.glob("*.json"):
        text = path.read_text()
        assert "placeholder" in text, path.name
        assert "slack.com" not in text, path.name
        assert "xoxb-" not in text and "xoxp-" not in text, path.name


@pytest.mark.parametrize(
    ("name", "event", "address", "thread"),
    [
        ("message-posted", "message.posted", "D0000000001", "1700000000.000200"),
        ("app-mention", "message.mentioned", "C0000000001", "1700000000.000100"),
    ],
)
def test_a_signed_delivery_becomes_an_intake_command(
    name: str, event: str, address: str, thread: str
) -> None:
    headers, body = recorded(name)
    result = intake.normalise(signed(headers, body), body, RECEIVED, SHARED)
    assert first_error("IntakeResult", result, "connector/v1") is None
    accepted = result["accepted"]
    assert accepted["event"] == event and event in INTAKE_EVENTS
    assert accepted["channel"] == "channel.chat"
    assert accepted["sender"] == {"account": "U0000000001", "kind": "person"}
    assert accepted["reply_to"] == {"channel": "channel.chat", "address": address, "thread": thread}
    assert (
        accepted["intent"]["raw"].lower().endswith("turn issue 412 into a pull request at level 3")
    )


def test_a_message_becomes_intent_context_and_moment() -> None:
    headers, body = recorded("message-posted")
    accepted = intake.normalise(signed(headers, body), body, RECEIVED, SHARED)["accepted"]
    assert accepted["event_id"] == "Ev0000000001"
    assert accepted["intent"]["raw"] == "Turn issue 412 into a pull request at level 3"
    assert accepted["context"] == {
        "conversation": "D0000000001",
        "message": "1700000000.000200",
        "event": "message.posted",
    }
    assert accepted["occurred_at"] == "2023-11-14T22:13:20Z"


def test_a_message_in_a_thread_is_answered_in_that_thread() -> None:
    headers, body = recorded("app-mention")
    accepted = intake.normalise(signed(headers, body), body, RECEIVED, SHARED)["accepted"]
    assert accepted["context"]["thread"] == "1700000000.000100"
    assert accepted["reply_to"]["thread"] == "1700000000.000100", "the thread, not the message"


def test_an_unsigned_delivery_is_refused_before_its_body_is_read() -> None:
    headers, body = recorded("message-posted")
    assert intake.normalise(headers, body, RECEIVED, SHARED) == {
        "refused": {"reason": "unsigned", "detail": "no x-slack-signature header"}
    }
    garbage = intake.normalise(headers, "this is not json {", RECEIVED, SHARED)
    assert garbage["refused"]["reason"] == "unsigned"


def test_a_wrongly_signed_delivery_is_refused_before_its_body_is_read() -> None:
    headers, body = recorded("message-posted")
    wrong = intake.normalise(signed(headers, body, "another-value"), body, RECEIVED, SHARED)
    assert wrong["refused"]["reason"] == "bad_signature"
    tampered = intake.normalise(signed(headers, body), body.replace("412", "999"), RECEIVED, SHARED)
    assert tampered["refused"]["reason"] == "bad_signature"
    moved = signed(headers, body)
    moved["X-Slack-Request-Timestamp"] = str(MOMENT + 1)
    assert intake.normalise(moved, body, RECEIVED, SHARED)["refused"]["reason"] == "bad_signature"
    garbage = intake.normalise(signed(headers, "x"), "this is not json {", RECEIVED, SHARED)
    assert garbage["refused"]["reason"] == "bad_signature"


@pytest.mark.parametrize("offset", [-301, 301, -3600])
def test_a_delivery_signed_far_from_its_arrival_is_a_replay(offset: int) -> None:
    headers, body = recorded("message-posted")
    stale = signed(headers, body, moment=MOMENT + offset)
    result = intake.normalise(stale, body, RECEIVED, SHARED)
    assert result["refused"]["reason"] == "bad_signature"
    assert "replay" in result["refused"]["detail"]


@pytest.mark.parametrize("offset", [-300, 0, 300])
def test_a_delivery_signed_within_the_window_is_accepted(offset: int) -> None:
    headers, body = recorded("message-posted")
    result = intake.normalise(signed(headers, body, moment=MOMENT + offset), body, RECEIVED, SHARED)
    assert "accepted" in result, result


def test_without_a_secret_or_a_moment_nothing_verifies() -> None:
    headers, body = recorded("message-posted")
    result = intake.normalise(signed(headers, body), body, RECEIVED, None)
    assert result["refused"]["reason"] == "bad_signature"
    assert INTAKE_CREDENTIAL in result["refused"]["detail"]
    no_moment = {k: v for k, v in signed(headers, body).items() if "Timestamp" not in k}
    assert intake.normalise(no_moment, body, RECEIVED, SHARED)["refused"]["reason"] == (
        "bad_signature"
    )


@pytest.mark.parametrize("name", ["url-verification", "message-changed"])
def test_what_is_not_a_new_message_is_refused_as_unsupported(name: str) -> None:
    headers, body = recorded(name)
    result = intake.normalise(signed(headers, body), body, RECEIVED, SHARED)
    assert result["refused"]["reason"] == "unsupported_event"


def test_the_connectors_own_message_is_refused_so_that_it_never_answers_itself() -> None:
    headers, body = recorded("message-own-action")
    result = intake.normalise(signed(headers, body), body, RECEIVED, SHARED)
    assert result["refused"]["reason"] == "own_action"
    marked = json.loads(recorded("message-posted")[1])
    marked["event"]["metadata"] = {
        "event_type": "taktus_delivery",
        "event_payload": {"idempotency_key": "taktus:run:step:1"},
    }
    text = json.dumps(marked)
    result = intake.normalise(signed(headers, text), text, RECEIVED, SHARED)
    assert result["refused"]["reason"] == "own_action", "the mark alone is enough"


def test_a_malformed_delivery_is_refused_cleanly() -> None:
    headers, _ = recorded("message-posted")
    for body in (
        "[]",
        json.dumps({"type": "event_callback", "event_id": "Ev1"}),
        json.dumps({"type": "event_callback", "event": {"type": "message", "ts": "1.2"}}),
        json.dumps(
            {"type": "event_callback", "event_id": "Ev1", "event": {"type": "message", "ts": "1"}}
        ),
    ):
        result = intake.normalise(signed(headers, body), body, RECEIVED, SHARED)
        assert result["refused"]["reason"] == "malformed", body
        assert first_error("IntakeResult", result, "connector/v1") is None


async def test_the_intake_tool_reads_the_secret_from_its_file_at_the_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Through MCP, with the secret in the file its variable names, as the connector's runtime
    puts every secret."""
    headers, body = recorded("message-posted")
    server = build_server(Config(target="http://127.0.0.1:1"))
    variable = f"TAKTUS_CREDENTIAL_{INTAKE_CREDENTIAL}_FILE"
    secret = tmp_path / "signing-secret"
    async with Client(server) as client:
        monkeypatch.delenv(INTAKE_CREDENTIAL, raising=False)
        monkeypatch.delenv(variable, raising=False)
        arguments = {"headers": signed(headers, body), "body": body, "received_at": RECEIVED}
        result = await client.call_tool("intake", arguments)
        assert not result.is_error
        assert isinstance(result.structured_content, dict)
        assert result.structured_content["refused"]["reason"] == "bad_signature"

        secret.write_text(SHARED + "\n", encoding="utf-8")
        monkeypatch.setenv(variable, str(secret))
        result = await client.call_tool("intake", arguments)
        assert isinstance(result.structured_content, dict)
        assert result.structured_content["accepted"]["event"] == "message.posted"
        assert SHARED not in json.dumps(result.structured_content)
