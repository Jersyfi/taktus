"""A purpose served by an ordered chain of models, switched at the step boundary (issue #328;
UC-8.2 §2; ADR-0116, ADR-0043).

Each case runs a plan with one step on a model through the run engine over fakes of every
port. The chain has two or three members, each a fake model that answers, answers at its rate
limit, or cannot be reached. The provenance record names the member that produced the result
and the route it took; the accounts book what the step waited for.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from fakes import FakeClock, FakeIdentifiers, FakeMaturities, FakeWorker
from fakes.model import FakeModel

from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.models import Declared, StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.run.application.query import BlockedTime
from taktus.components.run.application.service import EngineOptions, RunEngine, StartRun
from taktus.components.run.domain.model import Cause, Run, RunState, StepState
from taktus.components.run.domain.service import provenance, routing
from taktus.ports.model import Location, Permitted
from taktus.ports.worker import ComputeLimit, Limits, QuotaLimit
from taktus.shared.v1 import (
    Commissioned,
    ExactnessClass,
    Fallback,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    Provenance,
    ProvenanceRoute,
    RouteSkip,
    Step,
)

AT = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
TENANT = "t"
PERSON = "idn_operator"
ENOUGH = Limits(
    compute=ComputeLimit(seconds=10, resource_class="cpu.small"), quota=QuotaLimit(units=20)
)


class Rule:
    """A tenant's residency rule: its own location, narrowed per data class."""

    def __init__(self, own: Permitted = "anywhere", **classes: Permitted) -> None:
        self.own = own
        self.classes = classes

    async def permitted(self, tenant: str, data_class: str | None) -> Permitted:
        if data_class is not None and data_class in self.classes:
            return self.classes[data_class]
        return self.own


def llm(
    exactness: ExactnessClass = ExactnessClass.SOURCED, data_class: str | None = None
) -> tuple[Step, dict[str, Any]]:
    step = Step(
        id="draft",
        method=Method.LLM,
        reason="r",
        rejected=(),
        exactness=exactness,
        fallback=Fallback(when="x", to=Method.HUMAN),
    )
    work: dict[str, Any] = {"purpose": "reasoning", "prompt": "Say yes.", "values": {}}
    if data_class is not None:
        work["data_class"] = data_class
    return step, work


class World:
    """One tenant, an engine over memory stores, and a chain of models for `reasoning`."""

    def __init__(
        self,
        members: Sequence[tuple[str, FakeModel, Location]],
        *,
        rule: Rule | None = None,
        classes: Mapping[str, tuple[str, ...]] | None = None,
    ) -> None:
        self.clock = FakeClock(AT)
        self.persistence = MemoryPersistence()
        self.runs = MemoryRepository(self.persistence, Run)
        self.objects = MemoryObjectStore()
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.provenance = MemoryProvenanceStore(self.persistence)
        declared = {
            f"model.{name}": Declared(location=location, **_classes(classes, name))
            for name, _, location in members
        }
        pool = StaticModelPool(
            [(f"model.{name}", ["reasoning"], model, model.name) for name, model, _ in members],
            declared,
        )
        self.engine = RunEngine(
            runs=self.runs,
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=self.provenance,
            workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
            models=pool,
            clock=self.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            options=EngineOptions(uncalibrated_margin=0.0),
            maturities=FakeMaturities(),
            residency=rule,
        )
        self.accounts = BlockedTime(self.ledger, self.objects, self.persistence, self.runs)

    async def start(self, definition: tuple[Step, dict[str, Any]]) -> Run:
        step, work = definition
        plan = Plan(
            id="pln_1",
            command_id="cmd_1",
            goal="g",
            autonomy_level=3,
            steps=(step,),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=PERSON, at=AT),
        )
        return await self.engine.start(
            StartRun(
                plan=plan,
                work={step.id: work},
                budget=ENOUGH,
                process_version="routing@1",
                actor=PERSON,
                tenant=TENANT,
            )
        )

    async def record(self, run: Run) -> Provenance:
        async with self.persistence.transaction(TENANT):
            (record,) = await self.provenance.of_run(TENANT, run.id)
        return record

    async def kinds(self) -> list[tuple[str, str | None]]:
        async with self.persistence.transaction(TENANT):
            entries = await self.ledger.entries(TENANT)
        return [(e.kind, e.outcome) for e in entries if e.kind.startswith("step.")]


def _classes(classes: Mapping[str, tuple[str, ...]] | None, name: str) -> dict[str, Any]:
    if classes is None or name not in classes:
        return {}
    return {"classes": classes[name]}


