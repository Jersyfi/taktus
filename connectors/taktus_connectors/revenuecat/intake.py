"""Intake: the in-app subscription service's webhook becomes an intake command, or is refused
(ADR-0337).

The service signs nothing. It sends the value its operator configured for the webhook in the
`Authorization` header, and that is all a receiver can check: the scheme `shared-token`. The
connector compares the header with the intake secret in constant time before the body is read.
It proves the sender knows the value; it does not prove the body is the one the service sent,
and it bounds no replay. That is why only events that start reading processes, or processes a
person confirms, are taken from it.

**De-duplicated by the event.** The event's identifier is the service's `event.id`, which a
redelivery carries unchanged, so the intake keeps one event (ADR-0048 §4).

- `INITIAL_PURCHASE`, `RENEWAL`, `PRODUCT_CHANGE`, `CANCELLATION`, `UNCANCELLATION` and
  `EXPIRATION` become `subscription.changed`: `customer` (`app_user_id`), `subscription`
  (`original_transaction_id`), `change` (the type in lowercase);
- `BILLING_ISSUE` becomes `payment.failed`: `customer`, `payment` (`transaction_id`, else the
  event's identifier).

The sender is the service's project, configured for the connector, an automation. Every other
type — `TEST` among them — is `unsupported_event`. Nothing of the customer but the identifier
the product chose is copied: no store, country, price or address.
"""

from __future__ import annotations

import hmac
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from taktus_connectors.revenuecat.declaration import CAPABILITY

type Json = dict[str, Any]

TOKEN_HEADER = "authorization"  # noqa: S105 — a header's name, no secret
PAYMENT_FAILED = "payment.failed"
SUBSCRIPTION_CHANGED = "subscription.changed"
CHANGES = frozenset(
    {
        "INITIAL_PURCHASE",
        "RENEWAL",
        "PRODUCT_CHANGE",
        "CANCELLATION",
        "UNCANCELLATION",
        "EXPIRATION",
    }
)


def refused(reason: str, detail: str) -> Json:
    return {"refused": {"reason": reason, "detail": detail}}


def signed(body: str, secret: str) -> dict[str, str]:
    """The header the service writes: the configured value, whatever the body."""
    return {TOKEN_HEADER: secret}


def receiver(project: str) -> Callable[..., Json]:
    def normalise(
        headers: Mapping[str, str], body: str, received_at: str, secret: str | None
    ) -> Json:
        lowered = {name.lower(): value for name, value in headers.items()}
        given = lowered.get(TOKEN_HEADER, "").strip()
        if not given:
            return refused("unsigned", f"no {TOKEN_HEADER} header")
        if not secret:
            return refused("bad_signature", "no intake secret is available; nothing can be checked")
        if not hmac.compare_digest(given.encode("utf-8"), secret.strip().encode("utf-8")):
            return refused("bad_signature", f"{TOKEN_HEADER} is not the configured value")
        return _event(body, received_at, project)

    return normalise


def _event(body: str, received_at: str, project: str) -> Json:
    try:
        payload = json.loads(body)
    except ValueError:
        return refused("malformed", "the body is not JSON")
    event = payload.get("event") if isinstance(payload, dict) else None
    if not isinstance(event, dict):
        return refused("malformed", "the body carries no event")
    kind = event.get("type")
    if kind not in CHANGES and kind != "BILLING_ISSUE":
        return refused("unsupported_event", f"an event of type {kind!r} is not taken")
    identifier = event.get("id")
    customer = event.get("app_user_id")
    if not isinstance(identifier, str) or not identifier:
        return refused("malformed", "the event names no identifier")
    if not isinstance(customer, str) or not customer:
        return refused("malformed", "the event names no customer")
    if kind == "BILLING_ISSUE":
        payment = event.get("transaction_id")
        name, context = (
            PAYMENT_FAILED,
            {
                "customer": customer,
                "payment": payment if isinstance(payment, str) and payment else identifier,
            },
        )
    else:
        subscription = event.get("original_transaction_id")
        if not isinstance(subscription, str) or not subscription:
            return refused("malformed", "the event names no subscription")
        name, context = (
            SUBSCRIPTION_CHANGED,
            {
                "customer": customer,
                "subscription": subscription,
                "change": str(kind).lower(),
            },
        )
    stamp = event.get("event_timestamp_ms")
    occurred = (
        datetime.fromtimestamp(stamp / 1000, UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
        if isinstance(stamp, int) and not isinstance(stamp, bool)
        else received_at
    )
    return {
        "accepted": {
            "event_id": identifier,
            "event": name,
            "channel": CAPABILITY,
            "sender": {"account": project, "kind": "automation"},
            "intent": {"raw": name, "authored": False},
            "context": context,
            "reply_to": {"channel": CAPABILITY, "address": project},
            "occurred_at": occurred,
        }
    }
