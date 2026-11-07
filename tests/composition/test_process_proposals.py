"""Taktus proposes processes (UC-4.4, ADR-0270), and a failure healed again and again becomes an
improvement proposal (UC-4.6), over the memory stores.

What is real: the run engine, which records who started a run and what it consumed; the ledger;
the process component's rule; the composition's list and its acts. What stands in: a fake
worker that reports the compute it used, and the request path of ADR-0251 §1, which records
the words it was handed and returns a run as `ProposalActs.ask` would.

What is proven: a process a person starts by hand at a regular cadence is proposed to that
person, with the work it would take over, its cost from what the runs consumed and why now,
and to nobody else; an irregular rhythm or fewer than three starts are not proposed; a
failure healed its limit of times is an improvement proposal every identity sees; the list is
ordered by how often the work recurs per 30 days, with that reason on each; each is accepted
or declined on its own, an accepted one handed to the request path that builds a proposal of
a version and runs nothing for real, a decided one no longer listed; only the person a
proposal is shown to may decide it.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fakes import FakeClock, FakeIdentifiers, FakeWorker, InnerStep
from fakes.maturity import VERIFIED

from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.run.application.service import EngineOptions, RunEngine, StartRun
from taktus.components.run.domain.model import Run
from taktus.composition.process_proposals import ProcessProposals, ProposalRefused
from taktus.ports.ledger import Fact
from taktus.ports.worker import ComputeLimit, Limits
from taktus.shared.v1 import (
    Commissioned,
    ExactnessClass,
    Fallback,
    LedgerRefs,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    Step,
)

AT = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
TENANT = "t"
ANNA = "idn_anna"
BEN = "idn_ben"
BUDGET = Limits(compute=ComputeLimit(seconds=60, resource_class="cpu.small"))
STEP = Step(
    id="report",
    method=Method.WORKER,
    reason="r",
    rejected=(),
    exactness=ExactnessClass.TOLERANT,
    fallback=Fallback(when="x", to=Method.HUMAN),
    requires=("shell.script",),
)


class Asked:
    """The request path of ADR-0251 §1, recording what it was handed."""

    def __init__(self, world: World) -> None:
        self.world = world
        self.asked: list[tuple[str, str, str]] = []

    async def ask(self, tenant: str, process_id: str, request: str, by: str) -> Run:
        self.asked.append((process_id, request, by))
        return await self.world.start("change-process@1", by)


class World:
    def __init__(self) -> None:
        self.clock = FakeClock(AT)
        self.persistence = MemoryPersistence()
        self.runs = MemoryRepository(self.persistence, Run)
        self.objects = MemoryObjectStore()
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.runs,
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=MemoryProvenanceStore(self.persistence),
            workers=StaticWorkerPool(
                [("worker.fake.0", FakeWorker(script=(InnerStep("one", 2.0),)))]
            ),
            clock=self.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            options=EngineOptions(uncalibrated_margin=0.0),
        )
        self.asked = Asked(self)
        self.proposals = ProcessProposals(
            ledger=self.ledger,
            runs=self.runs,
            versions=MemoryRepository(self.persistence, ProcessVersion),
            objects=self.objects,
            work=self.persistence,
            clock=self.clock,
            asking=self.asked,
        )
        self.plans = 0

    async def start(self, ref: str, by: str) -> Run:
        self.plans += 1
        plan = Plan(
            id=f"pln_{self.plans}",
            command_id=f"cmd_{self.plans}",
            goal="g",
            autonomy_level=3,
            steps=(STEP,),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=by, at=self.clock.now()),
        )
        work: dict[str, Any] = {"report": {"task": {"goal": "g", "acceptance": ["a"]}}}
        return await self.engine.start(
            StartRun(
                plan=plan,
                work=work,
                budget=BUDGET,
                process_version=ref,
                actor=by,
                tenant=TENANT,
            )
        )

    async def by_hand(self, ref: str, by: str, every: timedelta, times: int) -> None:
        for _ in range(times):
            await self.start(ref, by)
            self.clock.current += every

    async def record(self, kind: str, **more: Any) -> None:
        async with self.persistence.transaction(TENANT):
            await self.ledger.record(TENANT, Fact(kind=kind, **more))

    async def recurred(self, process: str, step: str, failure: str, times: int) -> None:
        """A failure healed `times` times and its recurrence recorded, as ADR-0254 records it."""
        for attempt in range(times):
            stored = json.dumps({"failure": failure, "action": "retry", "attempt": attempt + 1})
            digest = await self.objects.put(stored.encode())
            refs = LedgerRefs(
                tenant=TENANT,
                run_id=f"heal_{attempt}",
                process_version=f"{process}@1",
                step_id=step,
            )
            await self.record("step.healed", refs=refs, outcome="retry", content_digest=digest)
        await self.record(
            "heal.recurred",
            refs=LedgerRefs(tenant=TENANT, process_version=f"{process}@1", step_id=step),
            outcome="proposed",
            content_digest="sha256:" + hashlib.sha256(failure.encode()).hexdigest(),
        )


async def test_a_process_started_by_hand_every_week_is_proposed_to_that_person_only() -> None:
    w = World()
    await w.by_hand("weekly-report@1", ANNA, timedelta(days=7), 4)
    (proposal,) = await w.proposals.listed(TENANT, ANNA)
    assert proposal.kind == "by_hand" and proposal.process_id == "weekly-report"
    assert proposal.takes_over == "starting weekly-report by hand, about every 7 days"
    assert proposal.why_now.startswith("started by hand 4 times in the last 90 days")
    assert proposal.cost.startswith("per a run: compute_seconds 2; per 30 days: compute_seconds")
    assert proposal.order == "recurs 4.3 times per 30 days"
    assert await w.proposals.listed(TENANT, BEN) == [], "shown to the person whose work it is"


async def test_an_irregular_rhythm_or_two_starts_are_not_proposed() -> None:
    w = World()
    for gap in (1, 9, 2):
        await w.start("ad-hoc@1", ANNA)
        w.clock.current += timedelta(days=gap)
    await w.by_hand("twice@1", ANNA, timedelta(days=7), 2)
    assert await w.proposals.listed(TENANT, ANNA) == []


async def test_a_failure_healed_again_and_again_is_an_improvement_proposal_everyone_sees() -> None:
    w = World()
    await w.recurred("nightly", "fetch", "the export service answered 503", 3)
    for viewer in (ANNA, BEN):
        (proposal,) = await w.proposals.listed(TENANT, viewer)
        assert proposal.kind == "healed" and proposal.reader is None
        assert "removing the cause of a failure of step fetch" in proposal.takes_over
        assert "healed 3 times" in proposal.why_now
        assert "the export service answered 503" in proposal.words


async def test_the_list_is_ordered_by_how_often_the_work_recurs_and_says_so() -> None:
    w = World()
    await w.recurred("nightly", "fetch", "timeout", 3)
    await w.by_hand("weekly-report@1", ANNA, timedelta(days=7), 3)
    await w.by_hand("daily-check@1", ANNA, timedelta(days=1), 5)
    listed = await w.proposals.listed(TENANT, ANNA)
    assert [p.process_id for p in listed] == ["daily-check", "weekly-report", "nightly"]
    assert [p.order for p in listed] == [
        "recurs 30.0 times per 30 days",
        "recurs 4.3 times per 30 days",
        "recurs 3.0 times per 30 days",
    ]


async def test_each_is_accepted_or_declined_on_its_own_and_accepting_builds_a_proposal() -> None:
    w = World()
    await w.by_hand("weekly-report@1", ANNA, timedelta(days=7), 3)
    await w.recurred("nightly", "fetch", "timeout", 3)
    report, nightly = sorted(await w.proposals.listed(TENANT, ANNA), key=lambda p: p.kind)
    accepted = await w.proposals.accept(TENANT, report.id, ANNA)
    assert w.asked.asked == [("weekly-report", report.words, ANNA)]
    assert accepted.run.process_version == "change-process@1", (
        "accepting starts the run that builds a proposal of a version; nothing of it is "
        "registered or runs for real before a person commissions it"
    )
    assert [p.id for p in await w.proposals.listed(TENANT, ANNA)] == [nightly.id]
    await w.proposals.decline(TENANT, nightly.id, BEN)
    assert await w.proposals.listed(TENANT, ANNA) == []
    assert len(w.asked.asked) == 1, "declining asks for nothing"
    async with w.persistence.transaction(TENANT):
        kinds = [
            e.kind
            for e in await w.ledger.of_kinds(TENANT, ("proposal.accepted", "proposal.declined"))
        ]
    assert kinds == ["proposal.accepted", "proposal.declined"]


async def test_only_the_person_a_proposal_is_shown_to_may_decide_it_and_only_once() -> None:
    w = World()
    await w.by_hand("weekly-report@1", ANNA, timedelta(days=7), 3)
    (proposal,) = await w.proposals.listed(TENANT, ANNA)
    with pytest.raises(ProposalRefused):
        await w.proposals.decline(TENANT, proposal.id, BEN)
    await w.proposals.decline(TENANT, proposal.id, ANNA)
    with pytest.raises(ProposalRefused):
        await w.proposals.accept(TENANT, proposal.id, ANNA)
