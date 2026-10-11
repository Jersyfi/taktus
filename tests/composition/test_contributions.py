"""A contribution from a person Taktus does not know starts the triage for its owner (UC-1.9,
ADR-0088), over the memory stores: an issue or pull request opened by an unplaced sender on a
channel the instance names a triage for is kept as data, without the sender's account or text,
and starts one run of the triage process acting for whoever registered it — once per
contribution, never as a command of the sender. Everything else an unknown sender sends stays
as UC-1.7 and UC-4.14 say."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from composition.test_reactions import ACCOUNT, TENANT, World, bundle
from taktus.components.command.application.service import (
    CompleteIntake,
    ReceiveIntake,
    ReceiveIntakeHandler,
    UnknownSender,
)
from taktus.components.command.domain.model import IntakeStatus
from taktus.composition.reactions import Reactions, run_id_of
from taktus.ports.connector import Delivery, IntakeResult
from taktus.ports.outbox import INTAKE_CONTRIBUTION

STRANGER = "999001"
TRIAGE = "p05-triage"


def opened(
    delivery: str = "dlv_c1",
    *,
    kind: str = "issue.opened",
    number: str = "245",
    account: str = STRANGER,
) -> IntakeResult:
    context: dict[str, Any] = {"repository": "acme/taktus"}
    if kind == "pull_request.opened":
        context |= {"pull_request": number, "head": "outside", "base": "main"}
    elif kind == "issue_comment.created":
        context |= {"issue": number, "comment": "7", "is_pull_request": False}
    else:
        context |= {"issue": number}
    return IntakeResult.model_validate(
        {
            "accepted": {
                "event_id": delivery,
                "event": kind,
                "channel": "channel.repo",
                "sender": {"account": account, "kind": "person"},
                "intent": {"raw": "Please add an export to CSV"},
                "context": context,
                "reply_to": {"channel": "channel.repo", "address": f"acme/taktus#{number}"},
                "occurred_at": "2026-10-10T09:00:00Z",
            }
        }
    )


def triage_bundle() -> dict[str, Any]:
    document = bundle(TRIAGE, triggers=[])
    document.pop("triggers")
    document["inputs"] = {"number": {"description": "the item", "example": 245}}
    document["steps"][0]["work"] = {"rule": "constant", "value": {"$input": "number"}}
    return document


class Public(World):
    """The world of `test_reactions.py`, with `channel.repo` public: its triage is named."""

    def __init__(self, *, triage: dict[str, str] | None = None) -> None:
        super().__init__()
        self.receive = ReceiveIntakeHandler(
            {"channel.repo": self.connector},
            self.events,
            self.persistence,
            self.identity.directory,
            outbox=self.outbox,
            triage={"channel.repo": TRIAGE} if triage is None else triage,
        )
        old = self.reactions
        self.reactions = Reactions(
            tenants=(TENANT,),
            outbox=self.outbox,
            intake=old._intake,
            reactions=old._reactions,
            commission=old._commission,
            engine=old._engine,
            runs=self.runs,
            ledger=self.ledger,
            work=self.persistence,
            clock=self.clock,
            identities=self.identity.directory,
            ids=self.ids,
        )

    async def sent(self, answer: IntakeResult) -> Any:
        self.connector.answer = answer
        self.clock.current += timedelta(seconds=1)
        delivery = Delivery(headers={}, body="{}", received_at=self.clock.now())
        return await self.receive.execute(
            ReceiveIntake(channel="channel.repo", delivery=delivery, tenant=TENANT)
        )

    async def contributions(self) -> int:
        async with self.persistence.transaction(TENANT):
            return len(await self.outbox.unpublished(TENANT, INTAKE_CONTRIBUTION, 100))


async def test_an_issue_an_unknown_sender_opens_starts_the_triage_for_its_owner() -> None:
    world = Public()
    await world.registered(triage_bundle())
    outcome = await world.sent(opened())

    assert outcome.accepted is None, "no command of the sender is kept"
    assert outcome.unknown_sender is not None
    kept = outcome.contribution
    assert kept is not None and kept.status is IntakeStatus.CONTRIBUTION
    assert kept.sender_account != STRANGER and STRANGER not in kept.model_dump_json()
    assert kept.intent == "", "the sender's text is read from the system of record, not kept"
    assert await world.contributions() == 1

    (started,) = await world.reactions.tick()
    assert started == run_id_of(TENANT, TRIAGE, "dlv_c1")
    run = await world.run(started)
    assert run is not None
    assert run.identity == "idn_op", "the run acts for whoever registered the triage"
    assert run.inputs == {"number": 245}
    assert await world.contributions() == 0
    async with world.persistence.transaction(TENANT):
        entries = await world.ledger.entries(TENANT)
    assert all(STRANGER not in e.model_dump_json() for e in entries), "never the account"
    assert await world.reactions.tick() == []


async def test_a_pull_request_from_outside_starts_the_triage_too() -> None:
    world = Public()
    await world.registered(triage_bundle())
    await world.sent(opened(kind="pull_request.opened", number="300"))
    (started,) = await world.reactions.tick()
    run = await world.run(started)
    assert run is not None and run.inputs == {"number": 300}


async def test_a_contribution_delivered_twice_starts_the_triage_once() -> None:
    world = Public()
    await world.registered(triage_bundle())
    await world.sent(opened())
    await world.sent(opened())
    assert await world.contributions() == 1
    assert len(await world.reactions.tick()) == 1
    await world.sent(opened())
    assert await world.reactions.tick() == []


async def test_a_contribution_is_never_completed_into_a_command_of_its_sender() -> None:
    world = Public()
    await world.registered(triage_bundle())
    await world.sent(opened())
    try:
        await world.reactions._intake.execute(CompleteIntake(tenant=TENANT, event_id="dlv_c1"))
    except UnknownSender:
        pass
    else:
        raise AssertionError("a contribution was completed into a command")


async def test_a_comment_by_an_unknown_sender_is_no_contribution() -> None:
    world = Public()
    await world.registered(triage_bundle())
    outcome = await world.sent(opened(kind="issue_comment.created"))
    assert outcome.contribution is None and outcome.unknown_sender is not None
    assert await world.contributions() == 0


async def test_a_channel_without_a_triage_keeps_nothing_of_an_unknown_sender() -> None:
    world = Public(triage={})
    await world.registered(triage_bundle())
    outcome = await world.sent(opened())
    assert outcome.contribution is None and outcome.accepted is None
    assert await world.contributions() == 0
    assert await world.reactions.tick() == []


async def test_a_placed_sender_s_issue_is_no_contribution() -> None:
    world = Public()
    await world.linked(account=ACCOUNT)
    await world.registered(triage_bundle())
    outcome = await world.sent(opened(account=ACCOUNT))
    assert outcome.accepted is not None and outcome.contribution is None
    assert await world.contributions() == 0


async def test_no_trigger_matches_an_unknown_sender_while_the_triage_starts() -> None:
    """UC-4.14 stands: a process whose trigger names the kind is not started by a stranger."""
    world = Public()
    await world.registered(triage_bundle())
    refine = {"event": "issue.opened", "inputs": {"path": "x"}, "from_event": {"issue": "issue"}}
    await world.registered(bundle("refine", triggers=[refine]))
    await world.sent(opened())
    (started,) = await world.reactions.tick()
    assert started == run_id_of(TENANT, TRIAGE, "dlv_c1")
    assert await world.run(run_id_of(TENANT, "refine", "dlv_c1")) is None


async def test_the_triage_waits_while_no_version_is_active() -> None:
    world = Public()
    await world.sent(opened())
    assert await world.reactions.tick() == []
    assert await world.contributions() == 1, "it waits, it is not discarded"


async def test_a_contribution_received_before_the_version_was_active_starts_nothing() -> None:
    world = Public()
    await world.sent(opened())
    world.clock.current += timedelta(seconds=5)
    await world.registered(triage_bundle())
    assert await world.reactions.tick() == []
    assert await world.contributions() == 0
