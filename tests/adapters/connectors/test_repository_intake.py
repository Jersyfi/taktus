"""Intake as a function: recorded deliveries in, intake commands or refusals out.

No endpoint, no network. The payloads under the connector's `payloads/` are real deliveries with
every identifier replaced; the secret is any value, because the test signs with the same one the
connector verifies with. The order the contract fixes — refuse before reading — is what the
unsigned and wrongly signed cases pin down: a body that is not even JSON is refused for its
signature, never for its content.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

import pytest
from mcp import Client

from taktus.adapters.driven.connectors.github import intake
from taktus.adapters.driven.connectors.github.declaration import INTAKE_CREDENTIAL, INTAKE_EVENTS
from taktus.adapters.driven.connectors.github.server import Config, build_server
from taktus.conformance.contracts import first_error

PAYLOADS = (
    Path(__file__).resolve().parents[3] / "src/taktus/adapters/driven/connectors/github/payloads"
)
SHARED = "any-shared-value-0123456789"  # not a secret: the test signs and verifies with it
RECEIVED = "2026-09-16T08:15:02Z"

type Json = dict[str, Any]


def recorded(name: str) -> tuple[dict[str, str], str]:
    headers = json.loads((PAYLOADS / f"{name}.headers.json").read_text())
    body = (PAYLOADS / f"{name}.body.json").read_text()
    return headers, body


def signed(headers: dict[str, str], body: str, shared: str = SHARED) -> dict[str, str]:
    digest = hmac.new(shared.encode(), body.encode(), hashlib.sha256).hexdigest()
    return {**headers, "X-Hub-Signature-256": f"sha256={digest}"}


def test_every_recorded_payload_carries_only_placeholders() -> None:
    for path in PAYLOADS.glob("*.json"):
        text = path.read_text()
        assert "placeholder" in text, path.name
        assert "github.com" not in text, path.name
        assert "ghp_" not in text and "ghs_" not in text, path.name


@pytest.mark.parametrize(
    ("name", "event", "address", "thread"),
    [
        (
            "issue-comment-created",
            "issue_comment.created",
            "placeholder-owner/placeholder-repo#412",
            "3000000001",
        ),
        ("issues-opened", "issues.opened", "placeholder-owner/placeholder-repo#413", None),
        (
            "pull-request-opened",
            "pull_request.opened",
            "placeholder-owner/placeholder-repo#57",
            None,
        ),
        (
            "workflow-run-completed",
            "pipeline_run.completed",
            "placeholder-owner/placeholder-repo#57",
            None,
        ),
    ],
)
def test_a_signed_delivery_becomes_an_intake_command(
    name: str, event: str, address: str, thread: str | None
) -> None:
    headers, body = recorded(name)
    result = intake.normalise(signed(headers, body), body, RECEIVED, SHARED)
    assert first_error("IntakeResult", result, "connector/v1") is None
    accepted = result["accepted"]
    assert accepted["event"] == event
    assert accepted["event"] in INTAKE_EVENTS
    assert accepted["channel"] == "channel.repo"
    assert accepted["sender"] == {"account": "100000001", "kind": "person"}
    assert accepted["reply_to"]["channel"] == "channel.repo"
    assert accepted["reply_to"]["address"] == address
    assert accepted["reply_to"].get("thread") == thread
    assert accepted["event_id"] == f"placeholder-delivery-{name}"
    assert accepted["intent"]["raw"]
    assert "login" not in json.dumps(accepted)  # the account, never the name


def test_the_comment_text_is_the_intent_and_the_issue_the_context() -> None:
    headers, body = recorded("issue-comment-created")
    accepted = intake.normalise(signed(headers, body), body, RECEIVED, SHARED)["accepted"]
    assert accepted["intent"]["raw"] == "@taktus turn this into a pull request at level 3"
    assert accepted["context"] == {
        "repository": "placeholder-owner/placeholder-repo",
        "event": "issue_comment.created",
        "issue": "412",
        "comment": "3000000001",
        "is_pull_request": False,
    }
    assert accepted["occurred_at"] == "2000-01-01T00:00:00Z"


def test_an_unsigned_delivery_is_refused_before_its_body_is_read() -> None:
    headers, body = recorded("issue-comment-created")
    result = intake.normalise(headers, body, RECEIVED, SHARED)
    assert result == {"refused": {"reason": "unsigned", "detail": "no x-hub-signature-256 header"}}
    garbage = intake.normalise(headers, "this is not json {", RECEIVED, SHARED)
    assert garbage["refused"]["reason"] == "unsigned"


def test_a_wrongly_signed_delivery_is_refused_before_its_body_is_read() -> None:
    headers, body = recorded("issue-comment-created")
    wrong = signed(headers, body, "another-value")
    result = intake.normalise(wrong, body, RECEIVED, SHARED)
    assert result["refused"]["reason"] == "bad_signature"
    tampered = intake.normalise(signed(headers, body), body.replace("412", "999"), RECEIVED, SHARED)
    assert tampered["refused"]["reason"] == "bad_signature"
    garbage = intake.normalise(signed(headers, "x"), "this is not json {", RECEIVED, SHARED)
    assert garbage["refused"]["reason"] == "bad_signature"


def test_without_a_secret_nothing_verifies() -> None:
    headers, body = recorded("issue-comment-created")
    result = intake.normalise(signed(headers, body), body, RECEIVED, None)
    assert result["refused"]["reason"] == "bad_signature"
    assert INTAKE_CREDENTIAL in result["refused"]["detail"]


def test_a_ping_is_refused_as_unsupported() -> None:
    headers, body = recorded("ping")
    result = intake.normalise(signed(headers, body), body, RECEIVED, SHARED)
    assert result["refused"]["reason"] == "unsupported_event"


def test_the_connectors_own_comment_is_refused_so_that_it_never_answers_itself() -> None:
    headers, body = recorded("issue-comment-own-action")
    result = intake.normalise(signed(headers, body), body, RECEIVED, SHARED)
    assert result["refused"]["reason"] == "own_action"


def test_a_malformed_delivery_is_refused_cleanly() -> None:
    headers, _ = recorded("issue-comment-created")
    for body in (
        "[]",
        json.dumps({"action": "created"}),
        json.dumps({"action": "created", "issue": {}, "comment": {"body": "x"}}),
    ):
        result = intake.normalise(signed(headers, body), body, RECEIVED, SHARED)
        assert result["refused"]["reason"] == "malformed", body
        assert first_error("IntakeResult", result, "connector/v1") is None
    no_delivery = {k: v for k, v in headers.items() if k != "x-github-delivery"}
    _, body2 = recorded("issue-comment-created")
    result = intake.normalise(signed(no_delivery, body2), body2, RECEIVED, SHARED)
    assert result["refused"]["reason"] == "malformed"


async def test_the_intake_tool_reads_the_secret_at_the_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Through MCP, with the secret in the environment under its declared name, as the
    connector's runtime would put it there."""
    headers, body = recorded("pull-request-opened")
    server = build_server(
        Config(target="http://127.0.0.1:1", repository="placeholder-owner/placeholder-repo")
    )
    async with Client(server) as client:
        monkeypatch.delenv(INTAKE_CREDENTIAL, raising=False)
        result = await client.call_tool(
            "intake", {"headers": signed(headers, body), "body": body, "received_at": RECEIVED}
        )
        assert not result.is_error
        assert isinstance(result.structured_content, dict)
        assert result.structured_content["refused"]["reason"] == "bad_signature"

        monkeypatch.setenv(INTAKE_CREDENTIAL, SHARED)
        result = await client.call_tool(
            "intake", {"headers": signed(headers, body), "body": body, "received_at": RECEIVED}
        )
        assert isinstance(result.structured_content, dict)
        assert result.structured_content["accepted"]["event"] == "pull_request.opened"
        assert SHARED not in json.dumps(result.structured_content)
