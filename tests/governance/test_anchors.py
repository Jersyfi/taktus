"""Anchors at the step boundary, configurable per tenant, raising decision requests in the
product (UC-7.4 §2, the anchor condition of UC-7.1 §2, ADR-0008, ADR-0015, ADR-0042).

Each case runs a plan through the run engine over fakes of every port, with the governance,
decision and identity components wired as the composition root wires them, and reads back the
run, the requests, the register and the ledger.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fakes import FakeConnector, FakeIdentifiers, FakeMaturities, FakeWorker
from fakes.clock import FakeClock
from fakes.connector import READ, WRITE
from fakes.identity import directory
from pydantic import ValidationError

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryObjectStore,
    MemoryProvenanceStore,
    MemoryQueue,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.decision.application.service import (
    AnswerRequest,
    ConfirmRequest,
    NotAnswerable,
    NotTheDecider,
    RaiseRequest,
)
from taktus.components.decision.application.service import NotRaised as RequestNotRaised
from taktus.components.decision.domain.model import Request
from taktus.components.governance.application.service import AnchorsRefused, ConfigureAnchors
from taktus.components.governance.domain.model import AnchorConfiguration
from taktus.components.governance.domain.service.anchors import applying, matches
from taktus.components.run.application.query import BlockedTime
from taktus.components.run.application.service import (
    ConfirmSteps,
    DecideSteps,
    EngineOptions,
    ResumeRun,
    RunEngine,
    StartRun,
)
from taktus.components.run.domain.model import Cause, Run, RunError, RunState, StepState
from taktus.components.run.ports import Draft, NotRaised
from taktus.composition.decisions import decision_wiring
from taktus.ports.worker import ComputeLimit, Limits, QuotaLimit
from taktus.shared.v1 import (
    AutonomyLevel,
    Commissioned,
    DecisionStatus,
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
STARTER = "idn_starter"
DECIDER = "idn_ada"
COLLEAGUE = "idn_bo"
OUTSIDER = "idn_cy"
WORKER = "worker.fake"
CONNECTOR = "connector.fake"


def anchor(id: str, kind: str, role: str = "finance.lead", **applies_to: Any) -> dict[str, Any]:
    return {
        "id": id,
        "class": kind,
        "act": f"the act of {id}",
        "applies_to": applies_to,
        "decider": {"role": role},
    }


LEGAL_WRITE = anchor("anc-write", "legal", actions=[WRITE])
CORRECTION = anchor("anc-correction", "correction", actions=["correction.*"])
CONFIGURED = {"anchors": [LEGAL_WRITE, CORRECTION]}


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


class World:
    def __init__(
        self,
        *definitions: tuple[Step, dict[str, Any]],
        level: AutonomyLevel = 3,
        configuration: Mapping[str, Any] | None = CONFIGURED,
        decision_days: int = 3,
    ) -> None:
        self.clock = FakeClock(AT)
        self.people = directory((TENANT,), clock=self.clock)
        self.persistence = self.people.persistence
        self.ledger = self.people.ledger
        self.runs = MemoryRepository(self.persistence, Run)
        self.worker = FakeWorker()
        self.connector = FakeConnector()
        self.connector.reads["x"] = {"id": "x"}
        self.queue = MemoryQueue(self.persistence, self.clock, lease_seconds=60)
        self.decisions = decision_wiring(
            lambda kind: MemoryRepository(self.persistence, kind),
            self.persistence,
            self.ledger,
            self.clock,
            self.people.directory,
        )
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
            options=EngineOptions(uncalibrated_margin=0.0, decision_days=decision_days),
            maturities=FakeMaturities(),
            queue=self.queue,
            anchors=self.decisions.anchors,
            decisions=self.decisions.requests,
        )
        self.level = level
        self.configuration = configuration
        self.steps = tuple(step for step, _ in definitions)
        self.work = {step.id: work for step, work in definitions}
        self.keys: dict[str, str] = {}

    async def setup(self) -> World:
        directory = self.people.directory
        await directory.add(TENANT, STARTER, (TENANT,))
        await directory.add(TENANT, DECIDER, (TENANT, "finance"), roles=("finance.lead",))
        await directory.add(TENANT, COLLEAGUE, (TENANT, "finance"), roles=("finance.lead",))
        await directory.add(TENANT, OUTSIDER, (TENANT, "finance"))
        if self.configuration is not None:
            await self.decisions.configure.execute(
                ConfigureAnchors(tenant=TENANT, document=self.configuration, actor=STARTER)
            )
        return self

    async def start(self, *, rehearsal: bool = False) -> Run:
        plan = Plan(
            id="pln_1",
            command_id="cmd_1",
            goal="g",
            autonomy_level=self.level,
            steps=self.steps,
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=STARTER, at=AT),
        )
        return await self.engine.start(
            StartRun(
                plan=plan,
                work=self.work,
                budget=BUDGET,
                process_version="p@1",
                actor=STARTER,
                tenant=TENANT,
                rehearsal=rehearsal,
            )
        )

    async def request(self, request_id: str) -> Request:
        async with self.persistence.transaction(TENANT):
            found = await MemoryRepository(self.persistence, Request).get(TENANT, request_id)
        assert found is not None
        return found

    async def answer(self, request_id: str, *, by: str = DECIDER, **given: str) -> str:
        answered = await self.decisions.answer.execute(
            AnswerRequest(tenant=TENANT, request_id=request_id, identity=by, **given)
        )
        return answered.message

    async def confirm(self, request_id: str, *, by: str = DECIDER, yes: bool = True) -> Run:
        confirmed = await self.decisions.confirm.execute(
            ConfirmRequest(tenant=TENANT, request_id=request_id, identity=by, confirmed=yes)
        )
        run_id = confirmed.request.request.raised_by.run
        return await self.engine.decide(DecideSteps(run_id=run_id, actor=by, tenant=TENANT))

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


def requests_of(run: Run, step: str) -> tuple[str, ...]:
    anchoring = run.step_run(step).anchoring
    assert anchoring is not None
    return anchoring.requests


# --- a tenant's anchors are configuration, and never emptied -------------------------------------


async def test_a_configuration_that_empties_the_legal_or_the_correction_class_is_refused() -> None:
    w = await World(configuration=None).setup()
    for document in ({"anchors": [CORRECTION]}, {"anchors": [LEGAL_WRITE]}, {"anchors": []}):
        with pytest.raises(AnchorsRefused, match=r"never emptied|at least 1"):
            await w.decisions.configure.execute(
                ConfigureAnchors(tenant=TENANT, document=document, actor=STARTER)
            )
    held = await w.decisions.anchors.of(TENANT)
    assert held.shipped, "nothing refused was stored: the tenant still holds the shipped default"
    assert {a.class_ for a in held.anchors} == {"legal", "correction"}


async def test_the_strategic_class_may_be_reduced_to_nothing() -> None:
    w = await World(configuration=None).setup()
    stored = await w.decisions.configure.execute(
        ConfigureAnchors(tenant=TENANT, document=CONFIGURED, actor=STARTER)
    )
    assert stored.of_class("strategic") == () and not stored.shipped
    assert await w.decisions.anchors.of(TENANT) == stored
    async with w.persistence.transaction(TENANT):
        kinds = [e.kind for e in await w.ledger.entries(TENANT)]
    assert "anchors.configured" in kinds


def test_an_anchor_that_selects_a_risk_class_the_configuration_does_not_define_is_refused() -> None:
    with pytest.raises(ValidationError, match="does not define"):
        AnchorConfiguration.model_validate(
            {
                "id": TENANT,
                "tenant": TENANT,
                "anchors": [
                    CORRECTION,
                    anchor("anc-pay", "legal", risk_classes=["financial.high"]),
                ],
            }
        )


def test_an_anchor_selects_by_action_by_process_and_by_risk_class() -> None:
    configuration = AnchorConfiguration.model_validate(
        {
            "id": TENANT,
            "tenant": TENANT,
            "anchors": [
                anchor("anc-pay", "legal", actions=["payment.release:*"]),
                anchor("anc-high", "legal", risk_classes=["financial.high"]),
                anchor("anc-release", "strategic", processes=["release-train"]),
                # Every selector given must match: a release, in the release train.
                anchor("anc-both", "strategic", actions=["vcs.release"], processes=["train"]),
                CORRECTION,
            ],
            "risk_classes": {"financial.high": ["payment.release:large", "ledger.*"]},
        }
    )

    def named(process: str, *actions: str) -> set[str]:
        return {a.id for a in applying(configuration, process=process, actions=actions)}

    assert named("p", "payment.release") == {"anc-pay"}
    assert named("p", "payment.release:large") == {"anc-pay", "anc-high"}
    assert named("p", "ledger.journal.post") == {"anc-high"}
    assert named("release-train", "shell.script") == {"anc-release"}
    assert named("train", "vcs.release") == {"anc-both"}
    assert named("p", "vcs.release") == set(), "the process selector does not match"
    assert named("p", "correction.execute") == {"anc-correction"}
    assert named("p", "repository.read") == set()


@pytest.mark.parametrize(
    ("pattern", "action", "expected"),
    [
        ("code.*", "code.edit", True),
        ("code.*", "code.edit.inline", True),
        ("code.*", "codex.edit", False),
        ("vcs.push:protected", "vcs.push:protected", True),
        ("vcs.push:protected", "vcs.push", False),
        ("vcs.push", "vcs.push:protected", True),
        ("payment.release:*", "payment.release", True),
        ("a.*.c", "a.b.c", True),
        ("a.b", "a.b.c", False),
    ],
)
def test_a_capability_pattern_matches_segment_by_segment(
    pattern: str, action: str, expected: bool
) -> None:
    assert matches(pattern, action) is expected


# --- an anchored act halts the run at the step boundary, at every level --------------------------


@pytest.mark.parametrize("level", [1, 2, 3])
async def test_no_autonomy_level_overrides_an_anchor(level: AutonomyLevel) -> None:
    w = await World(call("write", WRITE), level=level).setup()
    run = await w.start()
    assert run.state is RunState.WAITING_HUMAN and run.cause is Cause.PERSON
    assert states(run) == {"write": StepState.WAITING_HUMAN}
    assert w.connector.calls == [], "nothing of the anchored step started, at any level"
    (request_id,) = requests_of(run, "write")
    request = await w.request(request_id)
    assert request.status is DecisionStatus.OPEN and request.decider == "finance.lead"
    kinds = await w.kinds(run)
    assert "step.anchored:write:legal" in kinds
    assert not any(k.startswith("step.awaiting") for k in kinds), "the anchor asked first"


async def test_the_halt_is_at_the_boundary_and_the_rest_of_the_run_continues() -> None:
    w = await World(
        rule("prep"),
        call("write", WRITE, after=("prep",)),
        rule("report", after=("prep",)),
        rule("after", after=("write",)),
    ).setup()
    run = await w.start()
    assert states(run) == {
        "prep": StepState.SUCCEEDED,
        "write": StepState.WAITING_HUMAN,
        "report": StepState.SUCCEEDED,
        "after": StepState.PLANNED,
    }
    kinds = await w.kinds(run)
    assert not any(k.startswith(("step.admitted:write", "step.started:write")) for k in kinds)
    assert kinds[-1] == "run.waiting_human::person"


async def test_a_rehearsal_acts_on_nothing_and_is_asked_no_anchor() -> None:
    w = await World(call("read", READ), call("write", WRITE)).setup()
    run = await w.start(rehearsal=True)
    assert run.step_run("write").anchoring is None
    assert not any(k.startswith("step.anchored") for k in await w.kinds(run))


async def test_a_tenant_that_configured_nothing_holds_the_shipped_default() -> None:
    w = await World(call("write", WRITE), configuration=None).setup()
    run = await w.start()
    assert run.state is RunState.FINISHED, "the default anchors no fake write"
    w = await World(rule("fix"), configuration=None).setup()
    held = await w.decisions.anchors.applying(TENANT, "p", ("correction.execute",))
    assert [a.id for a in held] == ["anc-correction"]


# --- the request has one shape; one missing a part is not raised ---------------------------------


async def test_the_request_holds_every_part_of_the_one_shape() -> None:
    w = await World(call("write", WRITE)).setup()
    run = await w.start()
    request = await w.request(requests_of(run, "write")[0])
    shaped = request.request
    assert shaped.situation and shaped.question.endswith("?")
    assert len(shaped.options) == 2
    (recommended,) = [o for o in shaped.options if o.recommended]
    assert recommended.reason and all(o.consequence for o in shaped.options)
    assert shaped.blocking == (run.id, f"{run.id}/write")
    assert shaped.due == (AT + timedelta(days=3)).date()
    assert shaped.raised_by.run == run.id and shaped.raised_by.step == "write"
    assert shaped.channel.address == "role:finance.lead"


async def test_a_request_missing_a_part_is_not_raised() -> None:
    w = await World().setup()
    complete = RaiseRequest(
        tenant=TENANT,
        id="dr_x",
        run="run_x",
        step="s",
        class_="legal",
        situation="s",
        question="q?",
        options=[
            {"id": "A", "proposal": "a", "recommended": True, "reason": "r"},
            {"id": "B", "proposal": "b", "recommended": False},
        ],
        blocking=["run_x"],
        due=AT.date(),
        decider="finance.lead",
    )
    raising = w.decisions.requests._raising
    for missing in (
        {"situation": " "},
        {"question": ""},
        {"options": [{"id": "A", "proposal": "a", "recommended": True, "reason": "r"}]},
        {"options": [{"id": "A", "proposal": "a", "recommended": True}, complete.options[1]]},
        {"decider": ""},
    ):
        with pytest.raises(RequestNotRaised):
            await raising.execute(RaiseRequest(**{**complete.__dict__, **missing}))
    async with w.persistence.transaction(TENANT):
        assert await MemoryRepository(w.persistence, Request).list(TENANT) == []


async def test_an_anchored_step_whose_request_is_not_raised_fails_without_its_act() -> None:
    w = await World(call("write", WRITE)).setup()

    class Refusing:
        async def raise_request(self, tenant: str, draft: Draft) -> None:
            raise NotRaised("the situation is missing")

        async def verdict(self, tenant: str, request_id: str) -> None:
            return None

    w.engine._decisions = Refusing()
    run = await w.start()
    assert run.state is RunState.ESCALATED and run.cause is Cause.FAILURE
    assert run.step_run("write").state is StepState.FAILED
    assert "not raised" in (run.step_run("write").reason or "")
    assert w.connector.calls == [], "the act was not performed"


# --- a free-text answer is reflected back and takes effect only once confirmed -------------------


async def test_a_free_text_answer_is_not_acted_on_until_its_reading_is_confirmed() -> None:
    w = await World(call("write", WRITE), rule("after", after=("write",))).setup()
    run = await w.start()
    (request_id,) = requests_of(run, "write")

    message = await w.answer(request_id, text="Go with A, but tell the auditors.")
    assert "option A" in message and "tell the auditors" in message
    assert "does not act on it" in message and "Confirm" in message
    assert (await w.request(request_id)).status is DecisionStatus.INTERPRETED
    run = await w.engine.decide(DecideSteps(run_id=run.id, actor=DECIDER, tenant=TENANT))
    assert run.state is RunState.WAITING_HUMAN, "the run still waits for the confirmation"
    assert w.connector.calls == []

    run = await w.confirm(request_id)
    assert run.state is RunState.FINISHED
    assert [c[0] for c in w.connector.calls] == [WRITE]
    write = run.step_run("write")
    assert write.anchoring is not None and write.anchoring.verdict == "proceed"
    kinds = await w.kinds(run)
    assert kinds.index("step.decided:write:proceed") < kinds.index("step.admitted:write")


async def test_an_answer_no_option_can_be_read_from_changes_nothing() -> None:
    w = await World(call("write", WRITE)).setup()
    run = await w.start()
    (request_id,) = requests_of(run, "write")
    for unread in ("sounds good to me", "either A or B"):
        message = await w.answer(request_id, text=unread)
        assert "could not read one option" in message
        assert (await w.request(request_id)).status is DecisionStatus.ANSWERED
    with pytest.raises(NotAnswerable):
        await w.confirm(request_id)


async def test_a_reading_rejected_takes_nothing_into_effect() -> None:
    w = await World(call("write", WRITE)).setup()
    run = await w.start()
    (request_id,) = requests_of(run, "write")
    await w.answer(request_id, option="A")
    run = await w.confirm(request_id, yes=False)
    assert run.state is RunState.WAITING_HUMAN
    assert (await w.request(request_id)).status is DecisionStatus.OPEN
    assert w.connector.calls == []


async def test_only_a_holder_of_the_role_answers_and_only_the_one_who_answered_confirms() -> None:
    w = await World(call("write", WRITE)).setup()
    run = await w.start()
    (request_id,) = requests_of(run, "write")
    with pytest.raises(NotTheDecider):
        await w.answer(request_id, option="A", by=OUTSIDER)
    await w.answer(request_id, option="A", by=DECIDER)
    with pytest.raises(NotTheDecider):
        await w.confirm(request_id, by=COLLEAGUE)


async def test_an_anchored_step_is_not_confirmed_past_its_request() -> None:
    w = await World(call("write", WRITE), level=2).setup()
    run = await w.start()
    with pytest.raises(RunError, match="anchored"):
        await w.engine.confirm(
            ConfirmSteps(run_id=run.id, steps=("write",), actor=DECIDER, tenant=TENANT)
        )


# --- every answered request is an entry in the register ------------------------------------------


async def test_an_answered_request_is_an_entry_in_the_register_linked_to_run_and_request() -> None:
    w = await World(call("write", WRITE)).setup()
    run = await w.start()
    (request_id,) = requests_of(run, "write")
    await w.answer(request_id, text="B")
    run = await w.confirm(request_id)
    request = await w.request(request_id)
    assert request.status is DecisionStatus.APPLIED and request.request.outcome is not None
    (entry,) = await w.decisions.queries.entries(TENANT)
    assert entry.id == request.request.outcome
    assert (entry.run_id, entry.step_id, entry.request_id) == (run.id, "write", request_id)
    assert entry.option == "B" and entry.decided_by == DECIDER
    applied = [e for e in await w.entries(run) if e.kind == "decision.applied"]
    assert [(e.refs.run_id, e.refs.decision_request_id) for e in applied] == [(run.id, request_id)]


async def test_a_declined_act_is_not_performed_and_a_resume_asks_again() -> None:
    w = await World(call("write", WRITE)).setup()
    run = await w.start()
    (first,) = requests_of(run, "write")
    await w.answer(first, option="B")
    run = await w.confirm(first)
    assert run.state is RunState.HALTED and run.cause is Cause.DECLINED
    assert run.step_run("write").state is StepState.REJECTED
    assert w.connector.calls == []

    run = await w.engine.resume(ResumeRun(run_id=run.id, actor=STARTER, tenant=TENANT))
    assert run.state is RunState.WAITING_HUMAN
    (second,) = requests_of(run, "write")
    assert second != first and run.step_run("write").anchoring.round == 2  # type: ignore[union-attr]
    assert w.connector.calls == []


# --- nothing waits silently ----------------------------------------------------------------------


async def test_waiting_work_is_in_the_run_s_history_and_the_decider_s_list_overdue_shown() -> None:
    w = await World(call("write", WRITE), decision_days=1).setup()
    run = await w.start()
    (request_id,) = requests_of(run, "write")
    assert request_id in (run.reason or "") and "finance.lead" in (run.reason or "")
    raised = [e for e in await w.entries(run) if e.kind == "decision.raised"]
    assert [e.refs.decision_request_id for e in raised] == [request_id]

    listed = await w.decisions.queries.addressed_to(TENANT, DECIDER)
    assert [(a.request.id, a.overdue) for a in listed] == [(request_id, False)]
    assert await w.decisions.queries.addressed_to(TENANT, OUTSIDER) == []

    w.clock.current += timedelta(days=2)
    (late,) = await w.decisions.queries.addressed_to(TENANT, COLLEAGUE)
    assert late.overdue, "a request past its due date is shown as such"


# --- a decider's response times are theirs ----------------------------------------------------


async def test_another_identity_cannot_read_a_decider_s_response_time_under_their_name() -> None:
    w = await World(call("write", WRITE)).setup()
    run = await w.start()
    (request_id,) = requests_of(run, "write")
    w.clock.current += timedelta(hours=5)
    await w.answer(request_id, option="A")
    await w.confirm(request_id)

    own = await w.decisions.queries.response_times(TENANT, DECIDER)
    assert [o.request_id for o in own.own] == [request_id]
    assert own.own[0].seconds >= 5 * 3600

    for reader in (COLLEAGUE, OUTSIDER):
        theirs = await w.decisions.queries.response_times(TENANT, reader)
        assert theirs.own == ()
        assert DECIDER not in str(theirs.document()), "nobody else reads it under the name"
        for aggregate in (*theirs.by_role, *theirs.by_department):
            assert aggregate.median_seconds is None and aggregate.decisions is None
            assert aggregate.withheld, "one decider's aggregate is that person's number"


async def test_response_times_are_aggregated_by_role_and_department_over_two_deciders() -> None:
    w = await World(call("write", WRITE), call("write-two", WRITE)).setup()
    run = await w.start()
    first, second = requests_of(run, "write")[0], requests_of(run, "write-two")[0]
    await w.answer(first, option="A", by=DECIDER)
    await w.confirm(first, by=DECIDER)
    await w.answer(second, option="A", by=COLLEAGUE)
    await w.confirm(second, by=COLLEAGUE)
    read = await w.decisions.queries.response_times(TENANT, OUTSIDER)
    assert [(a.group, a.decisions) for a in read.by_role] == [("finance.lead", 2)]
    assert [(a.group, a.decisions) for a in read.by_department] == [("finance", 2)]
    assert read.by_role[0].median_seconds is not None
    assert DECIDER not in str(read.document()) and COLLEAGUE not in str(read.document())


async def test_a_decision_taken_on_the_surface_hands_the_run_to_a_runner() -> None:
    w = await World(call("write", WRITE)).setup()
    run = await w.start()
    (request_id,) = requests_of(run, "write")
    await w.answer(request_id, option="A")
    await w.decisions.confirm.execute(
        ConfirmRequest(tenant=TENANT, request_id=request_id, identity=DECIDER)
    )
    run = await w.engine.decide(
        DecideSteps(run_id=run.id, actor=DECIDER, tenant=TENANT, enqueue=True)
    )
    assert run.state is RunState.WAITING_HUMAN and w.connector.calls == []
    async with w.persistence.transaction(TENANT):
        (job,) = await w.queue.claim(TENANT, "runner-a", 5)
    assert job.payload == {"run_id": run.id}
    run = await w.engine.resume(
        ResumeRun(run_id=run.id, actor="runner-a", tenant=TENANT, on_claim=True)
    )
    assert run.state is RunState.FINISHED and [c[0] for c in w.connector.calls] == [WRITE]


# --- an anchor's halt is a block on a person (ADR-0043) ------------------------------------------


async def test_an_anchor_s_halt_is_booked_to_wait_human_and_read_as_the_decider_s_alone() -> None:
    w = await World(call("write", WRITE), rule("after", after=("write",))).setup()
    run = await w.start()
    held = run.step_run("write").block
    assert held is not None and (held.account, held.cause) == ("wait.human", "awaiting_decision")
    assert held.role == "finance.lead", "addressed to the role, never to a person"
    behind = run.step_run("after").block
    assert behind is not None and behind.account == "wait.dependency" and behind.on == "write"

    w.clock.current += timedelta(hours=2)
    (request_id,) = requests_of(run, "write")
    await w.answer(request_id, option="A")
    run = await w.confirm(request_id)
    assert run.state is RunState.FINISHED
    assert all(s.block is None for s in run.step_runs)

    accounts = BlockedTime(w.ledger, w.engine._objects, w.persistence)
    blocks = {b.account: b for b in await accounts.blocks(TENANT)}
    assert set(blocks) == {"wait.human", "wait.dependency"}
    decided = blocks["wait.human"]
    assert (decided.step_id, decided.cause, decided.role) == (
        "write",
        "awaiting_decision",
        "finance.lead",
    )
    assert decided.seconds >= timedelta(hours=2).total_seconds()
    text = json.dumps(
        [b.document() for b in blocks.values()]
        + [s.document() for s in await accounts.sums(TENANT)],
        default=str,
    )
    assert DECIDER not in text and COLLEAGUE not in text
    assert await accounts.own(TENANT, COLLEAGUE) == ()
    assert await accounts.own(TENANT, STARTER) == ()
    (own,) = await accounts.own(TENANT, DECIDER)
    assert own == decided
