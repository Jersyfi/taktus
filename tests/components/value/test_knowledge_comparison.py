"""The same work with and without a knowledge source connected, compared on the value ledger's
figures (UC-5.5 §2, ADR-0291).

A run is with knowledge where a connector answered one of its knowledge reads, and without
where a person did or nobody did. Each side gets the cockpit's figures; the difference is with
less without. A side without an ended run withholds its figures and the difference, never zero.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fakes import FakeClock

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.value.domain.model import Figure
from taktus.components.value.domain.service import knowledge
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerEntry, LedgerRefs, Method

TENANT = "default"
START = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)
SINCE = datetime(2026, 11, 1, tzinfo=UTC)
UNTIL = datetime(2026, 11, 8, tzinfo=UTC)
VERSION = "answer@1"
WORK: dict[str, Any] = {
    "search": {"rule": "connector", "operation": "knowledge.documents.search"},
    "answer": {"purpose": "support", "prompt": "…"},
    "confirm": {"rule": "connector", "operation": "knowledge.documents.versions"},
    "cite": {"rule": "citation", "capability": "knowledge.documents"},
    "post": {"rule": "connector", "operation": "channel.chat.post"},
}


class World:
    def __init__(self) -> None:
        self.persistence = MemoryPersistence()
        self.clock = FakeClock(START)
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)

    async def fact(self, kind: str, run: str, **given: Any) -> None:
        step = given.pop("step", None)
        async with self.persistence.transaction(TENANT):
            await self.ledger.record(
                TENANT,
                Fact(
                    kind=kind,
                    refs=LedgerRefs(
                        tenant=TENANT, process_version=VERSION, run_id=run, step_id=step
                    ),
                    **given,
                ),
            )

    async def run(
        self, name: str, *, served: bool, seconds: int, ends: str = "run.finished"
    ) -> None:
        await self.fact("run.created", name)
        self.clock.current += timedelta(seconds=seconds)
        if served:
            await self.fact(
                "step.finished",
                name,
                step="search",
                outcome="succeeded",
                method=Method.RULE,
                adapter="connector.knowledge",
            )
        else:
            await self.fact(
                "step.finished", name, step="search", outcome="succeeded", method=Method.HUMAN
            )
        await self.fact(
            "step.finished",
            name,
            step="post",
            outcome="succeeded",
            method=Method.RULE,
            adapter="connector.chat",
        )
        await self.fact(ends, name)

    async def entries(self) -> list[LedgerEntry]:
        async with self.persistence.transaction(TENANT):
            return list(await self.ledger.of_kinds(TENANT, knowledge.KINDS))


def by_id(figures: list[Figure]) -> dict[str, Figure]:
    return {f.id: f for f in figures}


def test_a_versions_knowledge_reads_are_the_connector_calls_of_the_capability_it_cites() -> None:
    assert knowledge.knowledge_reads(WORK) == {"search", "confirm"}
    assert knowledge.knowledge_reads({"post": WORK["post"]}) == frozenset(), "no citation step"


async def test_the_same_work_with_and_without_a_source_is_compared_on_the_cockpit_figures() -> None:
    w = World()
    await w.run("run_1", served=True, seconds=60)
    await w.run("run_2", served=True, seconds=120)
    await w.run("run_3", served=False, seconds=600, ends="run.escalated")
    await w.run("run_4", served=False, seconds=300)
    await w.fact("step.corrected", "run_4", step="post")
    reads = {VERSION: knowledge.knowledge_reads(WORK)}
    tallies = knowledge.sides(await w.entries(), reads, SINCE, UNTIL)["answer"]
    assert tallies["with"].runs == ("run_1", "run_2")
    assert tallies["without"].runs == ("run_3", "run_4"), "a person's read is no source"
    found = by_id(
        knowledge.comparison(
            "answer",
            tallies,
            reads[VERSION],
            since=SINCE,
            until=UNTIL,
            costs={"with": 4.0, "without": 1.0},
            currency="EUR",
        )
    )
    assert found["value.with_knowledge.cycle_seconds"].value == 93, "each entry takes a second"
    assert found["value.without_knowledge.cycle_seconds"].value == 453
    assert found["value.knowledge_effect.cycle_seconds"].value == -360
    assert found["value.with_knowledge.quality"].value == 1
    assert found["value.without_knowledge.quality"].value == 0, "escalated, and corrected"
    assert found["value.knowledge_effect.quality"].value == 1
    assert found["value.knowledge_effect.escalation_rate"].value == -0.5
    assert found["value.with_knowledge.automation"].value == 1
    assert found["value.without_knowledge.automation"].value == 0.5
    assert found["value.with_knowledge.cost_per_case"].value == 2
    assert found["value.without_knowledge.cost_per_case"].value == 1, "one finished run"
    assert found["value.with_knowledge.cost_per_case"].unit == "EUR"
    effect = found["value.knowledge_effect.quality"]
    assert effect.basis["runs_with"] == 2 and effect.basis["runs_without"] == 2
    assert effect.basis["knowledge_reads"] == ["confirm", "search"]
    side = found["value.with_knowledge.quality"]
    assert (side.basis["side"], side.basis["runs"]) == ("with", ["run_1", "run_2"])
    assert all(f.method for f in found.values())
    assert all(f.scope == "process" and f.subject == "answer" for f in found.values())


async def test_a_side_without_runs_withholds_its_figures_and_the_difference_never_zero() -> None:
    w = World()
    await w.run("run_1", served=True, seconds=60)
    reads = {VERSION: knowledge.knowledge_reads(WORK)}
    tallies = knowledge.sides(await w.entries(), reads, SINCE, UNTIL)["answer"]
    found = by_id(
        knowledge.comparison(
            "answer",
            tallies,
            reads[VERSION],
            since=SINCE,
            until=UNTIL,
            costs={"with": None, "without": None},
            currency="EUR",
        )
    )
    assert found["value.without_knowledge.runs_ended"].value == 0
    for compared in knowledge.COMPARED:
        without = found[knowledge.figure_id("value.without_knowledge", compared)]
        assert without.value is None and without.withheld, compared
        effect = found[knowledge.figure_id("value.knowledge_effect", compared)]
        assert effect.value is None and "without knowledge" in (effect.withheld or ""), compared
    assert found["value.with_knowledge.quality"].value == 1
    assert found["value.with_knowledge.cost_per_case"].withheld == (
        "accounting priced no step of this side's runs"
    )


async def test_a_rehearsal_an_earlier_run_and_a_version_reading_no_knowledge_are_left_out() -> None:
    w = World()
    await w.run("run_1", served=True, seconds=60)
    await w.fact("run.created", "run_r", rehearsal=True)
    await w.fact("run.finished", "run_r", rehearsal=True)
    entries = await w.entries()
    reads = {VERSION: knowledge.knowledge_reads(WORK)}
    later = knowledge.sides(entries, reads, START + timedelta(days=1), UNTIL)
    assert later == {}, "the run ended before the period"
    assert knowledge.sides(entries, {VERSION: frozenset()}, SINCE, UNTIL) == {}
    assert knowledge.sides(entries, reads, SINCE, UNTIL)["answer"]["with"].runs == ("run_1",)
