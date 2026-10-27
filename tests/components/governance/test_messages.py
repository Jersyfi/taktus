"""A tenant's rules for outward messages, and the cases a person answered in: kept, changed and
recorded, and read by the run through its port (ADR-0142, UC-7.6; NTC-0234)."""

from __future__ import annotations

from datetime import UTC, datetime, time

import pytest
from fakes import FakeClock
from pydantic import ValidationError

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.governance.application.service import ConfigureMessages, TenantMessages
from taktus.components.governance.application.service.messages import UNSET
from taktus.components.governance.domain.model import CaseAnswer, MessageRules, shipped_rules
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.run.domain.service import messages as run_messages
from taktus.components.run.ports import QuietHours
from taktus.composition.decisions import MessagesOfTheRun

AT = datetime(2026, 10, 23, 9, 0, tzinfo=UTC)
TENANT = "t"
LABEL = "Written by an AI system."


def kept() -> tuple[TenantMessages, ChainedLedger, MemoryPersistence]:
    clock = FakeClock(AT)
    persistence = MemoryPersistence()
    ledger = ChainedLedger(MemoryLedgerStore(persistence), clock)
    service = TenantMessages(
        MemoryRepository(persistence, MessageRules),
        MemoryRepository(persistence, CaseAnswer),
        ledger,
        persistence,
        clock,
    )
    return service, ledger, persistence


async def kinds(ledger: ChainedLedger, persistence: MemoryPersistence) -> list[str]:
    async with persistence.transaction(TENANT):
        return [f"{e.kind}:{e.refs.actor}" for e in await ledger.entries(TENANT)]


async def test_a_tenant_that_configured_nothing_holds_the_shipped_rules_the_run_holds() -> None:
    service, _, _ = kept()
    rules = await service.rules(TENANT)
    assert rules == shipped_rules(TENANT) and rules.label is None
    assert await MessagesOfTheRun(service).rules(TENANT) == run_messages.SHIPPED


async def test_rules_are_changed_recorded_and_read_by_the_run() -> None:
    service, ledger, persistence = kept()
    await service.configure(
        ConfigureMessages(
            tenant=TENANT,
            label=LABEL,
            delay_seconds=900,
            quiet=(time(22, 0), time(7, 0)),
            zone="Europe/Berlin",
            recipient_limit=3,
        ),
        by="op",
    )
    read = await MessagesOfTheRun(service).rules(TENANT)
    assert read.label == LABEL and read.delay_seconds == 900 and read.recipient_limit == 3
    assert read.quiet == QuietHours(begins=time(22, 0), ends=time(7, 0), zone="Europe/Berlin")
    assert "messages.configured:op" in await kinds(ledger, persistence)
    taken = await service.configure(
        ConfigureMessages(tenant=TENANT, label=UNSET, quiet=UNSET), by="op"
    )
    assert taken.label is None and taken.quiet_begins is None and taken.delay_seconds == 900


async def test_rules_that_cannot_hold_are_refused_and_change_nothing() -> None:
    with pytest.raises(ValidationError, match="different times"):
        MessageRules(id=TENANT, tenant=TENANT, quiet_begins=time(7), quiet_ends=time(7))
    service, _, _ = kept()
    for wrong in (
        ConfigureMessages(tenant=TENANT, zone="Mars/Olympus"),
        ConfigureMessages(tenant=TENANT, recipient_limit=0),
        ConfigureMessages(tenant=TENANT, delay_seconds=-1),
        ConfigureMessages(tenant=TENANT, label="   "),
    ):
        with pytest.raises(ValueError):
            await service.configure(wrong, by="op")
    assert await service.rules(TENANT) == shipped_rules(TENANT)


async def test_a_person_s_answer_in_a_case_is_recorded_once_for_its_process() -> None:
    service, ledger, persistence = kept()
    port = MessagesOfTheRun(service)
    assert not await port.answered(TENANT, "support", "T-17")
    first = await service.answer(TENANT, "support", "T-17", by="op")
    again = await service.answer(TENANT, "support", "T-17", by="other")
    assert first == again
    assert await port.answered(TENANT, "support", "T-17")
    assert not await port.answered(TENANT, "support", "T-18")
    assert not await port.answered(TENANT, "billing", "T-17")
    assert (await kinds(ledger, persistence)).count("case.answered:op") == 1
