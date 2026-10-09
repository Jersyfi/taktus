"""Intake: a signed event delivery becomes an intake command, or is refused.

A function from the delivery — headers, raw body, the moment it arrived — and the intake secret
to an `IntakeResult` (`Connector.json#/$defs/IntakeResult`). The transport that received the
delivery is not here; the MCP tool in `server.py` and the tests call this directly.

The order is the contract's: the signature is verified before the body is read, so that nothing
unsigned or wrongly signed is ever parsed. The scheme is `hmac-sha256-timestamped`: the service
signs `v0:<moment>:<raw body>` with the signing secret and sends the moment in a header of its
own. A moment more than `WINDOW` seconds from when the delivery arrived is refused as
`bad_signature`: a delivery captured on the way cannot be replayed later.

Then the event is normalised as far as the channel can: who wrote, as the service names them —
the account identifier, never a name — what they wrote, in which conversation, and where the
reply goes: into the thread of the message, so that a reply never lands outside the
conversation it answers. A message the connector itself posted carries its mark, or comes from
the very app the delivery is addressed to, and is refused, so that a reply is never answered.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from taktus.adapters.driven.connectors.slack.declaration import CHANNEL, INTAKE_CREDENTIAL
from taktus.adapters.driven.connectors.slack.operations import mark_of

type Json = dict[str, Any]

SIGNATURE_HEADER = "x-slack-signature"
TIMESTAMP_HEADER = "x-slack-request-timestamp"
VERSION = "v0"
WINDOW = 300
"""Seconds a delivery's moment of sending may lie from the moment it arrived."""

# The service's event type -> the event kind the declaration lists. A `message` with a subtype
# — an edit, a deletion, a join — is not a new message and is not normalised.
EVENTS: Mapping[str, str] = {"message": "message.posted", "app_mention": "message.mentioned"}


class Malformed(Exception):
    """The body is not a delivery this connector can read."""


def refused(reason: str, detail: str) -> Json:
    return {"refused": {"reason": reason, "detail": detail}}


def signature_of(body: bytes, moment: str, secret: str) -> str:
    base = f"{VERSION}:{moment}:".encode() + body
    return f"{VERSION}=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()


def verify(
    headers: Mapping[str, str],
    body: bytes,
    secret: str | None,
    received_at: datetime,
    window: int | None = WINDOW,
) -> Json | None:
    """None when the delivery is signed with the secret at a moment close to its arrival;
    otherwise the refusal. `window` None checks no moment — for the fault that shows the suite
    catches exactly that."""
    given = headers.get(SIGNATURE_HEADER, "")
    if not given:
        return refused("unsigned", f"no {SIGNATURE_HEADER} header")
    if not secret:
        return refused(
            "bad_signature",
            f"no intake secret is available under {INTAKE_CREDENTIAL}; nothing can be verified",
        )
    moment = headers.get(TIMESTAMP_HEADER, "").strip()
    if not moment.isdigit():
        return refused("bad_signature", f"no moment of sending in {TIMESTAMP_HEADER}")
    if window is not None and abs(received_at.timestamp() - int(moment)) > window:
        return refused(
            "bad_signature",
            f"signed {int(received_at.timestamp()) - int(moment)} s before it arrived; more "
            f"than {window} s is a replay",
        )
    if not hmac.compare_digest(given.strip(), signature_of(body, moment, secret)):
        return refused("bad_signature", f"{SIGNATURE_HEADER} does not verify against the secret")
    return None


def normalise(
    headers: Mapping[str, str],
    body: str,
    received_at: str,
    secret: str | None,
    *,
    window: int | None = WINDOW,
) -> Json:
    """The whole of intake: verify, read, refuse or accept."""
    lowered = {name.lower(): value for name, value in headers.items()}
    raw = body.encode("utf-8")
    try:
        arrived = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
    except ValueError:
        return refused("malformed", "received_at is not a moment")
    if arrived.tzinfo is None:
        arrived = arrived.replace(tzinfo=UTC)
    refusal = verify(lowered, raw, secret, arrived, window)
    if refusal is not None:
        return refusal
    try:
        payload = json.loads(raw)
    except ValueError as error:
        return refused("malformed", f"the body is not JSON: {error}")
    if not isinstance(payload, dict):
        return refused("malformed", "the body is not an object")
    if payload.get("type") != "event_callback":
        return refused(
            "unsupported_event",
            f"a delivery of type {payload.get('type')!r} is not an event this connector normalises",
        )
    try:
        return _event(payload, received_at)
    except Malformed as error:
        return refused("malformed", str(error))


def _event(payload: Json, received_at: str) -> Json:
    event = payload.get("event")
    if not isinstance(event, dict):
        raise Malformed("the delivery has no event")
    event_id = payload.get("event_id")
    if not isinstance(event_id, str) or not event_id:
        raise Malformed("the delivery has no event_id")
    kind = EVENTS.get(str(event.get("type", "")))
    if kind is None:
        return refused(
            "unsupported_event", f"an event of type {event.get('type')!r} is not normalised"
        )
    if mark_of(event) is not None or (
        event.get("app_id") and event.get("app_id") == payload.get("api_app_id")
    ):
        return refused("own_action", "the message was posted by this connector's own app")
    if event.get("subtype"):
        return refused(
            "unsupported_event", f"a message of subtype {event['subtype']!r} is not normalised"
        )
    conversation = event.get("channel")
    ts = event.get("ts")
    if not isinstance(conversation, str) or not conversation:
        raise Malformed("the event has no channel")
    if not isinstance(ts, str) or not ts:
        raise Malformed("the event has no ts")
    account = event.get("user") or event.get("bot_id")
    if not isinstance(account, str) or not account:
        raise Malformed("the event has no user")
    thread = event.get("thread_ts")
    context: Json = {"conversation": conversation, "message": ts, "event": kind}
    if isinstance(thread, str) and thread:
        context["thread"] = thread
    return {
        "accepted": {
            "event_id": event_id,
            "event": kind,
            "channel": CHANNEL,
            "sender": {
                "account": account,
                "kind": "automation" if event.get("bot_id") else "person",
            },
            "intent": {"raw": str(event.get("text") or "")},
            "context": context,
            "reply_to": {
                "channel": CHANNEL,
                "address": conversation,
                "thread": thread if isinstance(thread, str) and thread else ts,
            },
            "occurred_at": _moment(ts, received_at),
        }
    }


def _moment(ts: str, fallback: str) -> str:
    """A message's timestamp — seconds since the epoch, a dot, a sequence — as a moment."""
    try:
        seconds = int(ts.split(".", 1)[0])
    except ValueError:
        return fallback
    return datetime.fromtimestamp(seconds, UTC).isoformat().replace("+00:00", "Z")
