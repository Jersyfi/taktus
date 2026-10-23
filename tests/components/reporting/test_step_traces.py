"""A step's trace is kept for its tenant's retention and then erased (ADR-0135 §5, UC-6.14).

The retention is the default until the tenant sets one, and setting it is a ledger entry with
who set it. Once a line is older than the retention, the scheduler's look erases it, and the
erasure is a ledger entry that says nothing a line said; a line within the retention is kept.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryTraceStore
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.reporting.application.service import StepTraces
from taktus.components.reporting.domain.model import RunFacts
from taktus.composition.traces import traces_tick
from taktus.ports.traces import DEFAULT_RETENTION_DAYS, TraceLine

TENANT = "t"
NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


class StillClock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def now(self) -> datetime:
        return self.at

    async def sleep(self, seconds: float) -> None:
        self.at += timedelta(seconds=seconds)


class NoRuns:
    """The run level's records; the retention reads none of them."""

    async def run(self, tenant: str, run_id: str) -> RunFacts | None:
        return None


class Served:
    async def served(self) -> tuple[str, ...]:
        return (TENANT,)


def line(seq: int, recorded_at: datetime) -> TraceLine:
    return TraceLine(
        run_id="run_1",
        step_id="w",
        assignment_id="asg_1",
        seq=seq,
        ts=recorded_at,
        type="step.progress",
        detail={"step_id": "s", "message": f"said {seq}"},
        recorded_at=recorded_at,
    )


def world() -> tuple[StepTraces, MemoryPersistence, MemoryTraceStore, ChainedLedger, StillClock]:
    persistence = MemoryPersistence()
    clock = StillClock(NOW)
    ledger = ChainedLedger(MemoryLedgerStore(persistence), clock)
    store = MemoryTraceStore(persistence)
    traces = StepTraces(
        records=NoRuns(),  # type: ignore[arg-type]
        traces=store,
        work=persistence,
        ledger=ledger,
        clock=clock,
    )
    return traces, persistence, store, ledger, clock


async def kept(persistence: MemoryPersistence, store: MemoryTraceStore) -> list[int]:
    async with persistence.transaction(TENANT):
        return [x.seq for x in await store.lines(TENANT, "run_1", "w", limit=100)]


async def test_a_line_past_the_default_retention_is_erased_and_a_newer_one_kept() -> None:
    traces, persistence, store, ledger, _ = world()
    async with persistence.transaction(TENANT):
        await store.append(TENANT, line(1, NOW - timedelta(days=DEFAULT_RETENTION_DAYS + 1)))
        await store.append(TENANT, line(2, NOW - timedelta(days=DEFAULT_RETENTION_DAYS - 1)))

    assert (await traces.retention(TENANT)).days == DEFAULT_RETENTION_DAYS
    assert await traces.erase(TENANT) == 1
    assert await kept(persistence, store) == [2]

    async with persistence.transaction(TENANT):
        entries = await ledger.entries(TENANT)
    (erased,) = [e for e in entries if e.kind == "trace.erased"]
    assert erased.outcome == "retention" and "said" not in erased.model_dump_json()


async def test_a_retention_the_tenant_sets_is_recorded_and_erases_by_it() -> None:
    traces, persistence, store, ledger, _ = world()
    async with persistence.transaction(TENANT):
        await store.append(TENANT, line(1, NOW - timedelta(days=8)))
        await store.append(TENANT, line(2, NOW - timedelta(days=6)))

    retention = await traces.set_retention(TENANT, 7, by="idn_ada")
    assert retention.days == 7 and retention.configured_at == NOW
    assert await traces.erase(TENANT) == 1
    assert await kept(persistence, store) == [2]
    assert await traces.erase(TENANT) == 0, "nothing more to erase, and no entry for it"

    async with persistence.transaction(TENANT):
        entries = await ledger.entries(TENANT)
    kinds = [(e.kind, e.refs.actor) for e in entries]
    assert kinds == [("trace.retention_configured", "idn_ada"), ("trace.erased", None)]


async def test_the_scheduler_erases_once_an_interval_for_every_tenant_it_serves() -> None:
    traces, persistence, store, _, clock = world()
    tick = traces_tick(traces, Served(), clock, interval_seconds=3600)
    async with persistence.transaction(TENANT):
        await store.append(TENANT, line(1, NOW - timedelta(days=DEFAULT_RETENTION_DAYS - 1)))

    await tick()
    assert await kept(persistence, store) == [1], "within its retention"

    clock.at = NOW + timedelta(days=2)
    await tick()
    assert await kept(persistence, store) == [], "its retention ended a day ago"
