"""The rules of the stream of changes, without a stream (ADR-0055 §3 to §6).

One predicate decides what a reader may see; a run it may not see is absent from a snapshot and
from the changes, and nothing counts it. A resume is a snapshot when the position is unknown or
too far behind. A projection keeps no person, no figure and no content.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from taktus.components.reporting.application.service import LiveChanges
from taktus.components.reporting.domain.model import (
    Reader,
    RunRef,
    Scope,
    ScopeKind,
    SnapshotRun,
    StateAfter,
)
from taktus.components.reporting.domain.service.live import (
    MAX_BEHIND,
    needs_snapshot,
    project,
)
from taktus.components.reporting.domain.service.visibility import may_see
from taktus.components.reporting.ports import TenantState
from taktus.shared.v1 import Consumption, LedgerEntry, Method

AT = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
ADA = Reader(tenant="acme", identity="idn_ada", roles=("finance.lead",))
MINE = RunRef(id="run_1", tenant="acme", process_version="invoices@1")
THEIRS = RunRef(id="run_9", tenant="beta", process_version="invoices@1")


def entry(seq: int, kind: str, run: str = "run_1", **fields: object) -> LedgerEntry:
    return LedgerEntry.model_validate(
        {
            "seq": seq,
            "ts": AT,
            "kind": kind,
            "prev_hash": None,
            "hash": "sha256:" + f"{seq:064x}",
            "refs": {"tenant": "acme", "run_id": run, "step_id": "a", "actor": "idn_ada"},
            **fields,
        }
    )


def shown(ref: RunRef) -> SnapshotRun:
    return SnapshotRun(id=ref.id, process_version=ref.process_version, state="running")


class Records:
    def __init__(self, entries: Sequence[LedgerEntry], runs: Sequence[RunRef]) -> None:
        self.entries = list(entries)
        self.known = {r.id: r for r in runs}

    async def state(self, tenant: str) -> TenantState:
        newest = self.entries[-1] if self.entries else None
        return TenantState(
            seq=0 if newest is None else newest.seq,
            position=None if newest is None else newest.hash,
            runs=[(r, shown(r)) for r in self.known.values()],
        )

    async def head(self, tenant: str) -> int:
        return self.entries[-1].seq if self.entries else 0

    async def position(self, tenant: str, hash: str) -> int | None:
        return next((e.seq for e in self.entries if e.hash == hash), None)

    async def after(self, tenant: str, seq: int, *, limit: int) -> Sequence[LedgerEntry]:
        return [e for e in self.entries if e.seq > seq][:limit]

    async def runs(self, tenant: str, ids: Sequence[str]) -> Mapping[str, RunRef]:
        return {i: self.known[i] for i in ids if i in self.known}


def states(kind: str, outcome: str | None) -> StateAfter | None:
    return StateAfter(step="running") if kind == "step.started" else None


def test_the_predicate_holds_the_tenant_boundary_until_the_views_exist() -> None:
    assert may_see(ADA, MINE)
    assert not may_see(ADA, THEIRS)


def test_a_projection_keeps_no_person_no_figure_and_no_content() -> None:
    change = project(
        entry(
            3,
            "step.started",
            method="worker",
            model="m@1",
            adapter="worker.http",
            consumption=Consumption(compute_seconds=2, resource_class="cpu.small").document(),
            content_digest="sha256:" + "f" * 64,
        ),
        StateAfter(step="running"),
    )
    assert change is not None
    document = change.document()
    assert document["method"] == Method.WORKER
    for absent in ("idn_ada", "worker.http", "m@1", "cpu.small", "f" * 64):
        assert absent not in str(document)


def test_a_resume_is_a_snapshot_when_unknown_or_too_far_behind() -> None:
    assert needs_snapshot(None, 5)
    assert needs_snapshot(1, 2 + MAX_BEHIND)
    assert not needs_snapshot(1, 1 + MAX_BEHIND)


async def test_a_run_the_reader_may_not_see_is_absent_from_snapshot_and_changes() -> None:
    records = Records(
        [entry(1, "step.started"), entry(2, "step.started", run="run_9")], [MINE, THEIRS]
    )
    live = LiveChanges(records, states)
    opening = await live.open(ADA, Scope(kind=ScopeKind.TENANT), None)
    assert opening.snapshot is not None
    assert [r.id for r in opening.snapshot.runs] == ["run_1"]
    read = await live.read("acme", 0, limit=10)
    assert read.through == 2
    sent = live.visible(ADA, Scope(kind=ScopeKind.TENANT), read.pending)
    assert [c.run for c in sent] == ["run_1"]
    assert "run_9" not in str([c.document() for c in sent])