async def test_a_step_moves_to_the_second_member_after_a_429_of_the_first() -> None:
    """The verification of #328: the first member answers `429`, the step goes back to its
    boundary and is admitted again at once on the second; the provenance names the second as
    the member that produced the result, with the route that passed over the first; the wait is
    booked to `limit.provider`, its record naming who was at its limit and who answered."""
    first = FakeModel(answer="no", name="first-model@1", at_limit=1, retry_after=30.0)
    second = FakeModel(answer="yes", name="second-model@1")
    w = World([("first", first, "eu"), ("second", second, "eu")])
    run = await w.start(llm())
    assert run.state is RunState.FINISHED
    assert (len(first.prompts), len(second.prompts)) == (1, 1)
    record = await w.record(run)
    assert (record.adapter, record.adapter_version) == ("model.second", "second-model@1")
    assert record.route is not None and record.route.adapter == "model.second"
    skipped = [(s.adapter, s.reason) for s in record.route.skipped]
    assert skipped == [("model.first", "cooling_down")]
    (waited,) = await w.accounts.blocks(TENANT)
    assert (waited.account, waited.cause) == ("limit.provider", "at_provider_limit")
    async with w.persistence.transaction(TENANT):
        (entry,) = [e for e in await w.ledger.entries(TENANT) if e.kind == "step.waited"]
    assert entry.content_digest is not None
    content = await w.objects.get(entry.content_digest)
    assert content is not None
    document = json.loads(content)
    assert (document["adapter"], document["answered_by"]) == ("model.first", "model.second")
    assert (document["retry_after_seconds"], document["ended"]) == (30.0, "answered")
    assert await w.kinds() == [
        ("step.admitted", None),
        ("step.started", None),
        ("step.waiting", "at_provider_limit"),
        ("step.admitted", None),
        ("step.started", None),
        ("step.waited", "at_provider_limit"),
        ("step.finished", "succeeded"),
    ]


async def test_a_member_at_its_limit_is_passed_over_by_the_next_step_while_it_cools_down() -> None:
    """A cool-down holds for every step the engine runs, until the delay the provider named."""
    first = FakeModel(answer="no", name="first-model@1", at_limit=1, retry_after=600.0)
    second = FakeModel(answer="yes", name="second-model@1")
    w = World([("first", first, "eu"), ("second", second, "eu")])
    await w.start(llm())
    later = await w.start(llm())
    assert (await w.record(later)).adapter == "model.second"
    assert (len(first.prompts), len(second.prompts)) == (1, 2)
    w.clock.current += timedelta(seconds=600)
    again = await w.start(llm())
    assert (await w.record(again)).adapter == "model.first"


async def test_a_step_moves_to_the_next_member_after_a_failure_and_books_no_block() -> None:
    first = FakeModel(name="first-model@1", unreachable="connection refused")
    second = FakeModel(answer="yes", name="second-model@1")
    w = World([("first", first, "eu"), ("second", second, "eu")])
    run = await w.start(llm())
    assert run.state is RunState.FINISHED
    assert (await w.record(run)).adapter == "model.second"
    assert await w.accounts.blocks(TENANT) == ()
    kinds = await w.kinds()
    assert ("step.finished", "failed") in kinds and kinds[-1] == ("step.finished", "succeeded")


async def test_a_failure_with_no_other_member_escalates_as_before() -> None:
    first = FakeModel(name="first-model@1", unreachable="connection refused")
    w = World([("first", first, "eu")])
    run = await w.start(llm())
    assert run.state is RunState.ESCALATED and run.cause is Cause.FAILURE


async def test_a_429_with_no_other_member_waits_for_the_same_one() -> None:
    """ADR-0043 §5 as before: one member at its limit halts the run with cause `capacity`."""
    first = FakeModel(answer="yes", name="first-model@1", at_limit=1, retry_after=30.0)
    w = World([("first", first, "eu")])
    run = await w.start(llm())
    assert run.state is RunState.HALTED and run.cause is Cause.CAPACITY
    waiting = run.step_run("draft").block
    assert waiting is not None and waiting.retry_after_seconds == 30.0


async def test_every_member_cooling_down_makes_the_step_wait_without_a_call() -> None:
    first = FakeModel(answer="no", name="first-model@1", at_limit=1, retry_after=600.0)
    second = FakeModel(answer="no", name="second-model@1", at_limit=1, retry_after=900.0)
    w = World([("first", first, "eu"), ("second", second, "eu")])
    run = await w.start(llm())
    assert run.state is RunState.HALTED and run.cause is Cause.CAPACITY
    assert (len(first.prompts), len(second.prompts)) == (1, 1)
    waiting = run.step_run("draft").block
    assert waiting is not None and waiting.account == "limit.provider"
    # Asked again before either cool-down ended, the step calls nothing and waits on.
    later = await w.start(llm())
    assert later.state is RunState.HALTED and later.cause is Cause.CAPACITY
    assert (len(first.prompts), len(second.prompts)) == (1, 1)
    block = later.step_run("draft").block
    # Until the first cool-down ends: the first member's, less the seconds that passed.
    assert block is not None and block.retry_after_seconds is not None
    assert 500 < block.retry_after_seconds < 600


