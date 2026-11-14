"""An error tracker's webhook for a new issue starts the process its trigger names (ADR-0331): the
error tracking connector verifies the delivery and normalises it into `error.created`, the event
keeps the project and the error, and a redelivery or a second delivery of the same issue starts
nothing twice. The reaction is the one of `test_reactions.py`; the intake is the connector's own,
over deliveries in the shape of the tracker's published webhook (DEC-0225).
"""

from __future__ import annotations

import json
import secrets
from datetime import timedelta
from pathlib import Path
from typing import Any

from taktus_connectors.sentry import intake

from taktus.components.command.application.service import ReceiveIntake, ReceiveIntakeHandler
from taktus.components.process.domain.model.event import KINDS, Event, Kind
from taktus.composition.reactions import run_id_of
from taktus.ports.connector import Delivery, IntakeResult

from .test_reactions import TENANT, World, bundle

PAYLOADS = Path(__file__).parents[2] / "connectors" / "taktus_connectors" / "sentry" / "payloads"
SECRET = "client-" + secrets.token_hex(16)
CHANNEL = "errors.issues"


def delivery(name: str = "issue-created", received_at: str = "2026-10-10T09:00:01Z") -> Any:
    body = (PAYLOADS / f"{name}.body.json").read_text()
    headers = json.loads((PAYLOADS / f"{name}.headers.json").read_text())
    return intake.normalise({**headers, **intake.signed(body, SECRET)}, body, received_at, SECRET)


class ErrorsWorld(World):
    """The world of `test_reactions.py`, receiving on the error tracker's channel."""

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
        """The integration's installation, placed as the automation of a person who linked it."""
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


def test_the_delivery_is_verified_and_normalised_into_the_catalogues_kind() -> None:
    accepted = delivery()["accepted"]
    assert accepted["event"] == "error.created" and accepted["channel"] == CHANNEL
    assert accepted["event_id"] == "error:1170820242", "the issue, not the delivery, is the key"
    assert accepted["context"]["error"] == "1170820242"
    assert accepted["sender"]["kind"] == "automation"
    event = Event(
        id=accepted["event_id"],
        kind=Kind.ERROR_CREATED,
        channel=CHANNEL,
        occurred_at=accepted["occurred_at"],
        received_at="2026-10-10T09:00:01Z",
        context=Event.context_of(accepted["context"]),
    )
    assert event.missing() == [] and KINDS[Kind.ERROR_CREATED].required == {"project", "error"}


def test_a_delivery_that_is_not_signed_by_the_secret_or_not_a_new_issue_is_refused() -> None:
    body = (PAYLOADS / "issue-created.body.json").read_text()
    headers = json.loads((PAYLOADS / "issue-created.headers.json").read_text())
    unsigned = intake.normalise(headers, body, "2026-10-10T09:00:01Z", SECRET)
    assert unsigned["refused"]["reason"] == "unsigned"
    forged = intake.normalise(
        {**headers, **intake.signed(body, "another secret")}, body, "2026-10-10T09:00:01Z", SECRET
    )
    assert forged["refused"]["reason"] == "bad_signature"
    assert delivery("issue-resolved")["refused"]["reason"] == "unsupported_event"


async def test_a_new_error_starts_its_process_once_however_often_it_is_delivered() -> None:
    world = ErrorsWorld()
    first = delivery()
    await world.placed(first["accepted"]["sender"]["account"])
    await world.registered(
        bundle(
            "new-errors",
            triggers=[
                {
                    "event": "error.created",
                    "inputs": {"path": "1h"},
                    "from_event": {"issue": "error"},
                }
            ],
        )
    )
    await world.received(first)
    (started,) = await world.reactions.tick()
    assert started == run_id_of(TENANT, "new-errors", "error:1170820242")
    run = await world.run(started)
    assert run is not None and run.inputs == {"issue": 1170820242, "path": "1h"}

    await world.received(delivery(received_at="2026-10-10T09:05:00Z"))
    assert await world.reactions.tick() == [], "the same issue delivered again starts nothing"
