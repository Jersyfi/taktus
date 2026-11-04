"""A result a person corrected is assessed by itself and raised as a result defect, and the
defect counts in the process's quality history (#92, #645, ADR-0184), over the memory stores.

The provenance records and ledger entries are `tests/governance/test_result_defects.py`'s:
five daily runs of `billing`, the partner's adapter a new version from run r3.
"""

from __future__ import annotations

from datetime import timedelta

from fakes.clock import FakeClock
from governance.test_result_defects import AT, RECORDS, TENANT

from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.components.governance.application.service import ResultDefects
from taktus.components.governance.domain.model.anchors import AnchorConfiguration
from taktus.components.governance.domain.model.incident import (
    Incident,
    IncidentKind,
    WatchConfiguration,
)
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.domain.service.autonomy import history
from taktus.composition.defects import DefectWatch
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerEntry, LedgerRefs


class World:
    def __init__(self) -> None:
        self.persistence = MemoryPersistence()
        self.clock = FakeClock(AT + timedelta(days=6))
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.provenance = MemoryProvenanceStore(self.persistence)
        self.incidents = MemoryRepository(self.persistence, Incident)
        self.watch = DefectWatch(
            self.ledger,
            ResultDefects(
                self.provenance,
                self.ledger,
                self.incidents,
                MemoryRepository(self.persistence, WatchConfiguration),
                MemoryRepository(self.persistence, AnchorConfiguration),
                self.persistence,
                self.clock,
            ),
            self.persistence,
        )

    async def ran(self) -> None:
        async with self.persistence.transaction(TENANT):
            for r in RECORDS:
                refs = LedgerRefs(
                    tenant=TENANT,
                    run_id=r.run_id,
                    step_id=r.step_id,
                    process_version=r.process_version,
                )
                if r.step_id in ("import", "report"):
                    await self.ledger.record(
                        TENANT,
                        Fact(kind="run.created", refs=refs.model_copy(update={"step_id": None})),
                    )
                await self.ledger.record(
                    TENANT, Fact(kind="step.finished", refs=refs, outcome="succeeded")
                )
                if r.step_id in ("invoice", "report"):
                    await self.ledger.record(
                        TENANT,
                        Fact(
                            kind="run.finished",
                            refs=refs.model_copy(update={"step_id": None}),
                            outcome="succeeded",
                        ),
                    )
                await self.provenance.append(TENANT, r)

    async def corrected(self, run_id: str, step_id: str, *, rehearsal: bool = False) -> None:
        async with self.persistence.transaction(TENANT):
            await self.ledger.record(
                TENANT,
                Fact(
                    kind="step.corrected",
                    refs=LedgerRefs(
                        tenant=TENANT,
                        run_id=run_id,
                        step_id=step_id,
                        process_version="billing@1",
                        actor="idn_corrector",
                    ),
                    rehearsal=True if rehearsal else None,
                ),
            )

    async def entries(self) -> list[LedgerEntry]:
        async with self.persistence.transaction(TENANT):
            return list(await self.ledger.entries(TENANT))


async def test_a_correction_is_assessed_by_itself_and_raised_once() -> None:
    w = World()
    await w.ran()
    await w.corrected("r4", "import")
    (raised,) = await w.watch.sweep(TENANT)
    async with w.persistence.transaction(TENANT):
        incident = await w.incidents.get(TENANT, raised)
    assert incident is not None and incident.kind is IncidentKind.RESULT_DEFECT
    assert incident.facts["found"] == "corrected" and incident.facts["cause"] == "adapter_version"
    assert await w.watch.sweep(TENANT) == [], "a correction answered is not raised again"
    raised_entries = [e for e in await w.entries() if e.kind == "incident.raised"]
    assert len(raised_entries) == 1 and raised_entries[0].refs.actor is None


async def test_a_rehearsal_or_a_result_without_a_record_is_not_raised() -> None:
    w = World()
    await w.ran()
    await w.corrected("r2", "import", rehearsal=True)
    await w.corrected("r9", "import")
    assert await w.watch.sweep(TENANT) == []


async def test_the_raised_defect_ends_the_clean_row_of_the_quality_history() -> None:
    """#645: a raise of the level reads the history; a run found wrong after it ended counts."""
    w = World()
    await w.ran()
    before = history(await w.entries(), "billing")
    assert (before.clean, before.last_failed) == (5, None)
    await w.corrected("r4", "import")
    await w.watch.sweep(TENANT)
    after = history(await w.entries(), "billing")
    assert (after.clean, after.ended, after.last_failed) == (1, 5, "r4")
