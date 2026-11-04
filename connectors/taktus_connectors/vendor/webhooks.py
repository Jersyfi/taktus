"""Intake under the open specification of signed webhooks (ADR-0186, contract §7).

A vendor that serves its tools over MCP often sends its events as signed webhooks under an open
specification, and so do many systems besides. The specification signs
`<delivery identifier>.<moment>.<raw body>` with HMAC-SHA256, keyed with the bytes the secret
encodes in base64 after the prefix `whsec_`. It sends the identifier, the moment in whole seconds
since the epoch, and the signature in three headers of its own. The signature header carries one
or more entries `v1,<base64 digest>`, separated by spaces, so that a sender can roll its secret
over; one of them must verify. The contract calls this scheme `hmac-sha256-identified`.

The order is the contract's: the signature is verified before the body is read, so that nothing
unsigned or wrongly signed is ever parsed. A moment more than `WINDOW` seconds from the delivery's
arrival is refused as `bad_signature`: a captured delivery cannot be replayed later. The
identifier is signed, so a delivery whose identifier was changed on the way does not verify, and
the identifier is the `event_id` by which a redelivery is recognised.

Then the event is normalised as far as an open specification can. Its payload carries `type`,
the event kind, `timestamp`, when it occurred, and `data`. The kind must be one the operator
listed, or the delivery is refused as `unsupported_event`. The sender is the sending system as
the operator names it (`--intake-sender`), an automation: the specification names no person.
`data` is handed on as the context, as the sender wrote it. The reply goes back to the channel,
addressed to the sending system; a channel without a reply operation is answered nowhere, and the
intake's outcome says so (`composition/replies.py`).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

type Json = dict[str, Any]

SCHEME = "hmac-sha256-identified"
ID_HEADER = "webhook-id"
TIMESTAMP_HEADER = "webhook-timestamp"
SIGNATURE_HEADER = "webhook-signature"
VERSION = "v1"
SECRET_PREFIX = "whsec_"  # noqa: S105 — a prefix of the specification, no secret
WINDOW = 300
"""Seconds a delivery's moment of sending may lie from the moment it arrived."""
DEFAULT_CREDENTIAL = "VENDOR_INTAKE_SECRET"
TOKEN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


class Malformed(Exception):
    """The body is not a delivery under the specification."""


def refused(reason: str, detail: str) -> Json:
    return {"refused": {"reason": reason, "detail": detail}}


def key_of(secret: str) -> bytes | None:
    """The key the secret encodes in base64, after an optional `whsec_`; None when it is no
    base64."""
    try:
        return base64.b64decode(secret.strip().removeprefix(SECRET_PREFIX), validate=True)
    except (binascii.Error, ValueError):
        return None


def signature_of(delivery: str, moment: str, body: bytes, key: bytes) -> str:
    base = f"{delivery}.{moment}.".encode() + body
    return base64.b64encode(hmac.new(key, base, hashlib.sha256).digest()).decode()


def signed(body: str, secret: str, delivery: str, moment: int) -> dict[str, str]:
    """The headers a sender writes for `body`: what the faults and the tests sign with."""
    key = key_of(secret) or secret.encode()
    digest = signature_of(delivery, str(moment), body.encode(), key)
    return {
        ID_HEADER: delivery,
        TIMESTAMP_HEADER: str(moment),
        SIGNATURE_HEADER: f"{VERSION},{digest}",
    }


def arrival(received_at: str) -> float:
    """`received_at` in seconds since the epoch; 0 where it is not a moment."""
    try:
        moment = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    return (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).timestamp()


def verify(
    headers: Mapping[str, str],
    body: bytes,
    secret: str | None,
    received_at: datetime,
    window: int | None = WINDOW,
) -> Json | None:
    """None when the delivery is signed with the secret over its own identifier and moment,
    at a moment close to its arrival; otherwise the refusal. `window` None checks no moment —
    for the fault that shows the suite catches exactly that."""
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
    moment = headers.get(TIMESTAMP_HEADER, "").strip()
    if not moment.isdigit():
        return refused("bad_signature", f"no moment of sending in {TIMESTAMP_HEADER}")
    if window is not None and abs(received_at.timestamp() - int(moment)) > window:
        return refused(
            "bad_signature",
            f"signed {int(received_at.timestamp()) - int(moment)} s before it arrived; more "
            f"than {window} s is a replay",
        )
    expected = signature_of(delivery, moment, body, key)
    for entry in given.split():
        version, _, digest = entry.partition(",")
        if version == VERSION and hmac.compare_digest(digest, expected):
            return None
    return refused("bad_signature", f"no entry of {SIGNATURE_HEADER} verifies against the secret")


@dataclass(frozen=True)
class Intake:
    """What the operator configured: the channel the events arrive on, the kinds it takes, the
    sending system's account, and the credential that holds the secret."""

    channel: str
    events: tuple[str, ...]
    sender: str
    credential: str = DEFAULT_CREDENTIAL

    def __post_init__(self) -> None:
        if not TOKEN.match(self.channel) or not self.channel.startswith("channel."):
            raise ValueError(f"the intake channel {self.channel!r} is no capability channel.<…>")
        if not self.events:
            raise ValueError("the intake takes at least one event kind")
        for kind in self.events:
            if not TOKEN.match(kind):
                raise ValueError(f"the event kind {kind!r} is no lowercase dotted token")
        if not self.sender:
            raise ValueError("the intake names the sending system's account")

    def declaration(self) -> Json:
        return {"events": list(self.events), "signature": {"scheme": SCHEME}}

    def normalise(
        self,
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
            return self._event(lowered, raw, arrived)
        except Malformed as error:
            return refused("malformed", str(error))

    def _event(self, headers: Mapping[str, str], raw: bytes, arrived: datetime) -> Json:
        try:
            payload = json.loads(raw)
        except ValueError as error:
            raise Malformed(f"the body is not JSON: {error}") from None
        if not isinstance(payload, dict):
            raise Malformed("the body is not an object")
        kind = payload.get("type")
        if not isinstance(kind, str) or not kind:
            raise Malformed("the payload names no type")
        if kind not in self.events:
            return refused(
                "unsupported_event",
                f"an event of type {kind!r} is not one this intake takes "
                f"({', '.join(self.events)})",
            )
        data = payload.get("data", {})
        if not isinstance(data, dict):
            raise Malformed("the payload's data is not an object")
        occurred_at = arrived
        occurred = payload.get("timestamp")
        if isinstance(occurred, str):
            try:
                occurred_at = datetime.fromisoformat(occurred.replace("Z", "+00:00"))
            except ValueError:
                raise Malformed("the payload's timestamp is not a moment") from None
            if occurred_at.tzinfo is None:
                occurred_at = occurred_at.replace(tzinfo=UTC)
        moment = occurred_at.astimezone(UTC).isoformat(timespec="seconds")
        return {
            "accepted": {
                "event_id": headers[ID_HEADER].strip(),
                "event": kind,
                "channel": self.channel,
                "sender": {"account": self.sender, "kind": "automation"},
                "intent": {"raw": kind, "authored": False},
                "context": {"type": kind, "data": data},
                "reply_to": {"channel": self.channel, "address": self.sender},
                "occurred_at": moment.replace("+00:00", "Z"),
            }
        }