async def test_a_member_outside_the_tenant_s_residency_rule_is_never_chosen() -> None:
    """The verification of #328: a member the rule does not admit is passed over first in the
    chain or not, and never called — not when every member the rule admits is at its limit."""
    outside = FakeModel(answer="no", name="outside-model@1")
    inside = FakeModel(answer="yes", name="inside-model@1", at_limit=1)
    w = World([("outside", outside, "elsewhere"), ("inside", inside, "eu")], rule=Rule("eu"))
    run = await w.start(llm())
    assert run.state is RunState.HALTED and run.cause is Cause.CAPACITY
    assert outside.prompts == []
    w.clock.current += timedelta(minutes=2)
    run = await w.start(llm())
    assert run.state is RunState.FINISHED and outside.prompts == []
    record = await w.record(run)
    assert record.adapter == "model.inside"
    assert record.route is not None and record.route.permitted == "eu"
    assert [(s.adapter, s.reason) for s in record.route.skipped] == [("model.outside", "residency")]


async def test_a_data_class_narrows_the_rule_and_none_fitting_fails_naming_the_rule() -> None:
    eu = FakeModel(answer="yes", name="eu-model@1")
    w = World([("eu", eu, "eu")], rule=Rule("eu", personal="own"))
    run = await w.start(llm(data_class="personal"))
    assert run.state is RunState.ESCALATED and run.cause is Cause.FAILURE
    reason = run.step_run("draft").reason or ""
    assert "model.eu" in reason and "personal" in reason and "own" in reason
    assert eu.prompts == []
    own = FakeModel(answer="yes", name="own-model@1")
    w = World([("eu", eu, "eu"), ("own", own, "own")], rule=Rule("eu", personal="own"))
    run = await w.start(llm(data_class="personal"))
    record = await w.record(run)
    assert record.adapter == "model.own" and eu.prompts == []
    assert record.route is not None
    assert (record.route.permitted, record.route.data_class) == ("own", "personal")


async def test_a_member_that_may_not_produce_the_step_s_class_is_passed_over() -> None:
    loose = FakeModel(answer="no", name="loose-model@1")
    pinned = FakeModel(answer="yes", name="pinned-model@1")
    w = World(
        [("loose", loose, "eu"), ("pinned", pinned, "eu")],
        classes={"loose": ("free",)},
    )
    run = await w.start(llm(ExactnessClass.SOURCED))
    record = await w.record(run)
    assert record.adapter == "model.pinned" and loose.prompts == []
    assert record.route is not None
    assert [(s.adapter, s.reason) for s in record.route.skipped] == [("model.loose", "exactness")]
    run = await w.start(llm(ExactnessClass.FREE))
    assert (await w.record(run)).adapter == "model.loose"


async def test_routing_changes_the_model_and_never_the_method() -> None:
    """No member fits: the step fails on its method; it never moves to another one."""
    outside = FakeModel(answer="no", name="outside-model@1")
    w = World([("outside", outside, "elsewhere")], rule=Rule("own"))
    run = await w.start(llm())
    assert run.step_run("draft").state is StepState.FAILED
    assert run.step("draft").method is Method.LLM
    assert "residency" in (run.step_run("draft").reason or "")


async def test_the_recorded_route_is_computed_again_from_the_chain_and_the_record() -> None:
    """UC-8.2 §2: a step with the same declared needs is routed to the same member, and the route
    the provenance names is what the chain gives for the needs the record carries."""
    first = FakeModel(answer="no", name="first-model@1")
    second = FakeModel(answer="yes", name="second-model@1")
    w = World([("first", first, "elsewhere"), ("second", second, "eu")], rule=Rule("eu"))
    runs = [await w.start(llm()) for _ in range(3)]
    records = [await w.record(run) for run in runs]
    assert {r.adapter for r in records} == {"model.second"}
    pool = w.engine._models
    assert pool is not None
    route = records[0].route
    assert route is not None and records[0].exactness is not None
    again = routing.route(
        await pool.chain(route.purpose),
        routing.Needs(
            purpose=route.purpose,
            exactness=records[0].exactness,
            permitted=route.permitted,
            data_class=route.data_class,
        ),
        {},
        AT,
    )
    assert again.record() == route


def test_a_route_stays_within_the_bound_it_adds_to_a_record() -> None:
    """ADR-0021 §4 as ADR-0116 §7 amends it: with identifiers of 64 characters, a route adds at
    most 256 bytes plus 96 for every member it passed over."""
    long = "x" * 64

    def member(n: int) -> str:
        return f"model.{n}{long}"[:64]

    route = ProvenanceRoute(
        purpose="r" + long[:63],
        adapter=member(9),
        permitted="anywhere",
        data_class="d" + long[:63],
        skipped=tuple(RouteSkip(adapter=member(n), reason="cooling_down") for n in range(8)),
    )
    record = Provenance(
        id="p" + long[:63],
        run_id="r" + long[:63],
        step_id="s" + long[:63],
        process_version="v" + long[:63],
        method=Method.LLM,
        exactness=ExactnessClass.TOLERANT,
        adapter=member(9),
        adapter_version="a" + long[:63],
        route=route,
        inputs=(),
        outputs=("result",),
        result_digest="sha256:" + "0" * 64,
        ledger_seq=1,
        recorded_at=AT,
    )
    assert provenance.size_bytes(record) <= provenance.size_bound(record)
    without = record.model_copy(update={"route": None})
    added = provenance.size_bytes(record) - provenance.size_bytes(without)
    assert added <= provenance.ROUTE_BYTES + provenance.BYTES_PER_SKIP * len(route.skipped)
