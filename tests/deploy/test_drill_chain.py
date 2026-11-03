"""The drill's chain check recomputes the ledger by its published rule, without Taktus (ADR-0174 §3,
UC-10.5).

The backup program imports nothing of Taktus, so its walk of the chains is a second
implementation of the rule in `taktus.components.ledger`. These tests hold the two to each
other: on entries Taktus wrote into PostgreSQL — runs with their own chains, consumption,
anchors — and read back as the drill reads them, both find the chains intact; on every kind of
alteration, both find the same thing at the same entry.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fakes import FakeClock, FakeIdentifiers, FakeWorker
from fakes.maturity import VERIFIED
from sqlalchemy import text

from deploy.backup_program import backup
from taktus.adapters.driven.memory import MemoryObjectStore
from taktus.adapters.driven.postgres import (
    PostgresLedgerStore,
    PostgresPersistence,
    PostgresProvenanceStore,
    PostgresRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.ledger.domain.model import chain
from taktus.components.run.application.service import EngineOptions, RunEngine, StartRun
from taktus.components.run.domain.model import Run
from taktus.ports.ledger import Fact
from taktus.ports.worker import ComputeLimit, Limits
from taktus.shared.v1 import (
    Commissioned,
    ExactnessClass,
    Fallback,
    LedgerEntry,
    LedgerRefs,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    Step,
)

Row = dict[str, Any]


def test_the_program_hashes_every_field_the_entry_s_schema_has() -> None:
    """A field added to `LedgerEntry.json` must be added to the program, or its hashes differ."""
    assert set(backup.LEDGER_FIELDS) == set(LedgerEntry.model_fields)


@pytest.fixture
async def persistence(postgres_url: str) -> AsyncIterator[PostgresPersistence]:
    postgres = PostgresPersistence(postgres_url, pool_size=2)
    try:
        yield postgres
    finally:
        await postgres.close()


async def a_tenant(postgres: PostgresPersistence) -> str:
    tenant = f"t_drill_{os.urandom(4).hex()}"
    async with postgres.engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO tenant (id, name, created_at) VALUES (:t, :t, now())"), {"t": tenant}
        )
    return tenant


IDENTIFIERS: dict[str, FakeIdentifiers] = {}
"""One source of identifiers per tenant, so that a second batch of runs does not reuse one."""


async def runs(postgres: PostgresPersistence, tenant: str, count: int) -> None:
    """Runs of a rule and a worker step, as an instance runs them: each its own chain."""
    clock = FakeClock(datetime(2026, 10, 31, 9, 15, 30, 250_000, tzinfo=UTC))
    engine = RunEngine(
        maturities=VERIFIED,
        runs=PostgresRepository(postgres, Run),
        work=postgres,
        objects=MemoryObjectStore(),
        ledger=ChainedLedger(PostgresLedgerStore(postgres), clock),
        provenance=PostgresProvenanceStore(postgres),
        workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
        clock=clock,
        ids=IDENTIFIERS.setdefault(tenant, FakeIdentifiers()),
        telemetry=NoTelemetry(),
        options=EngineOptions(uncalibrated_margin=0.0),
    )
    steps = (
        Step(id="a", method=Method.RULE, reason="r", rejected=(), exactness=ExactnessClass.EXACT),
        Step(
            id="b",
            method=Method.WORKER,
            reason="r",
            rejected=(),
            exactness=ExactnessClass.TOLERANT,
            fallback=Fallback(when="x", to=Method.HUMAN),
            requires=("shell.script",),
            depends_on=("a",),
        ),
    )
    for n in range(count):
        plan = Plan(
            id=f"pln_{tenant}_{n}",
            command_id=f"cmd_{tenant}_{n}",
            goal="g",
            autonomy_level=3,
            steps=steps,
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by="idn_t", at=clock.now()),
        )
        await engine.start(
            StartRun(
                plan=plan,
                work={
                    "a": {"rule": "constant", "value": 42},
                    "b": {"task": {"goal": "g", "acceptance": ["a"]}},
                },
                budget=Limits(compute=ComputeLimit(seconds=10, resource_class="cpu.small")),
                process_version="p@1",
                actor="idn_t",
                tenant=tenant,
            )
        )


async def tenant_facts(postgres: PostgresPersistence, tenant: str, count: int) -> None:
    ledger = ChainedLedger(
        PostgresLedgerStore(postgres), FakeClock(datetime(2026, 10, 31, tzinfo=UTC))
    )
    async with postgres.transaction(tenant):
        for n in range(count):
            await ledger.record(
                tenant, Fact(kind="tenant.noted", refs=LedgerRefs(actor=f"idn_{n}"))
            )


async def anchor(postgres: PostgresPersistence, tenant: str) -> None:
    ledger = ChainedLedger(
        PostgresLedgerStore(postgres), FakeClock(datetime(2026, 10, 31, tzinfo=UTC))
    )
    async with postgres.transaction(tenant):
        assert await ledger.anchor(tenant) is not None


async def taktus_verifies(postgres: PostgresPersistence, tenant: str) -> tuple[int, bool]:
    ledger = ChainedLedger(PostgresLedgerStore(postgres), FakeClock())
    async with postgres.transaction(tenant):
        found = await ledger.verify(tenant, full=True)
    return found.entries, found.intact


async def rows_of(postgres: PostgresPersistence, tenant: str) -> list[Row]:
    """The tenant's entries exactly as the drill reads them: `to_jsonb` of each row, in UTC."""
    async with postgres.engine.connect() as connection:
        await connection.execute(text("SET TimeZone = 'UTC'"))
        result = await connection.execute(text(backup.LEDGER_ROWS))
        found = [row[0] for row in result]
    import json

    return [r for r in (json.loads(line) for line in found) if r["tenant"] == tenant]


