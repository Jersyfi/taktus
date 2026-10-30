"""Intake: a message the relay delivered, signed, becomes an intake command, or is refused.

A function from the delivery — headers, raw body, the moment it arrived — and the intake
secret to an `IntakeResult` (`Connector.json#/$defs/IntakeResult`). The relay (`relay.py`) reads
each new message from the mailbox and delivers it as a JSON body: the mailbox, the message's
UID there, and the message itself in base64, so that every byte survives. The scheme is
`hmac-sha256`: `X-Mail-Signature` is `sha256=` and the HMAC-SHA256 of the raw body, keyed with
the intake secret. The signature is verified before the body is read.

**De-duplicated by message identifier.** The event's identifier is the message's
`Message-ID`. The same message relayed twice — after a restart of the relay, or as two copies
in the mailbox — carries the same identifier, and the intake keeps one event: a delivery whose
identifier the tenant already holds is a redelivery (`components/command`, ADR-0048 §4). A
message without a `Message-ID` is identified by the digest of its bytes.

Then the message is normalised as far as the channel can. The sender is the digest of the
address it came from, `sha256:` and 64 hexadecimal digits: an opaque account, which the
identity component maps to a person, never a name. What they wrote is the subject and the
text of the plain part. The reply goes to the address the message asks replies to go to, in
the thread of the message. Three kinds of message are refused:

- a message this connector sent itself, recognised by its mark (`operations.py`), as
  `own_action`;
- an automatic message, one whose `Auto-Submitted` is not `no` (RFC 3834), as
  `unsupported_event`, so that two automata never answer each other;
- a message without a sender address, as `malformed`.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any

from taktus_connectors.mail.declaration import CHANNEL, INTAKE_CREDENTIAL
from taktus_connectors.mail.operations import (
    addresses_in,
    digest_of,
    is_own,
    moment_of,
    parse,
    text_of,
)

type Json = dict[str, Any]

SIGNATURE_HEADER = "x-mail-signature"
PREFIX = "sha256="
EVENT = "message.posted"
AUTOMATED = frozenset({"bulk", "list", "junk"})


def refused(reason: str, detail: str) -> Json:
    return {"refused": {"reason": reason, "detail": detail}}


def signature_of(body: str, secret: str) -> str:
    return PREFIX + hmac.new(secret.encode(), body.encode("utf-8"), hashlib.sha256).hexdigest()


def signed(body: str, secret: str) -> dict[str, str]:
    """The headers that sign a body, as the relay sends them."""
    return {SIGNATURE_HEADER: signature_of(body, secret)}


def account_of(address: str) -> str:
    return "sha256:" + hashlib.sha256(address.strip().lower().encode()).hexdigest()


def normalise(headers: Mapping[str, str], body: str, received_at: str, secret: str | None) -> Json:
    """The whole of intake: verify, read, refuse or accept."""
    given = {name.lower(): value for name, value in headers.items()}.get(SIGNATURE_HEADER, "")
    if not given:
        return refused("unsigned", f"no {SIGNATURE_HEADER} header")
    if not secret:
        return refused(
            "bad_signature",
            f"no intake secret is available under {INTAKE_CREDENTIAL}; nothing can be verified",
        )
    if not hmac.compare_digest(given.strip(), signature_of(body, secret)):
        return refused("bad_signature", f"{SIGNATURE_HEADER} does not verify against the secret")
    try:
        delivery = json.loads(body)
        raw = base64.b64decode(str(delivery["message"]), validate=True)
        mailbox = str(delivery.get("mailbox") or "INBOX")
    except (ValueError, KeyError, TypeError, binascii.Error):
        return refused("malformed", "the body is not a relayed message")
    try:
        message = parse(raw)
    except Exception:
        return refused("malformed", "the message cannot be read")
    mid = str(message.get("Message-ID", "")).strip()
    if mid and is_own(mid):
        return refused("own_action", "the message was sent by this connector")
    automatic = str(message.get("Auto-Submitted", "no")).strip().lower()
    if automatic != "no":
        return refused(
            "unsupported_event",
            f"an automatic message (Auto-Submitted: {automatic}) is not answered",
        )
    senders = addresses_in(message, "From")
    if not senders:
        return refused("malformed", "the message names no sender address")
    reply = (addresses_in(message, "Reply-To") or senders)[0]
    event_id = mid or digest_of(raw)
    automation = (
        str(message.get("Precedence", "")).strip().lower() in AUTOMATED
        or message.get("List-Id") is not None
    )
    context: Json = {"conversation": mailbox, "message": event_id}
    references = str(message.get("References", "") or message.get("In-Reply-To", "")).split()
    if references:
        context["thread"] = references[0]
    subject = str(message.get("Subject", "")).strip()
    text = text_of(message).strip()
    return {
        "accepted": {
            "event_id": event_id,
            "event": EVENT,
            "channel": CHANNEL,
            "sender": {
                "account": account_of(senders[0]),
                "kind": "automation" if automation else "person",
            },
            "intent": {"raw": f"{subject}\n\n{text}".strip()},
            "context": context,
            "reply_to": {"channel": CHANNEL, "address": reply, **({"thread": mid} if mid else {})},
            "occurred_at": moment_of(message) or received_at,
        }
    }
