"""Blocked-time accounts (issue #80; UC-9.5 §2 bullets 1, 2 and 5; ADR-0015, ADR-0043).

Each case runs plans through the run engine over fakes of every port, makes a run block for one
of the seven causes, lets time pass on the clock, lets the block end, and reads the accounts back
through the query that reads them: every block with its cause and duration, the sums per cause,
process and period, and a person's own waits — readable by that person and nobody else.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fakes import (
    FakeClock,
    FakeConnector,
    FakeIdentifiers,
    FakeMaturities,
    FakePlatform,
    FakeWorker,
)
from fakes.connector import READ
from fakes.model import FakeModel
from pydantic import ValidationError

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.run.application.query import BlockedTime
from taktus.components.run.application.service import (
    ConfirmSteps,
    EngineOptions,
    ResumeRun,
    RunEngine,
    StartRun,
)
from taktus.components.run.domain.model import ACCOUNTS, Cause, Run, RunState, StepState
from taktus.components.run.domain.model.block import limit_account
from taktus.components.run.domain.service.blocked import Block, BlockedSum, parse
from taktus.ports.platform import Headroom, PlatformObservation
from taktus.ports.worker import ComputeLimit, Limits, QuotaLimit
from taktus.shared.v1 import (
    AutonomyLevel,
    Commissioned,
    ExactnessClass,
    Fallback,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    Step,
)

AT = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)
TENANT = "t"
PERSON = "idn_decider"
OTHER = "idn_colleague"
ENOUGH = Limits(
    compute=ComputeLimit(seconds=10, resource_class="cpu.small"), quota=QuotaLimit(units=20)
)
GAP = timedelta(minutes=7)
"""How long the test lets a block last before it lets it end."""


def observed(*, free: float) -> PlatformObservation:
    """The platform with `free` of 100 units of storage free, and room in every other way."""
    return PlatformObservation(
        at=AT,
        cpu=Headroom(free=4, total=4, unit="cores", source="load"),
        memory=Headroom(free=2**34, total=2**35, unit="bytes", source="meminfo"),
        storage=Headroom(free=free, total=100, unit="bytes", source="disk"),
    )


def rule(id: str, *, after: tuple[str, ...] = ()) -> tuple[Step, dict[str, Any]]:
    step = Step(
        id=id,
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.EXACT,
        depends_on=after or None,
    )
    return step, {"rule": "constant", "value": 1}


def read(id: str) -> tuple[Step, dict[str, Any]]:
    step = Step(
        id=id, method=Method.RULE, reason="r", rejected=(), exactness=ExactnessClass.SOURCED
    )
    return step, {"rule": "connector", "operation": READ, "input": {"id": "x"}}


def worker(id: str) -> tuple[Step, dict[str, Any]]:
    step = Step(
        id=id,
        method=Method.WORKER,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        fallback=Fallback(when="x", to=Method.HUMAN),
        requires=("shell.script",),
    )
    return step, {"task": {"goal": "g", "acceptance": ["a"], "inputs": {"n": 1}}}


def llm(id: str) -> tuple[Step, dict[str, Any]]:
    step = Step(
        id=id,
        method=Method.LLM,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.SOURCED,
        fallback=Fallback(when="x", to=Method.HUMAN),
    )
    return step, {"purpose": "reasoning", "prompt": "Say yes.", "values": {}}


def wait(id: str, seconds: float) -> tuple[Step, dict[str, Any]]:
    return Step(id=id, method=Method.WAIT, reason="r", rejected=()), {"seconds": seconds}


class World:
    """One tenant: an engine over memory stores, a worker, a connector and a model, and the
    query that reads the accounts."""

    def __init__(self, *, worker: FakeWorker | None = None, model: FakeModel | None = None):
        self.clock = FakeClock(AT)
        self.persistence = MemoryPersistence()
        self.runs = MemoryRepository(self.persistence, Run)
        self.objects = MemoryObjectStore()
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.worker = worker or FakeWorker()
        self.model = model or FakeModel(answer="yes")
        connector = FakeConnector()
        connector.reads["x"] = {"id": "x"}
        self.engine = RunEngine(
            runs=self.runs,
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=MemoryProvenanceStore(self.persistence),
            workers=StaticWorkerPool([("worker.fake", self.worker)]),
            connectors=StaticConnectorPool([("connector.fake", connector)]),
            models=StaticModelPool([("model.fake", ["reasoning"], self.model, "fake-model@1")]),
            clock=self.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            options=EngineOptions(uncalibrated_margin=0.0),
            maturities=FakeMaturities(),
        )
        self.accounts = BlockedTime(self.ledger, self.objects, self.persistence)

    async def start(
        self,
        process: str,
        *definitions: tuple[Step, dict[str, Any]],
        budget: Limits = ENOUGH,
        level: AutonomyLevel = 3,
        actions: Mapping[str, AutonomyLevel] | None = None,
    ) -> Run:
        plan = Plan(
            id="pln_1",
            command_id="cmd_1",
            goal="g",
            autonomy_level=level,
            steps=tuple(step for step, _ in definitions),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=PERSON, at=AT),
        )
        return await self.engine.start(
            StartRun(
                plan=plan,
                work={step.id: work for step, work in definitions},
                budget=budget,
                process_version=f"{process}@1",
                actor=PERSON,
                tenant=TENANT,
                actions=dict(actions or {}),
            )
        )

    async def resume(self, run: Run, budget: Limits | None = None) -> Run:
        return await self.engine.resume(
            ResumeRun(run_id=run.id, actor=PERSON, tenant=TENANT, budget=budget)
        )

    async def answer(self, run: Run, *steps: str) -> Run:
        return await self.engine.confirm(
            ConfirmSteps(run_id=run.id, steps=steps, actor=PERSON, tenant=TENANT)
        )

    def later(self, by: timedelta = GAP) -> None:
        self.clock.current += by


async def every_cause(w: World) -> dict[str, Run]:
    """One run per process, each blocked for one cause, the block let last `GAP`, then ended.
    The process names the cause it blocks for."""
    runs: dict[str, Run] = {}

    # limit.provider: the model's provider answers at its rate limit once.
    w.model.at_limit = 1
    run = await w.start("provider", llm("draft"))
    assert run.state is RunState.HALTED and run.cause is Cause.CAPACITY
    w.later()
    runs["provider"] = await w.resume(run)

    # limit.quota: the read needs a quota unit, and the budget has half of one.
    run = await w.start("quota", read("look"), budget=Limits(quota=QuotaLimit(units=0.5)))
    assert run.state is RunState.HALTED and run.cause is Cause.LIMIT
    w.later()
    runs["quota"] = await w.resume(run, budget=ENOUGH)

    # limit.budget: the worker's estimate does not fit the compute the budget allows.
    small = Limits(compute=ComputeLimit(seconds=0.1, resource_class="cpu.small"))
    run = await w.start("budget", worker("build"), budget=small)
    assert run.state is RunState.HALTED and run.cause is Cause.LIMIT
    w.later()
    runs["budget"] = await w.resume(run, budget=ENOUGH)

    # limit.compute: the worker holds as many assignments as it declares, once.
    w.worker.full_for = 1
    run = await w.start("compute", worker("build"))
    assert run.state is RunState.HALTED and run.cause is Cause.CAPACITY
    w.later()
    runs["compute"] = await w.resume(run)

    # wait.human and wait.dependency: the read waits for a person to confirm it at level 2,
    # and the step after it is held back meanwhile.
    run = await w.start(
        "human",
        read("ask"),
        rule("then", after=("ask",)),
        actions={READ: 2},
    )
    assert run.state is RunState.WAITING_HUMAN
    w.later()
    runs["human"] = await w.answer(run, "ask")

    # wait.external: a wait step waits for time to pass.
    runs["external"] = await w.start("external", wait("pause", GAP.total_seconds()))

    for name, finished in runs.items():
        assert finished.state is RunState.FINISHED, name
        assert all(s.block is None for s in finished.step_runs), f"{name}: no block left open"
    return runs


# --- every block is recorded with its cause and its duration -------------------------------------


async def test_a_block_of_each_cause_is_recorded_with_its_cause_and_its_duration() -> None:
    w = World()
    runs = await every_cause(w)
    blocks = await w.accounts.blocks(TENANT)
    by_account = {b.account: b for b in blocks}
    assert set(by_account) == set(ACCOUNTS), "each of the seven causes, and nothing else"
    assert len(blocks) == len(ACCOUNTS), "one block per cause: none counted twice"
    expected = {
        "limit.provider": ("provider", "draft", "at_provider_limit"),
        "limit.quota": ("quota", "look", "rejected_by_admission"),
        "limit.budget": ("budget", "build", "rejected_by_admission"),
        "limit.compute": ("compute", "build", "at_capacity"),
        "wait.human": ("human", "ask", "awaiting_confirmation"),
        "wait.dependency": ("human", "then", "held_back"),
        "wait.external": ("external", "pause", "waiting_on_clock"),
    }
    for account, (process, step, cause) in expected.items():
        block = by_account[account]
        run = runs[process]
        assert (block.run_id, block.step_id, block.process) == (run.id, step, process), account
        assert block.process_version == f"{process}@1"
        assert block.cause == cause, account
        assert block.seconds == (block.until - block.since).total_seconds(), account
        # The clock was moved on by GAP while the step stood still; the engine's own reads of
        # the clock add a second each.
        assert GAP.total_seconds() <= block.seconds <= GAP.total_seconds() + 30, account
    assert by_account["wait.dependency"].on == "ask", "the held-back step names what it waited on"


async def test_every_record_is_a_ledger_entry_naming_its_document_and_none_without_an_end() -> None:
    w = World()
    await every_cause(w)
    async with w.persistence.transaction(TENANT):
        entries = list(await w.ledger.entries(TENANT))
    records = [e for e in entries if e.kind == "step.waited"]
    assert len(records) == len(ACCOUNTS)
    for entry in records:
        assert entry.content_digest is not None and entry.refs.run_id and entry.refs.step_id
        content = await w.objects.get(entry.content_digest)
        assert content is not None
        document = json.loads(content)
        assert entry.outcome == document["cause"], "the entry carries the cause as its token"
        assert document["account"] in ACCOUNTS and document["seconds"] >= 0
        assert entry.refs.actor is None, "a block is nobody's act"
        assert entry.consumption is None, "a record counts time, not consumption"
    async with w.persistence.transaction(TENANT):
        assert (await w.ledger.verify(TENANT)).intact


async def test_a_block_still_open_is_carried_by_its_step_and_ends_with_its_record() -> None:
    w = World()
    run = await w.start("human", read("ask"), rule("then", after=("ask",)), actions={READ: 2})
    ask, then = run.step_run("ask"), run.step_run("then")
    assert ask.block is not None and ask.block.account == "wait.human"
    assert then.block is not None and then.block.account == "wait.dependency"
    assert await w.accounts.blocks(TENANT) == (), "a block is recorded when it ends"
    async with w.persistence.transaction(TENANT):
        stored = await w.runs.get(TENANT, run.id)
    assert stored is not None and stored.step_run("ask").block == ask.block, "it survives"
    w.later()
    await w.answer(run, "ask")
    assert {b.account for b in await w.accounts.blocks(TENANT)} == {
        "wait.human",
        "wait.dependency",
    }


async def test_a_platform_that_cannot_hold_the_job_and_a_worker_at_its_limit_are_booked() -> None:
    w = World(worker=FakeWorker(halt_on_limit="quota", script=(*FakeWorker().script,) * 2))
    run = await w.start("halted", worker("build"))
    assert run.state is RunState.HALTED and run.cause is Cause.LIMIT
    assert run.step_run("build").block is not None
    assert run.step_run("build").block.cause == "halted_at_limit"
    assert run.step_run("build").block.account == "limit.quota"
    w.worker.halt_on_limit = None
    w.later()
    await w.resume(run, budget=ENOUGH.model_copy(update={"quota": QuotaLimit(units=40)}))
    (halted,) = await w.accounts.blocks(TENANT)
    assert (halted.account, halted.cause) == ("limit.quota", "halted_at_limit")

    w = World()
    # Storage below its refusal share first, room to spare after.
    w.engine._platform = FakePlatform(observed(free=1), observed(free=50))
    run = await w.start("platform", worker("build"))
    assert run.state is RunState.HALTED and run.cause is Cause.LIMIT
    w.later()
    await w.resume(run)
    (refused,) = await w.accounts.blocks(TENANT)
    assert (refused.account, refused.cause) == ("limit.compute", "rejected_by_capacity")


async def test_a_provider_at_its_limit_past_the_ceiling_escalates_with_its_wait_recorded() -> None:
    w = World(model=FakeModel(answer="yes", at_limit=2))
    w.engine._options = EngineOptions(uncalibrated_margin=0.0, capacity_ceiling_seconds=60)
    run = await w.start("provider", llm("draft"))
    assert run.state is RunState.HALTED and run.cause is Cause.CAPACITY
    assert run.step_run("draft").state is StepState.STOPPED
    w.later()
    run = await w.resume(run)
    assert run.state is RunState.ESCALATED and run.cause is Cause.CAPACITY
    (waited,) = await w.accounts.blocks(TENANT)
    assert (waited.account, waited.cause) == ("limit.provider", "at_provider_limit")
    async with w.persistence.transaction(TENANT):
        (entry,) = [e for e in await w.ledger.entries(TENANT) if e.kind == "step.waited"]
    assert entry.content_digest is not None
    content = await w.objects.get(entry.content_digest)
    assert content is not None and json.loads(content)["ended"] == "ceiling"


@pytest.mark.parametrize(
    ("kinds", "account"),
    [
        (("quota",), "limit.quota"),
        (("currency",), "limit.budget"),
        (("tokens",), "limit.budget"),
        (("compute",), "limit.budget"),
        (("quota", "tokens"), "limit.budget"),
    ],
)
def test_a_refusal_at_the_run_s_limits_is_booked_by_the_kinds_that_did_not_fit(
    kinds: tuple[str, ...], account: str
) -> None:
    assert limit_account(kinds) == account


# --- the sums, per cause, per process and per period, from the records alone ---------------------


async def test_blocked_time_and_share_sum_per_cause_process_and_period() -> None:
    w = World()
    await every_cause(w)
    # The next day: one more run blocked on its budget, and one of the same process that is not.
    w.later(timedelta(days=1))
    small = Limits(compute=ComputeLimit(seconds=0.1, resource_class="cpu.small"))
    blocked = await w.start("budget", worker("build"), budget=small)
    w.later()
    await w.resume(blocked, budget=ENOUGH)
    clear = await w.start("budget", worker("build"))
    assert clear.state is RunState.FINISHED and clear.step_run("build").block is None

    blocks = await w.accounts.blocks(TENANT)
    sums = await w.accounts.sums(TENANT, "day")
    # What the test sums by hand from the blocks it produced.
    expected: dict[tuple[str, str, str], list[Block]] = defaultdict(list)
    for block in blocks:
        expected[(block.account, block.process, block.until.date().isoformat())].append(block)
    assert {(s.account, s.process, s.period) for s in sums} == set(expected)
    for s in sums:
        held = expected[(s.account, s.process, s.period)]
        assert s.seconds == sum(b.seconds for b in held)
        assert s.blocks == len(held)
        assert s.runs_held_up == len({b.run_id for b in held})
        assert s.steps_held_up == len({(b.run_id, b.step_id) for b in held})
        assert s.share == s.runs_held_up / s.runs

    day_one, day_two = AT.date().isoformat(), (AT + timedelta(days=1)).date().isoformat()
    budget = {s.period: s for s in sums if s.account == "limit.budget"}
    assert budget[day_one].runs == 1 and budget[day_one].share == 1.0
    assert budget[day_two].runs == 2, "two runs of the process were active that day"
    assert budget[day_two].share == 0.5, "one of the two was held up"
    human = [s for s in sums if s.process == "human"]
    assert {s.account for s in human} == {"wait.human", "wait.dependency"}

    month = await w.accounts.sums(TENANT, "month")
    (budget_month,) = [s for s in month if s.account == "limit.budget"]
    assert budget_month.period == AT.strftime("%Y-%m")
    assert budget_month.seconds == budget[day_one].seconds + budget[day_two].seconds
    assert budget_month.blocks == 2 and budget_month.runs == 3


async def test_the_sums_are_ordered_by_their_keys_never_by_a_figure() -> None:
    w = World()
    await every_cause(w)
    sums = await w.accounts.sums(TENANT, "week")
    keys = [(s.account, s.process, s.period) for s in sums]
    assert keys == sorted(keys)


# --- a figure of waiting on a person is that person's ---------------------------------------------


PERSONAL = {"actor", "person", "identity", "decider", "confirmed_by", "answered_by", "by", "who"}


def test_no_block_and_no_sum_has_a_field_that_can_hold_a_person() -> None:
    for kind in (Block, BlockedSum):
        assert not set(kind.model_fields) & PERSONAL, kind.__name__
    with pytest.raises(ValidationError):
        Block.model_validate(
            {
                "account": "wait.human",
                "cause": "awaiting_confirmation",
                "run_id": "run_1",
                "step_id": "ask",
                "process_version": "p@1",
                "since": AT,
                "until": AT,
                "seconds": 0,
                "actor": PERSON,
            }
        )


async def test_a_wait_on_a_person_is_readable_under_their_name_by_that_person_alone() -> None:
    w = World()
    await every_cause(w)

    # Anyone else: every block and every sum, and the person's name in none of them.
    blocks = await w.accounts.blocks(TENANT)
    sums = await w.accounts.sums(TENANT, "day")
    for read_out in (blocks, sums):
        text = json.dumps([v.document() for v in read_out], default=str)
        assert PERSON not in text, "the accounts name no person"
    assert any(s.account == "wait.human" for s in sums), "the wait is there, summed"
    assert await w.accounts.own(TENANT, OTHER) == (), "nobody else reads it as the person's"

    # Nor the records themselves: what the ledger names by digest carries no one.
    async with w.persistence.transaction(TENANT):
        entries = list(await w.ledger.entries(TENANT))
    for entry in entries:
        if entry.kind == "step.waited" and entry.content_digest is not None:
            content = await w.objects.get(entry.content_digest)
            assert content is not None and PERSON.encode() not in content
            assert "actor" not in parse(json.loads(content)).document()

    # The person: their own wait, joined to their own answer.
    (own,) = await w.accounts.own(TENANT, PERSON)
    assert own.account == "wait.human" and own.step_id == "ask"
    assert own.seconds >= GAP.total_seconds()


async def test_a_rehearsal_books_nothing() -> None:
    w = World()
    plan_steps = (wait("pause", 60),)
    plan = Plan(
        id="pln_1",
        command_id="cmd_1",
        goal="g",
        autonomy_level=3,
        steps=tuple(s for s, _ in plan_steps),
        results_in=PlanResult.RUN,
        status=PlanStatus.COMMISSIONED,
        commissioned=Commissioned(by=PERSON, at=AT),
    )
    run = await w.engine.start(
        StartRun(
            plan=plan,
            work={s.id: work for s, work in plan_steps},
            budget=ENOUGH,
            process_version="rehearsed@1",
            actor=PERSON,
            tenant=TENANT,
            rehearsal=True,
        )
    )
    assert run.state is RunState.FINISHED
    assert run.step_run("pause").state is StepState.SUCCEEDED
    assert await w.accounts.blocks(TENANT) == ()
    assert await w.accounts.sums(TENANT) == ()
