"""Autonomy levels 1 to 3, per process and per tool action, enforced at the step boundary
(UC-7.1 §2, ADR-0039).

Each case runs a plan through the run engine over fakes of every port and reads the run and the
ledger back: which steps waited for a person, which ran, which never reached their adapter.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from fakes import FakeClock, FakeConnector, FakeIdentifiers, FakeMaturities, FakeWorker
from fakes.connector import READ, WRITE

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryQueue,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.run.application.service import (
    ConfirmSteps,
    EngineOptions,
    ResumeRun,
    RunEngine,
    StartRun,
)
from taktus.components.run.domain.model import Cause, Run, RunError, RunState, StepState
from taktus.ports.administration import Administration
from taktus.ports.worker import ComputeLimit, Limits, QuotaLimit
from taktus.shared.v1 import (
    Autonomy,
    AutonomyLevel,
    Commissioned,
    ExactnessClass,
    Fallback,
    LedgerEntry,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    Step,
)

AT = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
BUDGET = Limits(
    compute=ComputeLimit(seconds=10, resource_class="cpu.small"), quota=QuotaLimit(units=20)
)
TENANT = "t"
PERSON = "idn_person"
WORKER = "worker.fake"
CONNECTOR = "connector.fake"


def rule(id: str, *, after: tuple[str, ...] = (), value: Any = 1) -> tuple[Step, dict[str, Any]]:
    step = Step(
        id=id,
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.EXACT,
        depends_on=after or None,
    )
    return step, {"rule": "constant", "value": value}


def failing(id: str, *, after: tuple[str, ...] = ()) -> tuple[Step, dict[str, Any]]:
    step, _ = rule(id, after=after)
    return step, {"rule": "check", "conditions": [{"value": 1, "equals": 2}]}


def worker(id: str, *, after: tuple[str, ...] = ()) -> tuple[Step, dict[str, Any]]:
    step = Step(
        id=id,
        method=Method.WORKER,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        fallback=Fallback(when="x", to=Method.HUMAN),
        requires=("shell.script",),
        depends_on=after or None,
    )
    return step, {"task": {"goal": "g", "acceptance": ["a"], "inputs": {"n": 1}}}


def call(id: str, operation: str, *, after: tuple[str, ...] = ()) -> tuple[Step, dict[str, Any]]:
    step = Step(
        id=id,
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.SOURCED,
        depends_on=after or None,
    )
    return step, {"rule": "connector", "operation": operation, "input": {"id": "x"}}


class World:
    def __init__(
        self,
        *definitions: tuple[Step, dict[str, Any]],
        level: AutonomyLevel = 3,
        actions: Mapping[str, AutonomyLevel] | None = None,
        maturities: FakeMaturities | None = None,
        wired: bool = True,
        administration: Administration | None = None,
    ) -> None:
        self.clock = FakeClock(AT)
        self.persistence = MemoryPersistence()
        self.runs = MemoryRepository(self.persistence, Run)
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.worker = FakeWorker()
        self.connector = FakeConnector()
        self.connector.reads["x"] = {"id": "x"}
        self.maturities = maturities if maturities is not None else FakeMaturities()
        self.queue = MemoryQueue(self.persistence, self.clock, lease_seconds=60)
        self.engine = RunEngine(
            runs=self.runs,
            work=self.persistence,
            objects=MemoryObjectStore(),
            ledger=self.ledger,
            provenance=MemoryProvenanceStore(self.persistence),
            workers=StaticWorkerPool([(WORKER, self.worker)]),
            connectors=StaticConnectorPool([(CONNECTOR, self.connector)]),
            clock=self.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            options=EngineOptions(uncalibrated_margin=0.0),
            maturities=self.maturities if wired else None,
            queue=self.queue,
            administration=administration,
        )
        self.level = level
        self.actions = dict(actions or {})
        self.steps = tuple(step for step, _ in definitions)
        self.work = {step.id: work for step, work in definitions}

    async def start(self, *, rehearsal: bool = False, stop_after: int | None = None) -> Run:
        plan = Plan(
            id="pln_1",
            command_id="cmd_1",
            goal="g",
            autonomy_level=self.level,
            steps=self.steps,
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=PERSON, at=AT),
        )
        return await self.engine.start(
            StartRun(
                plan=plan,
                work=self.work,
                budget=BUDGET,
                process_version="p@1",
                actor=PERSON,
                tenant=TENANT,
                actions=self.actions,
                rehearsal=rehearsal,
                stop_after=stop_after,
            )
        )

    async def confirm(
        self, run: Run, *steps: str, performed: bool = False, stop_after: int | None = None
    ) -> Run:
        return await self.engine.confirm(
            ConfirmSteps(
                run_id=run.id,
                steps=steps,
                actor=PERSON,
                tenant=TENANT,
                performed=performed,
                stop_after=stop_after,
            )
        )

    async def entries(self, run: Run) -> list[LedgerEntry]:
        async with self.persistence.transaction(TENANT):
            return list(await self.ledger.entries(TENANT, run.id))

    async def kinds(self, run: Run) -> list[str]:
        return [
            f"{e.kind}:{e.refs.step_id or ''}:{e.outcome or ''}".rstrip(":")
            for e in await self.entries(run)
        ]


def states(run: Run) -> dict[str, StepState]:
    return {s.step_id: s.state for s in run.step_runs}


def before(kinds: Sequence[str], first: str, then: str) -> bool:
    """Whether an entry starting with `first` comes before every entry starting with `then`."""
    a = next(i for i, k in enumerate(kinds) if k.startswith(first))
    return all(a < i for i, k in enumerate(kinds) if k.startswith(then))


# --- per process and per tool action: the lowest holds -------------------------------------------


async def test_an_action_at_level_two_waits_while_the_rest_of_a_level_three_run_continues() -> None:
    w = World(
        rule("prep"),
        worker("build", after=("prep",)),
        rule("report", after=("prep",)),
        rule("publish", after=("build",)),
        level=3,
        actions={"shell.script": 2},
    )
    run = await w.start()
    assert run.state is RunState.WAITING_HUMAN and run.cause is Cause.PERSON
    assert states(run) == {
        "prep": StepState.SUCCEEDED,
        "build": StepState.WAITING_HUMAN,
        "report": StepState.SUCCEEDED,  # the rest of the run continued
        "publish": StepState.PLANNED,  # it depends on the waiting step
    }
    assert w.worker.estimates == [] and w.worker.assignments == [], "nothing of it started"
    build = run.step_run("build")
    assert build.reason is not None and "held by the action shell.script" in build.reason
    kinds = await w.kinds(run)
    assert "step.awaiting:build:confirmation" in kinds
    assert [k for k in kinds if k.startswith("step.awaiting")] == [
        "step.awaiting:build:confirmation"
    ], "only the action at level 2 waited; the process's own steps did not"
    assert kinds[-1] == "run.waiting_human::person"

    run = await w.confirm(run, "build")
    assert run.state is RunState.FINISHED
    assert run.step_run("build").confirmed_by == PERSON
    assert len(w.worker.assignments) == 1
    kinds = await w.kinds(run)
    assert before(kinds, "step.confirmed:build", "step.admitted:build")
    assert "step.awaiting:publish:confirmation" not in kinds, "publish ran without asking"


async def test_the_lowest_of_several_actions_on_one_step_holds() -> None:
    w = World(call("read", READ), level=3, actions={"fake.records": 2, READ: 1})
    run = await w.start()
    # A read does not act, so at level 1 it runs: Taktus supplies analyses.
    assert run.state is RunState.FINISHED
    w = World(call("write", WRITE), level=3, actions={"fake.records": 2, WRITE: 1})
    run = await w.start()
    assert run.step_run("write").state is StepState.WAITING_HUMAN
    (awaiting,) = [e for e in await w.entries(run) if e.kind == "step.awaiting"]
    assert awaiting.outcome == "performance", "level 1 of the operation held, not 2"


# --- each level behaves as UC-7.1 §1 names it ---------------------------------------------------


async def test_at_level_two_no_step_starts_before_a_person_confirmed_it() -> None:
    w = World(
        rule("prep"), worker("build", after=("prep",)), rule("done", after=("build",)), level=2
    )
    run = await w.start()
    assert run.state is RunState.WAITING_HUMAN
    assert states(run)["prep"] is StepState.WAITING_HUMAN
    run = await w.confirm(run, "prep")
    assert states(run)["build"] is StepState.WAITING_HUMAN and w.worker.estimates == []
    run = await w.confirm(run, "build")
    run = await w.confirm(run, "done")
    assert run.state is RunState.FINISHED
    kinds = await w.kinds(run)
    for step in ("prep", "build", "done"):
        assert before(kinds, f"step.confirmed:{step}", f"step.admitted:{step}"), step
        assert before(kinds, f"step.confirmed:{step}", f"step.started:{step}"), step
    confirmed = [e for e in await w.entries(run) if e.kind == "step.confirmed"]
    assert {e.refs.actor for e in confirmed} == {PERSON}


async def test_at_level_one_taktus_proposes_and_executes_no_act() -> None:
    w = World(
        rule("analyse"),
        worker("build", after=("analyse",)),
        call("write", WRITE, after=("analyse",)),
        call("read", READ, after=("analyse",)),
        level=1,
    )
    run = await w.start()
    assert run.state is RunState.WAITING_HUMAN
    assert states(run) == {
        "analyse": StepState.SUCCEEDED,  # the analysis Taktus supplies
        "build": StepState.WAITING_HUMAN,
        "write": StepState.WAITING_HUMAN,
        "read": StepState.SUCCEEDED,  # a read acts on nothing
    }
    assert w.worker.estimates == [] and w.worker.assignments == []
    assert [c[0] for c in w.connector.calls] == [READ], "the write was never called"
    awaiting = [e for e in await w.entries(run) if e.kind == "step.awaiting"]
    assert {e.outcome for e in awaiting} == {"performance"}
    assert all(e.content_digest is not None for e in awaiting), "the proposal is recorded"

    with pytest.raises(RunError, match="level 1"):
        await w.confirm(run, "build")  # a confirmation would let Taktus act
    run = await w.confirm(run, "build", "write", performed=True)
    assert run.state is RunState.FINISHED
    assert w.worker.assignments == [] and w.connector.acted == 0, "the person acted, not Taktus"
    assert run.step_run("write").confirmed_by == PERSON
    performed = [e for e in await w.entries(run) if e.kind == "step.performed"]
    assert {(e.refs.step_id, e.refs.actor) for e in performed} == {
        ("build", PERSON),
        ("write", PERSON),
    }


async def test_at_level_three_the_run_proceeds_without_confirmations() -> None:
    w = World(rule("prep"), worker("build", after=("prep",)), call("write", WRITE), level=3)
    run = await w.start()
    assert run.state is RunState.FINISHED
    kinds = await w.kinds(run)
    assert not [k for k in kinds if k.startswith(("step.awaiting", "step.confirmed"))]
    assert w.connector.acted == 1 and len(w.worker.assignments) == 1


async def test_an_answer_is_refused_where_nothing_waits_for_it() -> None:
    w = World(rule("prep"), rule("next", after=("prep",)), level=2)
    run = await w.start()
    with pytest.raises(RunError, match="does not wait"):
        await w.confirm(run, "next")
    with pytest.raises(RunError, match="waits for a confirmation"):
        await w.confirm(run, "prep", performed=True)
    with pytest.raises(RunError, match="has no step"):
        await w.confirm(run, "nope")


async def test_a_confirmation_hands_the_run_back_to_a_runner() -> None:
    w = World(rule("prep"), rule("next", after=("prep",)), level=2)
    run = await w.start()
    claim = ResumeRun(run_id=run.id, actor="runner", tenant=TENANT, on_claim=True)
    assert (await w.engine.resume(claim)).state is RunState.WAITING_HUMAN, (
        "a runner's claim does not continue what waits for a person"
    )
    run = await w.engine.confirm(
        ConfirmSteps(run_id=run.id, steps=("prep",), actor=PERSON, tenant=TENANT, enqueue=True)
    )
    assert run.state is RunState.WAITING_HUMAN and run.step_run("prep").confirmed_by == PERSON
    async with w.persistence.transaction(TENANT):
        jobs = await w.queue.claim(TENANT, "runner", 5)
    assert [j.payload["run_id"] for j in jobs] == [run.id]
    run = await w.engine.resume(claim)
    assert run.step_run("prep").state is StepState.SUCCEEDED
    assert (
        run.state is RunState.WAITING_HUMAN
        and run.step_run("next").state is StepState.WAITING_HUMAN
    )


async def test_a_resume_of_a_waiting_run_is_no_confirmation() -> None:
    w = World(rule("prep"), level=2)
    run = await w.start()
    run = await w.engine.resume(ResumeRun(run_id=run.id, actor=PERSON, tenant=TENANT))
    assert run.state is RunState.WAITING_HUMAN
    assert run.step_run("prep").state is StepState.WAITING_HUMAN


# --- from level 3, verified adapters only (NTC-0051) ---------------------------------------------


@pytest.mark.parametrize("family", ["worker", "connector"])
async def test_a_level_three_step_is_not_run_on_an_adapter_below_verified(family: str) -> None:
    adapter = WORKER if family == "worker" else CONNECTOR
    step = worker("act") if family == "worker" else call("act", READ)
    missing = ("the conformance suite has not been recorded as passed",)
    w = World(rule("prep"), step, level=3, maturities=FakeMaturities({adapter: missing}))
    run = await w.start()
    assert run.state is RunState.HALTED and run.cause is Cause.MATURITY
    act = run.step_run("act")
    assert act.state is StepState.REJECTED
    assert act.reason is not None and "'act'" in act.reason and adapter in act.reason
    assert missing[0] in act.reason
    assert w.worker.estimates == [] and w.worker.assignments == []
    assert w.connector.calls == []
    assert (await w.kinds(run))[-2:] == [
        "step.rejected:act:rejected_by_maturity",
        "run.halted::maturity",
    ]


async def test_the_threshold_is_not_asked_below_level_three() -> None:
    below = FakeMaturities({WORKER: ("nothing recorded",)})
    w = World(worker("build"), level=3, actions={"shell.script": 2}, maturities=below)
    run = await w.start()
    run = await w.confirm(run, "build")
    assert run.state is RunState.FINISHED, "a confirmed step at level 2 runs on any adapter"
    assert below.asked == []


async def test_without_a_maturity_record_no_level_three_step_reaches_an_adapter() -> None:
    w = World(rule("prep"), worker("build", after=("prep",)), level=3, wired=False)
    run = await w.start()
    assert run.state is RunState.HALTED and run.cause is Cause.MATURITY
    assert run.step_run("prep").state is StepState.SUCCEEDED, "a rule needs no adapter"
    assert w.worker.assignments == []


async def test_a_rehearsal_is_asked_for_neither_confirmation_nor_maturity() -> None:
    below = FakeMaturities({WORKER: ("nothing recorded",)})
    w = World(rule("prep"), worker("build", after=("prep",)), level=2, maturities=below)
    run = await w.start(rehearsal=True)
    assert run.state is RunState.FINISHED
    w = World(worker("build"), level=3, maturities=below)
    assert (await w.start(rehearsal=True)).state is RunState.FINISHED


# --- what no level switches off --------------------------------------------------------------


@pytest.mark.parametrize("level", [1, 2, 3])
async def test_no_level_switches_off_the_stop_the_reports_or_the_escalation(level: int) -> None:
    autonomy_level: AutonomyLevel = level  # type: ignore[assignment]
    # The escalation duty: a failing step escalates at every level.
    w = World(rule("prep"), failing("check", after=("prep",)), level=autonomy_level)
    run = await w.start()
    for _ in range(2):
        if run.state is RunState.WAITING_HUMAN:
            run = await w.confirm(run, *(s.step_id for s in run.waiting()))
    assert run.state is RunState.ESCALATED and run.cause is Cause.FAILURE
    # The reports: every state change of every step is in the ledger, whatever the level.
    kinds = await w.kinds(run)
    assert "step.finished:prep:succeeded" in kinds and "step.finished:check:failed" in kinds
    assert kinds[-1] == "run.escalated::failure"

    # The emergency stop: a stop requested at a boundary halts the run at every level.
    w = World(rule("one"), rule("two", after=("one",)), level=autonomy_level)
    run = await w.start(stop_after=1)
    if run.state is RunState.WAITING_HUMAN:
        run = await w.confirm(run, "one", stop_after=1)
    assert run.state is RunState.HALTED and run.cause is Cause.STOP
    assert run.step_run("two").state is not StepState.SUCCEEDED


async def test_a_run_waiting_for_a_person_is_stopped_at_once() -> None:
    w = World(rule("prep"), level=2)
    run = await w.start()
    await w.engine.request_stop(run.id, TENANT)
    stored = await w.engine.resume(ResumeRun(run_id=run.id, actor=PERSON, tenant=TENANT))
    kinds = await w.kinds(stored)
    assert "run.halted::stop" in kinds
    assert before(kinds, "run.halted::stop", "run.resumed")


def test_no_field_of_the_statement_reaches_the_stop_the_reports_or_the_escalation() -> None:
    """The statement is closed: what a level can be configured with is these fields, and none
    of them names the stop, a report or the escalation. A new field fails here and is looked at
    against UC-7.1 before it passes."""
    assert set(Autonomy.model_fields) == {"level", "reason", "toward_next", "actions", "history"}
    with pytest.raises(ValueError):
        Autonomy.model_validate(
            {"level": 3, "reason": "r", "toward_next": "t", "emergency_stop": False}
        )


# --- no level is reserved for a size or kind of tenant ------------------------------------------


@pytest.mark.parametrize("level", [1, 2, 3])
async def test_a_tenant_of_one_person_sets_any_of_the_three_levels(level: int) -> None:
    autonomy_level: AutonomyLevel = level  # type: ignore[assignment]
    w = World(rule("only"), level=autonomy_level)
    run = await w.start()
    if level == 2:
        run = await w.confirm(run, "only")
    assert run.state is RunState.FINISHED
    assert {e.refs.actor for e in await w.entries(run) if e.refs.actor} == {PERSON}


# --- a credential that administers this instance's platform (ADR-0025, ADR-0052) -----------------


def with_credential(
    definition: tuple[Step, dict[str, Any]], name: str
) -> tuple[Step, dict[str, Any]]:
    step, work = definition
    return step, {**work, "credentials": [{"name": name, "injected_as": "env"}]}


@pytest.mark.parametrize("family", ["worker", "connector"])
async def test_a_step_naming_a_credential_that_administers_this_platform_is_not_run(
    family: str,
) -> None:
    """Issue #83: admission refuses the step, naming the step, the credential and the platform;
    the run halts with cause `administration` before anything reaches an adapter."""
    step = worker("act") if family == "worker" else call("act", READ)
    here = Administration(platform="here", declared={"KUBE": ("here",)})
    w = World(rule("prep"), with_credential(step, "KUBE"), administration=here)
    run = await w.start()
    assert run.state is RunState.HALTED and run.cause is Cause.ADMINISTRATION
    act = run.step_run("act")
    assert act.state is StepState.REJECTED
    assert act.reason is not None
    assert "'act'" in act.reason and "'KUBE'" in act.reason and "'here'" in act.reason
    assert w.worker.assignments == [] and w.connector.calls == []
    assert (await w.kinds(run))[-2:] == [
        "step.rejected:act:rejected_by_administration",
        "run.halted::administration",
    ]


async def test_an_undeclared_credential_is_refused_once_the_platform_is_named() -> None:
    """DEC-0133, provisional Option A: a credential nobody declared is refused too."""
    w = World(
        with_credential(call("act", READ), "TOKEN"),
        administration=Administration(platform="here"),
    )
    run = await w.start()
    assert run.cause is Cause.ADMINISTRATION
    reason = run.step_run("act").reason
    assert reason is not None and "undeclared" in reason


@pytest.mark.parametrize(
    "administration",
    [
        Administration(platform="here", declared={"TOKEN": ()}),
        Administration(platform="here", declared={"TOKEN": ("elsewhere",)}),
        Administration(declared={"TOKEN": ("here",)}),
    ],
    ids=["declared-none", "another-platform", "no-platform-named"],
)
async def test_a_credential_administering_nothing_here_runs(
    administration: Administration,
) -> None:
    w = World(with_credential(call("act", READ), "TOKEN"), administration=administration)
    run = await w.start()
    assert run.state is RunState.FINISHED
