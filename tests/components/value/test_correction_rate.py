"""The measured correction rate is counted by the value ledger and carried by the exactness
statement (UC-6.9 §1, §3; ADR-0226; #224).

A result of a step that declares a check counts once it finished outside a rehearsal; it is
corrected once a person recorded `step.corrected` for it. The value component folds the ledger
into the figure, the process component writes it into the statement's residual risk, and the
view and the report read it from there and never compute it."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml
from fakes import FakeClock

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.process.domain.model.exactness import NONE_COUNTED, NOT_YET_MEASURED
from taktus.components.value.application.query import CorrectionRates
from taktus.components.value.domain.service.corrections import CORRECTIONS, Counted, fold
from taktus.composition.levels import VersionStatements, statement_of
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerRefs

ROOT = Path(__file__).resolve().parents[3]
BUNDLE = yaml.safe_load((ROOT / "examples" / "processes" / "six-times-seven.yaml").read_text())
TENANT = "default"
AT = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)


class World:
    def __init__(self) -> None:
        self.persistence = MemoryPersistence()
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), FakeClock(AT))
        self.rates = CorrectionRates(self.ledger, self.persistence)
        self.version = parse_bundle(BUNDLE)
        self.checked = [s.id for s in self.version.steps if s.checks]

    async def record(
        self, kind: str, run: str, step: str, outcome: str | None = None, *, rehearsal: bool = False
    ) -> None:
        async with self.persistence.transaction(TENANT):
            await self.ledger.record(
                TENANT,
                Fact(
                    kind=kind,
                    refs=LedgerRefs(
                        tenant=TENANT,
                        process_version=self.version.ref,
                        run_id=run,
                        step_id=step,
                        actor="idn_person",
                    ),
                    outcome=outcome,
                    rehearsal=True if rehearsal else None,
                ),
            )


async def test_the_value_ledger_counts_corrections_after_the_checks_passed_per_hundred() -> None:
    w = World()
    checked = w.checked[0]
    unchecked = next(s.id for s in w.version.steps if not s.checks and s.exactness is not None)
    for n in range(4):
        await w.record("step.finished", f"run_{n}", checked, "succeeded")
    await w.record("step.finished", "run_x", checked, "failed")
    await w.record("step.finished", "run_r", checked, "succeeded", rehearsal=True)
    await w.record("step.finished", "run_0", unchecked, "succeeded")
    await w.record("step.corrected", "run_1", checked)
    await w.record("step.corrected", "run_1", checked)  # corrected twice is one result
    await w.record("step.corrected", "run_0", unchecked)  # no check passed: not counted
    found = await w.rates.of(TENANT, w.version.ref, w.checked)
    assert (found.corrected, found.counted) == (1, 4)
    assert found.per_hundred == 25.0


def test_the_figure_keeps_no_person() -> None:
    state = Counted()
    dumped = CORRECTIONS.dump(state)
    assert set(dumped) == {"counted", "corrected"}
    assert fold(state, _entry()) is state


def _entry():  # type: ignore[no-untyped-def]
    from taktus.shared.v1 import LedgerEntry

    return LedgerEntry.model_construct(
        kind="step.finished",
        refs=LedgerRefs(tenant=TENANT),
        rehearsal=False,
        outcome="succeeded",
    )


async def test_the_statement_carries_the_measured_rate_and_says_so_while_none_counted() -> None:
    w = World()
    unmeasured = statement_of(w.version)
    assert unmeasured is not None and unmeasured.parts[3].lines[-1] == NOT_YET_MEASURED
    none = statement_of(w.version, (0, 0))
    assert none is not None and none.parts[3].lines[-1] == NONE_COUNTED
    measured = statement_of(w.version, (1, 4))
    assert measured is not None
    last = measured.parts[3].lines[-1]
    assert "1 of 4" in last and "25.0 per hundred" in last


async def test_a_report_reads_the_rate_the_value_ledger_counted() -> None:
    w = World()
    versions = MemoryRepository(w.persistence, ProcessVersion)
    async with w.persistence.transaction(TENANT):
        await versions.put(TENANT, w.version)
    for n in range(2):
        await w.record("step.finished", f"run_{n}", w.checked[0], "succeeded")
    await w.record("step.corrected", "run_0", w.checked[0])
    rendered = await VersionStatements(w.persistence, versions, w.rates).rendered(
        TENANT, w.version.ref
    )
    assert rendered is not None and "1 of 2" in rendered and "50.0 per hundred" in rendered
