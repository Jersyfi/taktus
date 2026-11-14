"""The payment provider's and the in-app subscription service's webhooks (ADR-0337): the first is
verified under `hmac-sha256-stamped` — its moment signed, a replay refused — the second under
`shared-token`, which proves only that the sender knows the configured value. Both become the
catalogue's `payment.failed` and `subscription.changed`, keyed by the source's event identifier,
and a subscription that changed starts B-3.04 for its customer once, however often it is
delivered. Deliveries are written for the test from the sources' published webhook payloads
(DEC-0225).
"""

from __future__ import annotations

import json
import secrets
from datetime import timedelta
from pathlib import Path
from typing import Any

import yaml
from taktus_connectors.revenuecat import intake as in_app
from taktus_connectors.stripe import intake as card

from taktus.components.command.application.service import ReceiveIntake, ReceiveIntakeHandler
from taktus.components.process.domain.model.event import Event, Kind
from taktus.composition.reactions import run_id_of
from taktus.ports.connector import Delivery, IntakeResult

from .test_reactions import TENANT, World

ROOT = Path(__file__).parents[2]
CARD = ROOT / "connectors" / "taktus_connectors" / "stripe" / "payloads"
IN_APP = ROOT / "connectors" / "taktus_connectors" / "revenuecat" / "payloads"
B_3_04 = ROOT / "blueprints" / "software-operations" / "processes" / "B-3.04-paid-not-unlocked.yaml"
SECRET = "whsec_" + secrets.token_hex(16)
TOKEN = "Bearer " + secrets.token_hex(16)
ARRIVED = "2026-01-01T00:00:00Z"
MOMENT = 1767225600
CHANNEL = "payments.subscriptions"


def body(folder: Path, name: str) -> str:
    return (folder / f"{name}.body.json").read_text()


def from_card(name: str, moment: int = MOMENT, secret: str = SECRET) -> dict[str, Any]:
    text = body(CARD, name)
    return card.receiver()(card.signed(text, secret, moment), text, ARRIVED, SECRET)


def from_in_app(name: str, token: str = TOKEN) -> dict[str, Any]:
    text = body(IN_APP, name)
    return in_app.receiver("proj_fake")({"Authorization": token}, text, ARRIVED, TOKEN)


def test_a_failed_payment_is_verified_with_its_moment_and_keyed_by_the_event() -> None:
    accepted = from_card("payment-failed")["accepted"]
    assert accepted["event"] == "payment.failed" and accepted["event_id"].startswith("evt_")
    assert accepted["context"] == {"customer": "cus_fake3", "payment": "in_fake3"}
    event = Event(
        id=accepted["event_id"],
        kind=Kind.PAYMENT_FAILED,
        channel=CHANNEL,
        occurred_at=accepted["occurred_at"],
        received_at=ARRIVED,
        context=Event.context_of(accepted["context"]),
    )
    assert event.missing() == []
    changed = from_card("subscription-created")["accepted"]
    assert changed["context"] == {
        "customer": "cus_fake1",
        "subscription": "sub_fake1",
        "change": "created",
    }


def test_a_card_delivery_signed_long_ago_with_another_secret_or_of_another_type_is_refused() -> (
    None
):
    assert from_card("payment-failed", moment=MOMENT - 3600)["refused"]["reason"] == "bad_signature"
    assert from_card("payment-failed", secret="whsec_" + secrets.token_hex(8))["refused"][
        "reason"
    ] == ("bad_signature")
    text = body(CARD, "payment-failed")
    header = card.signed(text, SECRET, MOMENT)[card.SIGNATURE_HEADER]
    rolled = {card.SIGNATURE_HEADER: header.replace("v1=", "v1=00,v1=", 1)}
    assert "accepted" in card.receiver()(rolled, text, ARRIVED, SECRET), "one v1 entry verifies"
    moved = {card.SIGNATURE_HEADER: header.replace(f"t={MOMENT}", f"t={MOMENT - 1}")}
    assert card.receiver()(moved, text, ARRIVED, SECRET)["refused"]["reason"] == "bad_signature"
    assert from_card("charge-succeeded")["refused"]["reason"] == "unsupported_event"


def test_the_in_app_service_is_admitted_by_its_configured_value_alone() -> None:
    renewal = from_in_app("renewal")["accepted"]
    assert renewal["event"] == "subscription.changed" and renewal["context"]["change"] == "renewal"
    assert "DE" not in json.dumps(renewal) and "9.99" not in json.dumps(renewal)
    billing = from_in_app("billing-issue")["accepted"]
    assert billing["event"] == "payment.failed"
    assert billing["context"] == {"customer": "app_user1", "payment": "2000000099"}
    assert (
        from_in_app("renewal", token="Bearer " + secrets.token_hex(8))["refused"]["reason"]
        == "bad_signature"
    )
    assert from_in_app("test")["refused"]["reason"] == "unsupported_event"


class PaymentsWorld(World):
    """The world of `test_reactions.py`, receiving on the payment provider's channel."""

    def __init__(self) -> None:
        super().__init__()
        self.receive = ReceiveIntakeHandler(
            {CHANNEL: self.connector},
            self.events,
            self.persistence,
            self.identity.directory,
            outbox=self.outbox,
        )

    async def placed(self, account: str) -> None:
        who, _ = await self.identity.person(TENANT, "idn_ada")
        code = await self.identity.code(who, CHANNEL)
        answer = await self.identity.directory.unknown_sender(CHANNEL, account, code)
        assert answer.linked is not None

    async def received(self, result: dict[str, Any]) -> None:
        self.connector.answer = IntakeResult.model_validate(result)
        self.clock.current += timedelta(seconds=1)
        given = Delivery(headers={}, body="{}", received_at=self.clock.now())
        outcome = await self.receive.execute(
            ReceiveIntake(channel=CHANNEL, delivery=given, tenant=TENANT)
        )
        assert outcome.accepted is not None


async def test_a_changed_subscription_starts_b_3_04_for_its_customer_once() -> None:
    world = PaymentsWorld()
    created = from_card("subscription-created")
    await world.placed(created["accepted"]["sender"]["account"])
    await world.registered(yaml.safe_load(B_3_04.read_text()))
    await world.received(created)
    (started,) = await world.reactions.tick()
    assert started == run_id_of(TENANT, "b-3-04", "evt_1QfakeSubscriptionCreated")
    run = await world.run(started)
    assert run is not None and run.inputs == {"customer": "cus_fake1"}
    await world.received(from_card("subscription-created"))
    assert await world.reactions.tick() == [], "a redelivery starts nothing twice"
