"""Corrections are counted per process and action class, and a level falls by rule (UC-7.5 §2,
ADR-0110).

Each case runs a plan through the run engine over fakes of every port, with the governance,
decision and identity components wired as the composition root wires them
(`composition/decisions.py`), and reads back the run, the ledger, the object store and the
incidents. Registration is the product's own handler with the same wiring.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeConnector, FakeIdentifiers, FakeMaturities, FakeWorker
from fakes.clock import FakeClock
from fakes.connector import READ, WRITE
from fakes.identity import directory

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryObjectStore,
    MemoryProvenanceStore,
    MemoryQueue,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.governance.application.service import (
    ConfigureAnchors,
    ConfigureCorrections,
)
from taktus.components.governance.domain.model import IncidentKind, Unit
from taktus.components.governance.domain.service import corrections as rule
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import Process, ProcessVersion, RaiseRefused
from taktus.components.run.application.service import (
    ConfirmSteps,
    EngineOptions,
    ResumeRun,
    RunEngine,
    StartRun,
)
from taktus.components.run.domain.model import Cause, Run, RunState, StepState
from taktus.composition.decisions import decision_wiring
from taktus.ports.connector import CallContext, Result
from taktus.ports.ledger import Fact
from taktus.ports.worker import ComputeLimit, Limits, QuotaLimit
from taktus.shared.v1 import (
    AutonomyLevel,
    Commissioned,
    ExactnessClass,
    LedgerEntry,
    LedgerRefs,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    Step,
)

AT = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
BUDGET = Limits(
    compute=ComputeLimit(seconds=10, resource_class="cpu.small"), quota=QuotaLimit(units=40)
)
TENANT = "t"
PERSON = "idn_ada"
WORKER = "worker.fake"
CONNECTOR = "connector.fake"
VERSION = "p@1"


def anchor(id: str, kind: str, **applies_to: Any) -> dict[str, Any]:
    return {
        "id": id,
        "class": kind,
        "act": f"the act of {id}",
        "applies_to": applies_to,
        "decider": {"role": "owner"},
    }


ELSEWHERE = {
    "anchors": [
        anchor("anc-payment", "legal", actions=["payment.*"]),
        anchor("anc-correction", "correction", actions=["correction.*"]),
    ]
}
"""Anchors that name nothing the processes here do."""
ON_WRITE = {
    "anchors": [
        anchor("anc-write", "legal", actions=[WRITE]),
        anchor("anc-correction", "correction", actions=["correction.*"]),
    ]
}
"""An anchor on the write every process here performs."""


def rule_step(id: str, *, after: tuple[str, ...] = (), value: Any = 1) -> tuple[Step, Any]:
    step = Step(
        id=id,
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.EXACT,
        depends_on=after or None,
    )
    return step, {"rule": "constant", "value": value}


def call(id: str, operation: str, *, after: tuple[str, ...] = ()) -> tuple[Step, Any]:
    step = Step(
        id=id,
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.SOURCED,
        depends_on=after or None,
    )
    return step, {"rule": "connector", "operation": operation, "input": {"id": "x"}}


class AnchoringConnector(FakeConnector):
    """A connector during whose write the tenant's anchors change: the anchor came into force
    while the step acted, after its boundary had asked."""

    def __init__(self) -> None:
        super().__init__()
        self.on_write: Any = None

    async def call(self, operation: str, context: CallContext, input: Mapping[str, Any]) -> Result:
        result = await super().call(operation, context, input)
        if operation == WRITE and self.on_write is not None:
            act, self.on_write = self.on_write, None
            await act()
        return result


class World:
    def __init__(
        self,
        *definitions: tuple[Step, Any],
        level: AutonomyLevel = 2,
        actions: Mapping[str, AutonomyLevel] | None = None,
    ) -> None:
        self.clock = FakeClock(AT)
        self.people = directory((TENANT,), clock=self.clock)
        self.persistence = self.people.persistence
        self.ledger = self.people.ledger
        self.objects = MemoryObjectStore()
        self.runs = MemoryRepository(self.persistence, Run)
        self.connector = AnchoringConnector()
        self.connector.reads["x"] = {"id": "x"}
        self.decisions = decision_wiring(
            lambda kind: MemoryRepository(self.persistence, kind),
            self.persistence,
            self.ledger,
            self.clock,
            self.people.directory,
        )
        self.corrections = self.decisions.corrections
        self.engine = RunEngine(
            runs=self.runs,
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=MemoryProvenanceStore(self.persistence),
            workers=StaticWorkerPool([(WORKER, FakeWorker())]),
            connectors=StaticConnectorPool([(CONNECTOR, self.connector)]),
            clock=self.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            options=EngineOptions(uncalibrated_margin=0.0),
            maturities=FakeMaturities(),
            queue=MemoryQueue(self.persistence, self.clock, lease_seconds=60),
            anchors=self.decisions.anchors,
            decisions=self.decisions.requests,
            levels=self.decisions.levels,
        )
        self.register = RegisterProcessVersionHandler(
            MemoryRepository(self.persistence, ProcessVersion),
            self.persistence,
            MemoryRepository(self.persistence, Process),
            ledger=self.ledger,
            clock=self.clock,
            lowered=self.decisions.lowered,
        )
        self.level = level
        self.actions = dict(actions or {})
        self.steps = tuple(step for step, _ in definitions)
        self.work = {step.id: work for step, work in definitions}

    async def setup(self, anchors: Mapping[str, Any] = ELSEWHERE) -> World:
        await self.people.directory.add(TENANT, PERSON, (TENANT,), roles=("owner",))
        await self.anchors(anchors)
        return self

    async def anchors(self, document: Mapping[str, Any]) -> None:
        await self.decisions.configure.execute(
            ConfigureAnchors(tenant=TENANT, document=document, actor=PERSON)
        )

    async def limits(self, **given: Any) -> None:
        await self.corrections.configure(ConfigureCorrections(tenant=TENANT, **given), by=PERSON)

    async def start(self) -> Run:
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
                process_version=VERSION,
                actor=PERSON,
                tenant=TENANT,
                actions=self.actions,
            )
        )

    async def answer(self, run: Run, *steps: str, **given: Any) -> Run:
        return await self.engine.confirm(
            ConfirmSteps(run_id=run.id, steps=steps, actor=PERSON, tenant=TENANT, **given)
        )

    async def chain(self) -> list[LedgerEntry]:
        async with self.persistence.transaction(TENANT):
            return list(await self.ledger.entries(TENANT))

    async def of(self, kind: str) -> list[LedgerEntry]:
        return [e for e in await self.chain() if e.kind == kind]

    async def kinds(self, run: Run) -> list[str]:
        async with self.persistence.transaction(TENANT):
            entries = await self.ledger.entries(TENANT, run.id)
        return [f"{e.kind}:{e.refs.step_id or ''}:{e.outcome or ''}".rstrip(":") for e in entries]

    async def document(self, digest: str | None) -> dict[str, Any]:
        assert digest is not None
        stored = await self.objects.get(digest)
        assert stored is not None
        return dict(json.loads(stored))


def first(kinds: list[str], prefix: str) -> int:
    return next(i for i, k in enumerate(kinds) if k.startswith(prefix))


# --- every decision on a proposal is recorded -----------------------------------------------------


async def test_every_decision_records_its_outcome_process_step_action_and_time() -> None:
    w = await World(
        rule_step("a"),
        call("b", WRITE, after=("a",)),
        rule_step("c", after=("b",)),
        level=3,
        actions={WRITE: 2},
    ).setup()
    run = await w.start()
    assert run.step_run("b").state is StepState.WAITING_HUMAN
    run = await w.answer(run, "b")
    assert run.state is RunState.FINISHED

    (decided,) = await w.of("proposal.decided")
    assert decided.outcome == "released"
    assert decided.refs.process_version == VERSION and decided.refs.step_id == "b"
    assert decided.refs.action == WRITE, "the action class whose level held the step"
    assert decided.ts > AT, "and when"
    assert decided.refs.actor is None, "the record that is counted names no person"
    record = await w.document(decided.content_digest)
    assert record["outcome"] == "released" and record["released"] is None
    (awaiting,) = await w.of("step.awaiting")
    assert record["proposal"] == awaiting.content_digest, "the proposal it decided"
    (confirmed,) = await w.of("step.confirmed")
    assert confirmed.refs.actor == PERSON, "the answer's own entry names who answered"


async def test_a_corrected_decision_keeps_the_proposal_and_the_version_released() -> None:
    w = await World(rule_step("a", value=1), rule_step("b", after=("a",))).setup()
    run = await w.start()
    run = await w.answer(run, "a", corrected={"a": {"rule": "constant", "value": 2}})
    (decided,) = await w.of("proposal.decided")
    assert decided.outcome == "corrected" and decided.refs.action is None
    record = await w.document(decided.content_digest)
    proposal = await w.document(record["proposal"])
    released = await w.document(record["released"])
    assert proposal["work"] == {"rule": "constant", "value": 1}
    assert released["work"] == {"rule": "constant", "value": 2}, "the change can be seen"
    assert {k: v for k, v in proposal.items() if k != "work"} == {
        k: v for k, v in released.items() if k != "work"
    }
    assert run.work["a"] == {"rule": "constant", "value": 2}, "at level 2 it runs as released"
    assert run.step_run("a").state is StepState.SUCCEEDED


async def test_a_rejected_proposal_runs_nothing_halts_the_run_and_is_proposed_again() -> None:
    w = await World(call("a", WRITE)).setup()
    run = await w.start()
    run = await w.answer(run, "a", rejected=True)
    assert run.state is RunState.HALTED and run.cause is Cause.DECLINED
    assert run.step_run("a").state is StepState.PLANNED
    assert w.connector.acted == 0, "nothing of it ran"
    (decided,) = await w.of("proposal.decided")
    assert decided.outcome == "rejected"
    assert (await w.document(decided.content_digest))["released"] is None
    (declined,) = await w.of("step.declined")
    assert declined.refs.actor == PERSON

    run = await w.engine.resume(ResumeRun(run_id=run.id, actor=PERSON, tenant=TENANT))
    assert run.step_run("a").state is StepState.WAITING_HUMAN, "proposed again, not run"
    assert w.connector.acted == 0


# --- the rate is a rule over the records ----------------------------------------------------------


async def test_the_rate_per_process_and_action_over_7_and_28_days_is_reproducible() -> None:
    w = await World(rule_step("a"), rule_step("b", after=("a",)), level=2).setup()
    await w.limits(lower_minimum=10, raise_decisions=50)
    for outcome in ("released", "corrected", "released", "rejected"):
        run = await w.start()
        if outcome == "corrected":
            run = await w.answer(run, "a", corrected={"a": {"rule": "constant", "value": 3}})
        elif outcome == "rejected":
            run = await w.answer(run, "a", rejected=True)
            continue
        else:
            run = await w.answer(run, "a")
        run = await w.answer(run, "b")
        w.clock.current += timedelta(days=5)

    (figures,) = await w.corrections.figures(TENANT)
    assert figures.unit == Unit(process_id="p")
    assert (figures.month.decided, figures.month.corrected, figures.month.rejected) == (7, 1, 1)
    assert figures.month.rate == pytest.approx(2 / 7)
    # Five days apart: the last 7 days hold the third run and the fourth.
    assert figures.week.decided == 3 and figures.week.rate == pytest.approx(1 / 3)

    # Reproducible from the ledger alone: the rule over the whole chain gives the same figures.
    again = rule.figures(await w.chain(), Unit(process_id="p"), figures.at)
    assert again == figures


# --- a raise is proposed with its figures, never applied ------------------------------------------


async def test_when_the_tenants_conditions_hold_a_raise_is_proposed_and_never_applied() -> None:
    w = await World(rule_step("a"), level=2).setup()
    await w.limits(raise_decisions=3, raise_weeks=1, raise_rate=0.2, lower_rate=0.5)
    run = await w.start()
    await w.answer(run, "a")
    w.clock.current += timedelta(days=8)
    for _ in range(2):
        run = await w.start()
        assert run.autonomy_level == 2
        await w.answer(run, "a")
    (proposed,) = await w.of("autonomy.proposed")
    assert proposed.outcome == "corrections" and proposed.refs.actor is None
    assert proposed.refs.process_version == VERSION and proposed.refs.action is None
    (one,) = await w.corrections.proposed(TENANT)
    assert one.figures.month.decided == 3 and one.figures.month.rate == 0.0
    assert one.figures.week.decided == 2

    run = await w.start()
    assert run.autonomy_level == 2, "the raise is proposed, never applied"
    await w.answer(run, "a")
    assert len(await w.of("autonomy.proposed")) == 1, "proposed once per change of level"
    assert await w.of("autonomy.raised") == []


# --- a breach lowers the process before its next step ---------------------------------------------


async def test_a_level_3_process_that_breaches_an_anchor_is_at_level_2_before_its_next_step() -> (
    None
):
    w = await World(call("write", WRITE), rule_step("after", after=("write",)), level=3).setup()

    async def configured_meanwhile() -> None:
        await w.anchors(ON_WRITE)

    w.connector.on_write = configured_meanwhile
    run = await w.start()

    assert w.connector.acted == 1, "the act was performed: its boundary named no anchor"
    assert run.autonomy_level == 2
    assert run.step_run("after").state is StepState.WAITING_HUMAN, "level 2 asks first"
    kinds = await w.kinds(run)
    lowered = first(kinds, "run.lowered")
    assert kinds[lowered] == "run.lowered::level_2"
    assert first(kinds, "step.finished:write") < lowered < first(kinds, "step.awaiting:after")
    assert "step.started:after" not in kinds

    (incident,) = await w.corrections.lowerings(TENANT)
    assert incident.kind is IncidentKind.BREACH and incident.rule == "anchor.breach"
    assert incident.process_version == VERSION and incident.run_id == run.id
    assert incident.facts["anchors"] == "anc-write"
    assert (incident.facts["level_before"], incident.facts["level_after"]) == ("3", "2")
    (entry,) = await w.of("autonomy.lowered")
    assert entry.outcome == "level_2" and entry.refs.incident_id == incident.id
    assert entry.refs.actor is None, "lowered without a person: it is never held for approval"
    assert [e.outcome for e in await w.of("incident.raised")] == ["lowered"]

    run = await w.start()
    assert run.step_run("write").state is StepState.WAITING_HUMAN, "the next run too"


# --- a rate above the tenant's limit lowers the unit ----------------------------------------------


async def test_a_correction_rate_above_the_limit_lowers_the_process_one_level() -> None:
    w = await World(
        rule_step("a"), rule_step("b", after=("a",)), call("c", WRITE, after=("b",)), level=2
    ).setup()
    await w.limits(lower_rate=0.25, lower_minimum=2)
    run = await w.start()
    run = await w.answer(run, "a", corrected={"a": {"rule": "constant", "value": 5}})
    assert run.autonomy_level == 2 and await w.of("autonomy.lowered") == []
    run = await w.answer(run, "b", rejected=True)
    run = await w.engine.resume(ResumeRun(run_id=run.id, actor=PERSON, tenant=TENANT))

    assert run.autonomy_level == 1
    assert run.step_run("b").state is StepState.SUCCEEDED, "level 1: a rule is analysis, and runs"
    awaiting = [e for e in await w.of("step.awaiting") if e.refs.step_id == "c"]
    assert [e.outcome for e in awaiting] == ["performance"], "level 1: the person acts"
    (incident,) = await w.corrections.lowerings(TENANT)
    assert incident.kind is IncidentKind.CORRECTIONS and incident.rule == "corrections.rate"
    assert incident.facts["rate"] == 1.0 and incident.facts["decided"] == 2.0
    assert incident.facts["limit"] == 0.25
    assert (incident.facts["level_before"], incident.facts["level_after"]) == ("2", "1")


async def test_a_rate_above_the_limit_lowers_the_action_class_and_leaves_the_process() -> None:
    w = await World(
        call("w1", WRITE),
        call("w2", WRITE, after=("w1",)),
        call("r", READ, after=("w2",)),
        level=3,
        actions={WRITE: 2},
    ).setup()
    await w.limits(lower_rate=0.25, lower_minimum=1)
    run = await w.start()
    run = await w.answer(
        run, "w1", corrected={"w1": {"rule": "connector", "operation": WRITE, "input": {"id": "y"}}}
    )

    assert run.autonomy_level == 3, "the process keeps its level"
    assert run.actions[WRITE] == 1, "the action class fell one level"
    (entry,) = await w.of("autonomy.lowered")
    assert entry.refs.action == WRITE and entry.outcome == "level_1"
    assert run.work["w1"]["input"] == {"id": "y"}, "the corrected work is what is proposed now"
    # The level fell before w1 started: at its boundary it is level 1, and the person acts.
    awaiting = [e.outcome for e in await w.of("step.awaiting") if e.refs.step_id == "w1"]
    assert awaiting == ["confirmation", "performance"]
    assert w.connector.acted == 0, "Taktus executes no act at level 1"

    run = await w.answer(run, "w1", performed=True)
    assert run.step_run("w2").state is StepState.WAITING_HUMAN
    awaiting = [e.outcome for e in await w.of("step.awaiting") if e.refs.step_id == "w2"]
    assert awaiting == ["performance"]


# --- a level that fell rises only through UC-7.1 --------------------------------------------------


def bundle(version: str, level: int) -> dict[str, Any]:
    return {
        "id": "p",
        "version": version,
        "name": "P",
        "autonomy": {"level": level, "reason": "r", "toward_next": "t", "history": 1},
        "steps": [
            {
                "id": "a",
                "method": "rule",
                "reason": "r",
                "rejected": [],
                "exactness": "tolerant",
                "work": {"rule": "constant", "value": 1},
            }
        ],
    }


async def test_a_level_lowered_by_rule_rises_again_only_with_approval_and_evidence() -> None:
    w = await World(call("write", WRITE), level=3).setup()
    await w.register.execute(RegisterProcessVersion(bundle("1", 3), tenant=TENANT, by=PERSON))
    async with w.persistence.transaction(TENANT):
        await w.ledger.record(
            TENANT,
            Fact(
                kind="run.finished",
                refs=LedgerRefs(tenant=TENANT, process_version=VERSION, run_id="run_clean"),
            ),
        )

    async def configured_meanwhile() -> None:
        await w.anchors(ON_WRITE)

    w.connector.on_write = configured_meanwhile
    await w.start()
    assert (await w.corrections.lowered(TENANT, VERSION)).level == 2

    with pytest.raises(RaiseRefused) as refused:
        await w.register.execute(RegisterProcessVersion(bundle("2", 3), tenant=TENANT, by=PERSON))
    assert "from level 2 to 3" in " ".join(refused.value.findings)
    (entry,) = await w.of("autonomy.refused")
    assert entry.outcome == "no_approval"

    at_two = await w.register.execute(
        RegisterProcessVersion(bundle("2", 2), tenant=TENANT, by=PERSON)
    )
    assert at_two.autonomy.level == 2, "a version at the lowered level needs nobody"
    again = await w.register.execute(
        RegisterProcessVersion(bundle("3", 3), tenant=TENANT, by=PERSON, approved_by=PERSON)
    )
    assert again.autonomy.level == 3
    (raised,) = await w.of("autonomy.raised")
    assert raised.refs.actor == PERSON, "with a person's approval and the history"


# --- the decision is a rule; no figure names a person ---------------------------------------------


def test_the_decision_to_lower_is_a_rule_and_no_model() -> None:
    root = Path(rule.__file__).resolve().parents[2]
    for path in (
        Path(rule.__file__),
        root / "application" / "service" / "corrections.py",
        root / "domain" / "model" / "corrections.py",
    ):
        source = path.read_text(encoding="utf-8")
        assert "ports.model" not in source and "ModelPool" not in source, path


async def test_no_figure_names_the_person_who_corrected() -> None:
    w = await World(rule_step("a"), level=2).setup()
    await w.limits(lower_minimum=10)
    for _ in range(3):
        run = await w.start()
        await w.answer(run, "a", corrected={"a": {"rule": "constant", "value": 9}})
    figures = await w.corrections.figures(TENANT)
    assert [f.unit for f in figures] == [Unit(process_id="p")], "per process, not per person"
    assert PERSON not in json.dumps([f.document() for f in figures], default=str)
    for entry in await w.of("proposal.decided"):
        assert entry.refs.actor is None
        assert PERSON not in json.dumps(await w.document(entry.content_digest))
