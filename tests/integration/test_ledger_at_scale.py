"""No read on a hot path reads a tenant's whole ledger (issue #321, ADR-0105).

A tenant's ledger holds 500 000 entries: runs of six entries each, one step admitted and
finished per run, through five adapters, ten steps and four processes. That is 83 333
observations of estimate and actual. A daemon serving the `api` role answers from it, in this
process.

The seeded entries are written by the database, with placeholder hashes. They stand for a
history a verification walked earlier. The test sets the checkpoint at the last of them, as that
verification would have. Every entry recorded after it is linked and hashed by the ledger, so the
walk from the checkpoint verifies.

On 2026-10-12 a run start's calibration took 23.6 s at this size, and `GET /runs/{id}/ledger`
26.2 s (docs/research/2026-10-12-devops-review.md §L2). The bounds are the issue's: under 50 ms
and under 200 ms. The first read of the calibration after the seeding builds the projection from
every entry once; its time is printed, not bounded.
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import text

from taktus.adapters.driven.postgres import PostgresProjectionStore
from taktus.adapters.driven.postgres import _schema as schema
from taktus.components.accounting.application.service import TaktRateHandler, TaktRateOf
from taktus.components.ledger.application.service.chained_ledger import CHECKPOINT
from taktus.components.process.domain.service.quality import QUALITY
from taktus.components.run.application.query import StepMeasures
from taktus.components.run.domain.model import Run, RunState
from taktus.components.run.domain.service.projections import CALIBRATION
from taktus.composition.daemon import Wired
from taktus.composition.settings import weighting_table_in_force
from taktus.ports.ledger import Fact
from taktus.ports.persistence import Projected
from taktus.ports.worker import ComputeLimit, Limits
from taktus.shared.v1 import Consumption, ExactnessClass, LedgerRefs, Method, Rejected, Step

from .test_daemon_scaling import Instance, instances
from .test_live_changes import chosen, reader_key

__all__ = ["chosen", "instances"]

ENTRIES = 500_000
AT = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)
CALIBRATION_SECONDS = 0.05
LEDGER_SECONDS = 0.2
REMAINING_SECONDS = 0.2
LEDGER_READS = 5
KINDS = (
    "ARRAY['run.created','run.started','step.admitted','step.started','step.finished',"
    "'run.finished']"
)


def placeholder(n: str) -> str:
    """A hash of the right shape for entry `n`: `sha256:` and 64 hex digits."""
    return f"'sha256:' || lpad(to_hex({n}), 64, '0')"


async def seed(wired: Wired, tenant: str) -> float:
    """500 000 entries, written by the database in one statement; the seconds it took."""
    run = "((n - 1) / 6)"
    kind = f"({KINDS})[(n - 1) % 6 + 1]"
    on_step = f"{kind} IN ('step.admitted', 'step.finished')"
    statement = f"""
        INSERT INTO ledger_entry (tenant, seq, ts, kind, prev_hash, hash, refs, method, adapter,
                                  consumption, outcome)
        SELECT :t, n, :at + n * interval '1 minute', {kind},
               CASE WHEN n = 1 THEN NULL ELSE {placeholder("n - 1")} END,
               {placeholder("n")},
               jsonb_strip_nulls(jsonb_build_object(
                   'run_id', 'run_' || {run},
                   'step_id', CASE WHEN {kind} LIKE 'step.%' THEN 'step-' || {run} % 10 END,
                   'process_version', 'seeded-' || {run} % 4 || '@1')),
               CASE WHEN {on_step} THEN 'worker' END,
               CASE WHEN {on_step} THEN 'worker.seeded-' || {run} % 5 END,
               CASE WHEN {kind} = 'step.admitted'
                    THEN jsonb_build_object('tokens_in', 100, 'tokens_out', 50)
                    WHEN {kind} = 'step.finished'
                    THEN jsonb_build_object('tokens_in', 80 + {run} % 37,
                                            'tokens_out', 30 + {run} % 29) END,
               CASE WHEN {kind} = 'step.finished' THEN 'succeeded' END
        FROM generate_series(1, {ENTRIES}) AS n
    """  # noqa: S608 — every name and number is a constant of this file
    started = time.perf_counter()
    async with wired.persistence.engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('taktus.tenant', :t, true)"), {"t": tenant}
        )
        await connection.execute(text(statement), {"t": tenant, "at": AT})
    async with wired.persistence.engine.begin() as connection:
        await connection.execute(text("ANALYZE ledger_entry"))
    return time.perf_counter() - started


async def checkpointed(wired: Wired, tenant: str) -> None:
    """The checkpoint at the last seeded entry, as the verification that walked them set it."""
    hash = "sha256:" + format(ENTRIES, "x").rjust(64, "0")
    async with wired.work.transaction(tenant):
        await PostgresProjectionStore(wired.persistence).write(
            tenant, CHECKPOINT, Projected(seq=ENTRIES, state={"hash": hash}), replace=True
        )


async def run_of_ten_steps(wired: Wired, tenant: str) -> str:
    """A run the reader may see, with its entries recorded by the ledger after the seed."""
    steps = tuple(
        Step(
            id=f"step-{n}",
            method=Method.RULE,
            reason="a fixed rule",
            rejected=(Rejected(method=Method.LLM, why="nothing here needs judgement"),),
            exactness=ExactnessClass.EXACT,
        )
        for n in range(10)
    )
    run = Run(
        id="run_measured",
        plan_id="pln_0",
        process_version="seeded-0@1",
        tenant=tenant,
        identity="idn_t",
        autonomy_level=3,
        budget=Limits(compute=ComputeLimit(seconds=2, resource_class="cpu.small")),
        steps=steps,
        work={},
        state=RunState.FINISHED,
        created_at=AT,
        updated_at=AT,
    )
    async with wired.work.transaction(tenant):
        await wired.runs.put(tenant, run)
        await wired.ledger.record(tenant, Fact(kind="run.created", refs=LedgerRefs(run_id=run.id)))
        for step in steps:
            refs = LedgerRefs(run_id=run.id, step_id=step.id, process_version=run.process_version)
            for kind, used in (("step.admitted", 100), ("step.finished", 120)):
                await wired.ledger.record(
                    tenant,
                    Fact(
                        kind=kind,
                        refs=refs,
                        method=Method.WORKER,
                        adapter="worker.seeded-0",
                        consumption=Consumption(tokens_in=used, tokens_out=50),
                        outcome="succeeded" if kind == "step.finished" else None,
                    ),
                )
        await wired.ledger.record(
            tenant, Fact(kind="run.finished", refs=LedgerRefs(run_id=run.id), outcome="succeeded")
        )
    return run.id


async def plan(wired: Wired, tenant: str, where: str) -> str:
    """The plan PostgreSQL chooses for a read of the tenant's entries."""
    async with wired.persistence.engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('taktus.tenant', :t, true)"), {"t": tenant}
        )
        rows = await connection.execute(
            text(
                f"EXPLAIN SELECT * FROM ledger_entry WHERE tenant = :t AND {where} ORDER BY seq"  # noqa: S608 — constants of this file
            ),
            {"t": tenant},
        )
        return "\n".join(row[0] for row in rows)