def as_entries(rows: list[Row]) -> list[LedgerEntry]:
    """The same rows as Taktus's own model reads them."""
    return [LedgerEntry.model_validate(backup.entry_document(r)) for r in rows]


async def test_both_find_every_chain_intact_on_entries_taktus_wrote(
    persistence: PostgresPersistence,
) -> None:
    tenant = await a_tenant(persistence)
    await tenant_facts(persistence, tenant, 3)
    await runs(persistence, tenant, 3)
    await anchor(persistence, tenant)
    await runs(persistence, tenant, 2)
    await tenant_facts(persistence, tenant, 1)
    await anchor(persistence, tenant)

    rows = await rows_of(persistence, tenant)
    found = backup.verify_ledger(rows, wanted=[rows[4]["seq"]])

    assert await taktus_verifies(persistence, tenant) == (len(rows), True)
    assert found.findings == [] and found.entries == len(rows)
    assert sum(1 for r in rows if r["kind"] == backup.ANCHORED) == 2
    assert len({backup.chain_name(r) for r in rows}) == 6, "the tenant's chain and five runs'"
    assert any(r.get("consumption") for r in rows), "consumption is hashed as stored"
    assert found.head == (rows[-1]["seq"], rows[-1]["hash"])
    assert found.hashes == {rows[4]["seq"]: rows[4]["hash"]}
    # Every hash the program computes is the one Taktus's own rule computes.
    for entry, row in zip(as_entries(rows), rows, strict=True):
        assert backup.hash_of(backup.entry_document(row)) == chain.hash_of(entry) == entry.hash


def altered(rows: list[Row], index: int, **change: object) -> list[Row]:
    copy = [dict(r) for r in rows]
    copy[index].update(change)
    return copy


async def test_both_find_the_same_alteration_at_the_same_entry(
    persistence: PostgresPersistence,
) -> None:
    tenant = await a_tenant(persistence)
    await tenant_facts(persistence, tenant, 2)
    await runs(persistence, tenant, 2)
    rows = await rows_of(persistence, tenant)
    # An entry in the middle of its chain: removing a chain's last entry is what an anchor finds.
    middle = next(
        i for i in range(len(rows) // 2, len(rows))
        if any(backup.chain_name(r) == backup.chain_name(rows[i]) for r in rows[i + 1 :])
    )  # fmt: skip
    alterations = {
        "a field": altered(rows, middle, outcome="tampered"),
        "a time": altered(rows, middle, ts="2026-10-31T09:15:31+00:00"),
        "a removed entry": [r for i, r in enumerate(rows) if i != middle],
        "a re-hashed entry": altered(
            rows, middle, outcome="tampered", hash=chain.hash_of(
                as_entries(altered(rows, middle, outcome="tampered"))[middle]
            ),
        ),
    }  # fmt: skip
    for what, changed in alterations.items():
        program = backup.verify_ledger(changed).findings
        taktus = list(chain.verify(as_entries(changed)).findings)
        assert program, f"{what}: the program found nothing"
        assert program == taktus, what


async def test_an_anchor_that_does_not_match_its_heads_is_found(
    persistence: PostgresPersistence,
) -> None:
    tenant = await a_tenant(persistence)
    await runs(persistence, tenant, 3)
    await anchor(persistence, tenant)
    rows = await rows_of(persistence, tenant)
    [index] = [i for i, r in enumerate(rows) if r["kind"] == backup.ANCHORED]
    # A run chain's head altered and its own hash recomputed: every link holds, the anchor not.
    head = max(i for i, r in enumerate(rows[:index]) if backup.chain_name(r))
    changed = altered(rows, head, outcome="tampered")
    changed[head]["hash"] = backup.hash_of(backup.entry_document(changed[head]))
    following = [
        i for i in range(head + 1, len(changed))
        if backup.chain_name(changed[i]) == backup.chain_name(changed[head])
    ]  # fmt: skip
    assert following == [], "the head is its chain's last entry"

    findings = backup.verify_ledger(changed).findings

    expected = "the anchor does not match the heads of the run chains it covers"
    assert findings == [f"entry {rows[index]['seq']}: {expected}"]


def test_a_digest_taken_before_holds_the_restored_chain_to_it() -> None:
    chains = backup.Chains(entries=3, head=(9, "sha256:c"), hashes={5: "sha256:b"})
    assert (
        backup.held_to(chains, {"seq": 5, "hash": "sha256:b"}, {"seq": 9, "hash": "sha256:c"}) == []
    )
    assert backup.held_to(chains, {"seq": 5, "hash": "sha256:x"}, None) == [
        "the head taken before, entry 5, is not in the chain as it was"
    ]
    assert backup.held_to(chains, None, {"seq": 7, "hash": "sha256:a"}) == [
        "the newest entry is not entry 7 with the hash noted"
    ]
    missing = backup.Chains()
    assert backup.held_to(missing, {"seq": 1, "hash": "sha256:a"}, None) != []
