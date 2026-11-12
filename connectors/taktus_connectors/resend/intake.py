"""Intake: the service's webhook for a message received becomes an intake command, or is
refused.

The service sends an event for every message its domain receives, `email.received`, signed
under the open specification of signed webhooks (ADR-0186), the scheme
`hmac-sha256-identified`. The headers are the specification's under the names the service's
signing library uses: `svix-id` the delivery's identifier, `svix-timestamp` the moment of
sending in whole seconds since the epoch, `svix-signature` one or more entries
`v1,<base64 digest>`. The digest is the HMAC-SHA256 of `<identifier>.<moment>.<raw body>`, keyed
with the bytes the secret encodes in base64 after its prefix `whsec_`. The signature is
verified before the body is read; a moment more than 300 seconds from the arrival is refused.

**De-duplicated by the message.** The event's identifier is the service's identifier of the
message, `data.email_id`: a redelivery of the event, and a second event for the same message,
carry the same one, and the intake keeps one event (`components/command`, ADR-0048 §4). The
context's `message` is that identifier too, which `mail.messages.read` reads.

Then the message is normalised as far as the event carries it. The sender is the digest of the
address it came from, `sha256:` and 64 hexadecimal digits, never a name. **The event carries
no text and no headers**: what they wrote is the subject alone, and the message's text is read
by `mail.messages.read`. For the same reason the intake cannot see an automatic message; the
reply refuses to answer one (`messages.py`). The reply goes to the sender's address, in the
thread of the message. Refused:

- a message from the connector's own sender address, as `own_action`;
- an event of another type, as `unsupported_event`;
- an event without a message identifier or a sender address, as `malformed`.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from taktus_connectors.resend.declaration import CHANNEL
from taktus_connectors.resend.messages import addresses, moment

type Json = dict[str, Any]

ID_HEADER = "svix-id"
TIMESTAMP_HEADER = "svix-timestamp"
SIGNATURE_HEADER = "svix-signature"
VERSION = "v1"
SECRET_PREFIX = "whsec_"  # noqa: S105 — a prefix of the specification, no secret
WINDOW = 300
"""Seconds a delivery's moment of sending may lie from the moment it arrived."""
RECEIVED = "email.received"
EVENT = "message.posted"


def refused(reason: str, detail: str) -> Json:
    return {"refused": {"reason": reason, "detail": detail}}


def key_of(secret: str) -> bytes | None:
    """The key the secret encodes in base64, after `whsec_`; None when it is no base64."""
    try:
        return base64.b64decode(secret.strip().removeprefix(SECRET_PREFIX), validate=True)
    except (binascii.Error, ValueError):
        return None


def signature_of(delivery: str, sent: str, body: bytes, key: bytes) -> str:
    base = f"{delivery}.{sent}.".encode() + body
    return base64.b64encode(hmac.new(key, base, hashlib.sha256).digest()).decode()


def signed(body: str, secret: str, delivery: str, sent: int) -> dict[str, str]:
    """The headers the service writes for `body`: what the faults and the tests sign with."""
    key = key_of(secret) or secret.encode()
    digest = signature_of(delivery, str(sent), body.encode(), key)
    return {
        ID_HEADER: delivery,
        TIMESTAMP_HEADER: str(sent),
        SIGNATURE_HEADER: f"{VERSION},{digest}",
    }


def arrival(received_at: str) -> float:
    """`received_at` in seconds since the epoch; 0 where it is not a moment."""
    try:
        found = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    return (found if found.tzinfo else found.replace(tzinfo=UTC)).timestamp()


def account_of(address: str) -> str:
    return "sha256:" + hashlib.sha256(address.strip().lower().encode()).hexdigest()


def verify(
    headers: Mapping[str, str],
    body: bytes,
    secret: str | None,
    arrived: datetime,
    window: int | None = WINDOW,
) -> Json | None:
    """None when the delivery is signed with the secret over its own identifier and moment,
    close to its arrival; otherwise the refusal. `window` None checks no moment — for the fault
    that shows the suite catches exactly that."""
    given = headers.get(SIGNATURE_HEADER, "").strip()
    if not given:
        return refused("unsigned", f"no {SIGNATURE_HEADER} header")
    if not secret:
        return refused("bad_signature", "no intake secret is available; nothing can be verified")
    key = key_of(secret)
    if key is None:
        return refused("bad_signature", "the intake secret is not base64; nothing can be verified")
    delivery = headers.get(ID_HEADER, "").strip()
    if not delivery:
        return refused("bad_signature", f"no delivery identifier in {ID_HEADER}")
    sent = headers.get(TIMESTAMP_HEADER, "").strip()
    if not sent.isdigit():
        return refused("bad_signature", f"no moment of sending in {TIMESTAMP_HEADER}")
    if window is not None and abs(arrived.timestamp() - int(sent)) > window:
        return refused(
            "bad_signature",
            f"signed {int(arrived.timestamp()) - int(sent)} s before it arrived; more than "
            f"{window} s is a replay",
        )
    expected = signature_of(delivery, sent, body, key)
    for entry in given.split():
        version, _, digest = entry.partition(",")
        if version == VERSION and hmac.compare_digest(digest, expected):
            return None
    return refused("bad_signature", f"no entry of {SIGNATURE_HEADER} verifies against the secret")


def receiver(sender: str, window: int | None = WINDOW) -> Callable[..., Json]:
    """The intake of a connector that sends from `sender`."""
    own = sender.strip().lower()

    def normalise(
        headers: Mapping[str, str], body: str, received_at: str, secret: str | None
    ) -> Json:
        """The whole of intake: verify, read, refuse or accept."""
        lowered = {name.lower(): value for name, value in headers.items()}
        try:
            arrived = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
        except ValueError:
            return refused("malformed", "received_at is not a moment")
        if arrived.tzinfo is None:
            arrived = arrived.replace(tzinfo=UTC)
        refusal = verify(lowered, body.encode("utf-8"), secret, arrived, window)
        if refusal is not None:
            return refusal
        return _event(body, received_at, own)

    return normalise


def _event(body: str, received_at: str, own: str) -> Json:
    try:
        payload = json.loads(body)
    except ValueError:
        return refused("malformed", "the body is not JSON")
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        return refused("malformed", "the body is not an event with data")
    kind = payload.get("type")
    if kind != RECEIVED:
        return refused("unsupported_event", f"an event of type {kind!r} is not a message received")
    data = payload["data"]
    mid = data.get("email_id")
    if not isinstance(mid, str) or not mid:
        return refused("malformed", "the event names no message")
    senders = addresses(data.get("from"))
    if not senders:
        return refused("malformed", "the message names no sender address")
    if senders[0].lower() == own:
        return refused("own_action", "the message was sent from this connector's address")
    subject = str(data.get("subject") or "").strip()
    return {
        "accepted": {
            "event_id": mid,
            "event": EVENT,
            "channel": CHANNEL,
            "sender": {"account": account_of(senders[0]), "kind": "person"},
            "intent": {"raw": subject},
            "context": {"conversation": "inbox", "message": mid},
            "reply_to": {"channel": CHANNEL, "address": senders[0], "thread": mid},
            "occurred_at": moment(data.get("created_at"))
            or moment(payload.get("created_at"))
            or received_at,
        }
    }