@pytest.mark.timing
async def test_half_a_million_entries_cost_a_run_start_and_a_ledger_read_what_they_return(
    instances: Callable[..., Instance], chosen: str
) -> None:
    async with instances("ledger", TAKTUS_ROLES="api", TAKTUS_TENANTS=chosen) as one:
        assert one.wired is not None
        wired = one.wired
        took = await seed(wired, chosen)
        print(f"\nseeded {ENTRIES} entries in {took:.1f} s")
        await checkpointed(wired, chosen)

        # The first read after the seeding builds the projection from every entry, once.
        started = time.perf_counter()
        async with wired.work.transaction(chosen):
            first = await wired.ledger.project(chosen, CALIBRATION)
        print(f"the calibration projection built once: {time.perf_counter() - started:.2f} s")
        # A run's adapter, step and process follow from its number modulo 20: twenty keys.
        assert len(first.observations()) == 20 * 20, "the last twenty of each key"

        run_id = await run_of_ten_steps(wired, chosen)

        # A run start's calibration: what `RunEngine._execute` reads before the first step.
        started = time.perf_counter()
        observations = await wired.engine._observations(chosen)
        calibrating = time.perf_counter() - started
        print(f"a run start's calibration: {calibrating * 1000:.1f} ms")
        assert calibrating < CALIBRATION_SECONDS, calibrating
        async with wired.work.transaction(chosen):
            rebuilt = await wired.ledger.rebuilt(chosen, CALIBRATION)
        assert observations == rebuilt.observations(), "the projection equals its rebuild"

        key = await reader_key(wired, chosen)
        base = f"http://127.0.0.1:{one.settings.http_port}"
        headers = {"Authorization": f"Bearer {key}"}
        async with httpx.AsyncClient(base_url=base, timeout=120) as http:
            # The first request pays for the connection and the warm caches. The bound holds
            # for the request itself: the median of five, so that a parallel `make verify` stealing
            # the processor during one request does not fail the requirement (#528).
            answer = await http.get(f"/runs/{run_id}/ledger", headers=headers)
            # Later reads move the checkpoint on, so the first answer is the one inspected.
            timed: list[float] = []
            for _ in range(LEDGER_READS):
                started = time.perf_counter()
                again = await http.get(f"/runs/{run_id}/ledger", headers=headers)
                timed.append(time.perf_counter() - started)
                assert again.status_code == 200, again.text
        reading = statistics.median(timed)
        print(
            f"GET /runs/{{id}}/ledger: median {reading * 1000:.1f} ms of {LEDGER_READS}, "
            f"best {min(timed) * 1000:.1f} ms, worst {max(timed) * 1000:.1f} ms"
        )
        assert answer.status_code == 200, answer.text
        assert reading < LEDGER_SECONDS, timed
        body = answer.json()
        assert len(body["entries"]) == 22 and body["entries"][0]["kind"] == "run.created"
        assert body["chain"]["intact"] is True, body["chain"]
        assert body["chain"]["checkpoint"] == ENTRIES

        # The sweep every minute and the blocked time read their own kinds only.
        for kinds in ({"interface.failed"}, {"step.waited"}):
            started = time.perf_counter()
            async with wired.work.transaction(chosen):
                found = await wired.ledger.of_kinds(chosen, kinds)
            took = time.perf_counter() - started
            print(f"the entries of {sorted(kinds)}: {took * 1000:.1f} ms")
            assert found == []

        by_run = await plan(wired, chosen, "(refs ->> 'run_id') = 'run_measured'")
        assert "ledger_entry_run" in by_run, by_run
        by_kind = await plan(wired, chosen, "kind = 'interface.failed' AND seq > 0")
        assert "ledger_entry_kind" in by_kind, by_kind
        assert schema.ledger_entry.name == "ledger_entry"


