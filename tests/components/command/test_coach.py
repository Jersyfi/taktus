"""The automation coach: hints from a person's own requests, theirs alone (ADR-0240, UC-13.3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fakes import FakeClock

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.command.application.service.coach import Coach, CoachError
from taktus.components.command.domain.model.coach import (
    DEFAULT_HINTS_PER_WEEK,
    CoachHint,
    CoachPolicy,
    CoachSettings,
    HintState,
)
from taktus.components.ledger.application.service import ChainedLedger
from taktus.ports.ledger import Fact
from taktus.shared.v1 import Command, Intent, LedgerRefs, ReplyTo

TENANT = "acme"
MONDAY = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)


class Harness:
    def __init__(self) -> None:
        self.persistence = MemoryPersistence()
        self.clock = FakeClock(MONDAY - timedelta(days=1))
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.commands = MemoryRepository(self.persistence, Command)
        self.policies = MemoryRepository(self.persistence, CoachPolicy)
        self.coach = Coach(
            MemoryRepository(self.persistence, CoachSettings),
            MemoryRepository(self.persistence, CoachHint),
            self.policies,
            self.commands,
            self.ledger,
            self.persistence,
            self.clock,
        )
        self.n = 0

    async def asks(self, identity: str, text: str, at: datetime) -> None:
        self.n += 1
        async with self.persistence.transaction(TENANT):
            await self.commands.put(
                TENANT,
                Command(
                    id=f"cmd_{self.n}",
                    channel="channel.chat",
                    identity=identity,
                    org_path=(TENANT,),
                    intent=Intent(raw=text),
                    reply_to=ReplyTo(channel="channel.chat", address="C1"),
                    received_at=at,
                ),
            )

    async def every_monday(self, identity: str, text: str, weeks: int = 3) -> None:
        for week in range(weeks):
            await self.asks(identity, text, MONDAY + timedelta(weeks=week))


async def test_a_hint_is_drawn_from_the_persons_own_requests_and_shown_to_them_only() -> None:
    h = Harness()
    await h.coach.settings(TENANT, "idn_ada")
    await h.coach.settings(TENANT, "idn_bo")
    await h.every_monday("idn_ada", "Summarise the open invoices")
    h.clock.current = MONDAY + timedelta(weeks=3)
    [hint] = await h.coach.hints(TENANT, "idn_ada")
    assert "every Monday" in hint.says and "summarise the open invoices" in hint.says
    assert await h.coach.hints(TENANT, "idn_bo") == [], "nothing of another person's"
    with pytest.raises(CoachError):
        await h.coach.dismiss(TENANT, "idn_bo", hint.id)


async def test_the_person_sets_how_many_hints_a_week_and_a_dismissed_one_never_returns() -> None:
    h = Harness()
    settings = await h.coach.settings(TENANT, "idn_ada")
    assert settings.hints_per_week == DEFAULT_HINTS_PER_WEEK == 1, "the default, stated"
    await h.every_monday("idn_ada", "summarise the open invoices")
    await h.every_monday("idn_ada", "list the late deliveries")
    h.clock.current = MONDAY + timedelta(weeks=3)
    assert len(await h.coach.hints(TENANT, "idn_ada")) == 1, "one a week by default"
    await h.coach.set(TENANT, "idn_ada", on=True, hints_per_week=0)
    first = await h.coach.hints(TENANT, "idn_ada")
    assert len(first) == 1, "none new at zero; the one offered stays"
    await h.coach.dismiss(TENANT, "idn_ada", first[0].id)
    await h.coach.set(TENANT, "idn_ada", on=True, hints_per_week=7)
    h.clock.current += timedelta(weeks=1)
    again = await h.coach.hints(TENANT, "idn_ada")
    assert [x.pattern for x in again] != [first[0].pattern]
    assert first[0].pattern not in {x.pattern for x in again}, "a dismissed pattern stays gone"


async def test_switching_the_coach_off_is_one_setting_and_stops_reading_requests() -> None:
    h = Harness()
    await h.coach.settings(TENANT, "idn_ada")
    off = await h.coach.set(TENANT, "idn_ada", on=False)
    assert not off.on and off.observed_since is None
    await h.every_monday("idn_ada", "summarise the open invoices")
    h.clock.current = MONDAY + timedelta(weeks=3)
    assert await h.coach.hints(TENANT, "idn_ada") == []
    on = await h.coach.set(TENANT, "idn_ada", on=True)
    assert on.observed_since is not None and on.observed_since > MONDAY + timedelta(weeks=2)
    assert await h.coach.hints(TENANT, "idn_ada") == [], "what was asked while off is never read"


async def test_whether_an_accepted_hint_lasted_is_shown_to_the_person_and_to_others_by_role() -> (
    None
):
    h = Harness()
    for person in ("idn_ada", "idn_bo"):
        await h.coach.settings(TENANT, person)
        await h.every_monday(person, f"report of {person[-2:]}")
    h.clock.current = MONDAY + timedelta(weeks=3)
    [ada] = await h.coach.hints(TENANT, "idn_ada")
    [bo] = await h.coach.hints(TENANT, "idn_bo")
    await h.coach.accept(TENANT, "idn_ada", ada.id, "report@1")
    await h.coach.accept(TENANT, "idn_bo", bo.id, "other@1")
    async with h.persistence.transaction(TENANT):
        await h.policies.put(TENANT, CoachPolicy(id=TENANT, lasting_days=14))
    h.clock.current += timedelta(days=13)
    async with h.persistence.transaction(TENANT):
        await h.ledger.record(
            TENANT,
            Fact(
                kind="run.created",
                refs=LedgerRefs(tenant=TENANT, run_id="run_9", process_version="report@1"),
            ),
        )
    h.clock.current += timedelta(days=2)
    checked = await h.coach.check_lasting(TENANT)
    assert {c.process_version: c.lasting for c in checked} == {"report@1": True, "other@1": False}
    assert await h.coach.own_share(TENANT, "idn_ada") == (1, 1)
    assert await h.coach.own_share(TENANT, "idn_bo") == (0, 1)
    by_role = await h.coach.share_by_role(TENANT, {"idn_ada": "finance", "idn_bo": "finance"})
    assert by_role == {"finance": (1, 2)}, "aggregated by role, never by person"


async def test_what_the_coach_passes_on_describes_a_procedure_and_belongs_to_the_person() -> None:
    h = Harness()
    await h.coach.settings(TENANT, "idn_ada")
    await h.every_monday("idn_ada", "summarise the open invoices")
    h.clock.current = MONDAY + timedelta(weeks=3)
    [hint] = await h.coach.hints(TENANT, "idn_ada")
    draft = await h.coach.procedure(TENANT, "idn_ada", hint.id)
    assert draft.owner == "idn_ada"
    assert draft.procedure == 'every Monday: "summarise the open invoices"'
    assert "idn_ada" not in draft.procedure and "idn_ada" not in hint.says
    assert hint.state is HintState.OFFERED
