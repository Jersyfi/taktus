"""Intake: the payment provider's webhook becomes an intake command, or is refused (ADR-0337).

The provider signs every delivery under the scheme `hmac-sha256-stamped`. The header
`Stripe-Signature` carries comma-separated entries: `t=<moment>`, the moment of sending in whole
seconds since the epoch, and one or more `v1=<digest>`, the HMAC-SHA256 of `<moment>.<raw body>`
keyed with the endpoint's signing secret, in lowercase hex. Several `v1` entries appear while a
secret is rolled over; one must verify. Entries of other names — `v0` of a test environment
among them — are ignored. The signature is verified before the body is read, and a moment more
than 300 seconds from the arrival is refused as a replay.

**De-duplicated by the event.** The event's identifier is the provider's `evt_…` identifier,
which a redelivery carries unchanged, so the intake keeps one event (ADR-0048 §4).

Two kinds of the catalogue are taken:

- `invoice.payment_failed` becomes `payment.failed`: `customer`, `payment` (the invoice);
- `customer.subscription.created`, `.updated` and `.deleted` become `subscription.changed`:
  `customer`, `subscription`, `change` (`created`, `updated`, `deleted`).

The sender is the provider's account the event belongs to (`account`, or the configured name
where the delivery names none), an automation; the event carries no amount, no address and no
name of the customer, only identifiers. Every other type is `unsupported_event`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from taktus_connectors.stripe.declaration import CAPABILITY

type Json = dict[str, Any]

SIGNATURE_HEADER = "stripe-signature"
WINDOW = 300
"""Seconds a delivery's moment of sending may lie from the moment it arrived."""
PAYMENT_FAILED = "payment.failed"
SUBSCRIPTION_CHANGED = "subscription.changed"
CHANGES = {
    "customer.subscription.created": "created",
    "customer.subscription.updated": "updated",
    "customer.subscription.deleted": "deleted",
}
DEFAULT_SENDER = "payment-provider"


def refused(reason: str, detail: str) -> Json:
    return {"refused": {"reason": reason, "detail": detail}}


def digest_of(moment: str, body: bytes, secret: str) -> str:
    base = moment.encode() + b"." + body
    return hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()


def signed(body: str, secret: str, moment: int) -> dict[str, str]:
    """The header the provider writes for `body`: what the faults and the tests sign with."""
    return {SIGNATURE_HEADER: f"t={moment},v1={digest_of(str(moment), body.encode(), secret)}"}


def _entries(header: str) -> tuple[str, list[str]]:
    moment = ""
    digests: list[str] = []
    for part in header.split(","):
        name, _, value = part.strip().partition("=")
        if name == "t":
            moment = value.strip()
        elif name == "v1":
            digests.append(value.strip().lower())
    return moment, digests


def verify(
    headers: Mapping[str, str],
    body: bytes,
    secret: str | None,
    arrived: datetime,
    window: int | None,
) -> Json | None:
    """None when one `v1` entry verifies over the header's moment, close to the arrival."""
    given = headers.get(SIGNATURE_HEADER, "").strip()
    if not given:
        return refused("unsigned", f"no {SIGNATURE_HEADER} header")
    if not secret:
        return refused("bad_signature", "no intake secret is available; nothing can be verified")
    moment, digests = _entries(given)
    if not moment.isdigit() or not digests:
        return refused("bad_signature", f"{SIGNATURE_HEADER} names no moment or no v1 digest")
    if window is not None and abs(arrived.timestamp() - int(moment)) > window:
        return refused(
            "bad_signature",
            f"signed {int(arrived.timestamp()) - int(moment)} s before it arrived; more than "
            f"{window} s is a replay",
        )
    expected = digest_of(moment, body, secret)
    if any(hmac.compare_digest(d, expected) for d in digests):
        return None
    return refused(
        "bad_signature", f"no v1 entry of {SIGNATURE_HEADER} verifies against the secret"
    )


def arrival(received_at: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def receiver(sender: str = DEFAULT_SENDER, window: int | None = WINDOW) -> Callable[..., Json]:
    """The intake; `window` None checks no moment — for the fault that shows the suite catches
    exactly that."""

    def normalise(
        headers: Mapping[str, str], body: str, received_at: str, secret: str | None
    ) -> Json:
        lowered = {name.lower(): value for name, value in headers.items()}
        arrived = arrival(received_at)
        if arrived is None:
            return refused("malformed", "received_at is not a moment")
        refusal = verify(lowered, body.encode("utf-8"), secret, arrived, window)
        if refusal is not None:
            return refusal
        return _event(body, received_at, sender)

    return normalise


def _event(body: str, received_at: str, sender: str) -> Json:
    try:
        payload = json.loads(body)
    except ValueError:
        return refused("malformed", "the body is not JSON")
    if not isinstance(payload, dict):
        return refused("malformed", "the body is not an object")
    kind = payload.get("type")
    data = payload.get("data")
    item = data.get("object") if isinstance(data, dict) else None
    identifier = payload.get("id")
    if kind != "invoice.payment_failed" and kind not in CHANGES:
        return refused("unsupported_event", f"an event of type {kind!r} is not taken")
    if not isinstance(identifier, str) or not identifier.startswith("evt_"):
        return refused("malformed", "the event names no identifier")
    if not isinstance(item, dict):
        return refused("malformed", "the event carries no object")
    customer = item.get("customer")
    record = item.get("id")
    if not isinstance(customer, str) or not customer or not isinstance(record, str) or not record:
        return refused("malformed", "the event's object names no customer or no identifier")
    if kind == "invoice.payment_failed":
        event, context = PAYMENT_FAILED, {"customer": customer, "payment": record}
    else:
        event = SUBSCRIPTION_CHANGED
        context = {"customer": customer, "subscription": record, "change": CHANGES[kind]}
    account = payload.get("account")
    who = account if isinstance(account, str) and account else sender
    created = payload.get("created")
    occurred = (
        datetime.fromtimestamp(created, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        if isinstance(created, int) and not isinstance(created, bool)
        else received_at
    )
    return {
        "accepted": {
            "event_id": identifier,
            "event": event,
            "channel": CAPABILITY,
            "sender": {"account": who, "kind": "automation"},
            "intent": {"raw": event, "authored": False},
            "context": context,
            "reply_to": {"channel": CAPABILITY, "address": who},
            "occurred_at": occurred,
        }
    }