class At:
    """A clock that stands still at a moment."""

    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def now(self) -> datetime:
        return self.moment


@pytest.mark.timing
async def test_the_remaining_whole_ledger_reads_cost_what_they_return(
    instances: Callable[..., Instance], chosen: str
) -> None:
    """The Takt rate, the measures of a step, the quality history of a raise and of a
    registration (ADR-0105 §9, issue #522), each over 500 000 entries, one per minute: the Takt
    rate reads the thirty days it rates, 7 200 finished steps of 83 333."""
    async with instances("ledger", TAKTUS_ROLES="api", TAKTUS_TENANTS=chosen) as one:
        assert one.wired is not None
        wired = one.wired
        await seed(wired, chosen)
        await checkpointed(wired, chosen)
        objects = wired.engine._objects
        now = AT + timedelta(minutes=ENTRIES)

        # The first read of a projection builds it from the entries of its kinds, once.
        started = time.perf_counter()
        async with wired.work.transaction(chosen):
            await wired.ledger.project(chosen, QUALITY)
        print(f"\nthe quality projection built once: {time.perf_counter() - started:.2f} s")

        async def timed_read(name: str, read: Callable[[], Awaitable[Any]]) -> Any:
            """The median of five, as the bound of the ledger route is measured (#528): the
            fastest would admit a read that is usually slower."""
            timed: list[float] = []
            for _ in range(LEDGER_READS):
                started = time.perf_counter()
                found = await read()
                timed.append(time.perf_counter() - started)
            reading = statistics.median(timed)
            print(
                f"{name}: median {reading * 1000:.1f} ms of {LEDGER_READS}, "
                f"best {min(timed) * 1000:.1f} ms, worst {max(timed) * 1000:.1f} ms"
            )
            assert reading < REMAINING_SECONDS, (name, timed)
            return found

        async def quality() -> Any:
            async with wired.work.transaction(chosen):
                return (await wired.ledger.project(chosen, QUALITY)).history("seeded-0")

        async def rate() -> Any:
            handler = TaktRateHandler(
                wired.ledger, objects, wired.work, At(now), weighting_table_in_force()
            )
            return await handler.execute(TaktRateOf(chosen))

        async def measures() -> Any:
            return await StepMeasures(wired.runs, wired.ledger, objects, wired.work).steps(chosen)

        history = await timed_read("the quality history of a raise or a registration", quality)
        taken = await timed_read("the Takt rate", rate)
        await timed_read("the measures of the steps", measures)

        # Each equals what every entry gives.
        async with wired.work.transaction(chosen):
            rebuilt = await wired.ledger.rebuilt(chosen, QUALITY)
        assert rebuilt.history("seeded-0") == history
        assert history.ended == ENTRIES // 6 // 4 + 1 and history.clean == history.ended
        assert taken.runs == 30 * 24 * 60 // 6 and taken.window_days == 30
        plan_ts = await plan(
            wired,
            chosen,
            f"kind = 'step.finished' AND ts >= '{(now - timedelta(days=30)).isoformat()}'",
        )
        assert "ledger_entry_kind_ts" in plan_ts, plan_ts
