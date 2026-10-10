"""Event reactions, made by the elected automation role (ADR-0048, UC-4.14), against PostgreSQL.

Two daemons with the `automation` role run in this process, as in `test_time_triggers.py`. The
intake's part — an intake event kept with its outbox entry, in one transaction — is written here
directly, as `ReceiveIntakeHandler` writes it; that the intake writes it is held by
`tests/composition/test_reactions.py`. What is proven: an event starts exactly one run of the
process its trigger names, with two automation roles running; an entry left unpublished — a
leader that died before publishing — starts nothing twice; after the leader stops, the other
leads and reacts to the next event; every run carries `run.triggered` with the outcome `event`
and acts for the sender as placed.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from taktus.adapters.driven.postgres import PostgresOutbox, PostgresRepository
from taktus.components.command.domain.model import IntakeEvent
from taktus.components.run.domain.model import Run
from taktus.composition.daemon import Wired
from taktus.composition.reactions import run_id_of
from taktus.ports.outbox import INTAKE_ACCEPTED

from .test_daemon_scaling import rule_only_bundle
from .test_time_triggers import SETTLE, Daemon, ManualClock, daemons, eventually, registered, tenant

__all__ = ["daemons", "tenant"]  # the fixtures, used by name

ACCOUNT = "100200"


async def linked(wired: Wired, tenant: str) -> str:
    """A person of the tenant who linked account 100200 on the repository channel."""
    _, key = await wired.identities.add(tenant, "idn_ada", (tenant,))
    who = await wired.identities.authenticate(key)
    assert who is not None
    code, _ = await wired.identities.create_link_code(who, "channel.repo")
    answer = await wired.identities.unknown_sender("channel.repo", ACCOUNT, code)
    assert answer.linked is not None
    return who.identity


async def kept(wired: Wired, tenant: str, delivery: str, at: datetime) -> None:
    """What the intake keeps for a delivery, with its outbox entry, in one transaction."""
    event = IntakeEvent(
        id=delivery,
        tenant=tenant,
        channel="channel.repo",
        event="issue.labelled",
        sender_account=ACCOUNT,
        sender_kind="person",
        intent="Event reactions",
        context={"repository": "acme/taktus", "issue": "76", "label": "ready"},
        reply_channel="channel.repo",
        reply_address="acme/taktus#76",
        occurred_at=at,
        received_at=at,
    )
    async with wired.work.transaction(tenant):
        await PostgresRepository(wired.persistence, IntakeEvent).put(tenant, event)
        await PostgresOutbox(wired.persistence).write(
            tenant, INTAKE_ACCEPTED, {"event_id": delivery}
        )


async def runs_of(wired: Wired, tenant: str, ref: str) -> list[Run]:
    async with wired.work.transaction(tenant):
        return [run for run in await wired.runs.list(tenant) if run.process_version == ref]


async def pending(wired: Wired, tenant: str) -> int:
    async with wired.work.transaction(tenant):
        return len(await PostgresOutbox(wired.persistence).unpublished(tenant, INTAKE_ACCEPTED, 99))


def event_bundle(tenant: str) -> dict[str, Any]:
    document = rule_only_bundle(0)
    document["id"] = f"implement-{tenant}"
    document["inputs"] = {"issue": {"description": "the issue", "example": 11}}
    document["triggers"] = [
        {"event": "issue.labelled", "filter": {"label": "ready"}, "from_event": {"issue": "issue"}}
    ]
    return document


async def test_an_event_starts_exactly_one_run_whoever_reacts(
    daemons: Callable[..., Daemon], tenant: str
) -> None:
    clock = ManualClock(datetime(2026, 10, 10, 9, 0, tzinfo=UTC))
    a = await daemons("automation-a", clock, TAKTUS_ROLES="automation").start()
    b = await daemons("automation-b", clock, TAKTUS_ROLES="automation").start()
    assert a.wired is not None
    wired = a.wired
    sender = await linked(wired, tenant)
    version = await registered(wired, tenant, event_bundle(tenant))
    process = version.process_id

    clock.current += timedelta(minutes=1)
    await kept(wired, tenant, "dlv_1", clock.now())
    await eventually(lambda: _count(wired, tenant, version.ref, 1))
    await eventually(lambda: _none_pending(wired, tenant))
    (run,) = await runs_of(wired, tenant, version.ref)
    assert run.id == run_id_of(tenant, process, "dlv_1")
    assert run.identity == sender and run.inputs == {"issue": 76}
    async with wired.work.transaction(tenant):
        entries = await wired.ledger.entries(tenant, run.id)
    assert [e.kind for e in entries][:2] == ["run.created", "run.triggered"]
    assert entries[1].outcome == "event"

    # A leader that died before publishing leaves the entry for the next: nothing twice.
    async with wired.work.transaction(tenant):
        await PostgresOutbox(wired.persistence).write(
            tenant, INTAKE_ACCEPTED, {"event_id": "dlv_1"}
        )
    await eventually(lambda: _none_pending(wired, tenant))
    await asyncio.sleep(SETTLE)
    assert [r.id for r in await runs_of(wired, tenant, version.ref)] == [run.id]

    # One of them stops; whichever led, the other leads now and reacts to the next event, once.
    await a.halt()
    assert b.wired is not None
    wired = b.wired
    clock.current += timedelta(minutes=1)
    await kept(wired, tenant, "dlv_2", clock.now())
    await eventually(lambda: _count(wired, tenant, version.ref, 2), seconds=60)
    await asyncio.sleep(SETTLE)
    assert len(await runs_of(wired, tenant, version.ref)) == 2
    async with wired.work.transaction(tenant):
        assert (await wired.ledger.verify(tenant)).intact


async def _count(wired: Wired, tenant: str, ref: str, n: int) -> bool:
    return len(await runs_of(wired, tenant, ref)) == n


async def _none_pending(wired: Wired, tenant: str) -> bool:
    return await pending(wired, tenant) == 0
