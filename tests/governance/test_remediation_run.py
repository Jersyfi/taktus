"""A remediation plan executed by the run engine (#92, ADR-0179 §3, UC-4.12): the corrected step
is carried in with the value a person gave, everything built on it runs again inside the system,
and every step that acts outward halts first with a decision request of class `correction`, at
every level (ADR-0022 §3)."""

from __future__ import annotations

from typing import Any

import pytest
from fakes import FakeIdentifiers
from fakes.connector import BLIND, READ

from governance.test_anchors import (
    AT,
    BUDGET,
    CORRECTION,
    LEGAL_WRITE,
    STARTER,
    TENANT,
    World,
    anchor,
    call,
    rule,
)
from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.command.application.service import CommissionPlanHandler
from taktus.components.governance.domain.model.incident import Incident, IncidentKind
from taktus.components.run.application.service import CorrectResult, CorrectResultHandler, StartRun
from taktus.components.run.domain.model import Remedy, Run, RunError, RunState, StepState
from taktus.composition.defects import Remedies, RemedyRefused
from taktus.shared.v1 import (
    Command,
    Commissioned,
    ExactnessClass,
    InputKind,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    Step,
)


def derive(id: str, on: str) -> tuple[Step, dict[str, Any]]:
    step = Step(
        id=id,
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.SOURCED,
        depends_on=(on,),
    )
    return step, {"rule": "connector", "operation": READ, "input": {"id": {"$from": on}}}


async def remedied(w: World, wrong: Run, *, corrected: Any, step: str = "book") -> Run:
    """A remediation run of `wrong`: the step `step` carried with the corrected value, every
    step it is not built on carried as the wrong run left it."""
    digest = await w.engine._objects.put(str(corrected).encode())
    built_on = {step} | {s.id for s in w.steps if step in (s.depends_on or ())}
    carried = []
    for step_run in wrong.step_runs:
        if step_run.step_id == step:
            assert step_run.checkpoint is not None
            checkpoint = step_run.checkpoint.model_copy(update={"result_digest": digest})
            carried.append(step_run.model_copy(update={"checkpoint": checkpoint}))
        elif step_run.step_id not in built_on:
            carried.append(step_run)
    plan = Plan(
        id="pln_remedy",
        command_id="cmd_remedy",
        goal="remedy",
        autonomy_level=4,
        steps=w.steps,
        results_in=PlanResult.RUN,
        status=PlanStatus.COMMISSIONED,
        commissioned=Commissioned(by=STARTER, at=AT),
    )
    return await w.engine.start(
        StartRun(
            plan=plan,
            work=w.work,
            budget=BUDGET,
            process_version="p@1",
            actor=STARTER,
            tenant=TENANT,
            remedy=Remedy(incident_id="inc_1", run_id=wrong.id, step_id=step),
            carried=tuple(carried),
        )
    )


async def test_a_plan_inside_the_system_runs_again_without_a_halt_and_names_the_correction() -> (
    None
):
    w = await World(rule("book"), derive("post", "book"), level=4).setup()
    wrong = await w.start()
    assert wrong.state is RunState.FINISHED
    again = await remedied(w, wrong, corrected=2)
    assert again.state is RunState.FINISHED
    assert again.remedy is not None and again.remedy.run_id == wrong.id
    async with w.persistence.transaction(TENANT):
        records = await w.engine._provenance.of_run(TENANT, again.id)
        old = await w.engine._provenance.of_run(TENANT, wrong.id)
    (post,) = [r for r in records if r.step_id == "post"]
    (wrong_post,) = [r for r in old if r.step_id == "post"]
    assert post.result_digest is not None and post.result_digest != wrong_post.result_digest
    (read,) = [i for i in post.inputs if i.kind is InputKind.RESULT]
    book = again.step_run("book")
    assert book.checkpoint is not None and read.digest == book.checkpoint.result_digest
    assert w.connector.calls[-1][2] == {"id": 2}, "built on the corrected value"
    assert not [r for r in records if r.step_id == "book"], "the carried step was not produced"
    assert {r.step_id for r in old} == {"book", "post"}, "the wrong run's records stay"


async def test_an_outward_correction_halts_with_a_request_of_class_correction_at_level_4() -> None:
    w = await World(rule("book"), call("send", BLIND, after=("book",)), level=4).setup()
    wrong = await w.start()
    assert wrong.state is RunState.FINISHED and w.connector.acted == 1
    again = await remedied(w, wrong, corrected=2)
    assert again.state is RunState.WAITING_HUMAN
    assert w.connector.acted == 1, "nothing outward was corrected without a person"
    send = again.step_run("send")
    assert send.state is StepState.WAITING_HUMAN and send.anchoring is not None
    (request_id,) = send.anchoring.requests
    request = await w.request(request_id)
    assert request.request.class_ == "correction"
    await w.answer(request_id, option="A")
    done = await w.confirm(request_id)
    assert done.state is RunState.FINISHED and w.connector.acted == 2


async def test_without_a_correction_anchor_that_names_the_act_the_outward_step_is_not_made() -> (
    None
):
    narrow = anchor("anc-correction", "correction", actions=["correction.invoice"])
    w = await World(
        rule("book"),
        call("send", BLIND, after=("book",)),
        level=4,
        configuration={"anchors": [LEGAL_WRITE, narrow]},
    ).setup()
    wrong = await w.start()
    again = await remedied(w, wrong, corrected=2)
    assert again.step_run("send").state is StepState.FAILED
    assert "correction" in (again.step_run("send").reason or "")
    assert w.connector.acted == 1


async def test_a_carried_step_must_be_done_and_of_the_plan() -> None:
    w = await World(rule("book"), derive("post", "book")).setup()
    wrong = await w.start()
    unknown = wrong.step_run("book").model_copy(update={"step_id": "nope"})
    plan = Plan(
        id="pln_x",
        command_id="cmd_x",
        goal="g",
        autonomy_level=3,
        steps=w.steps,
        results_in=PlanResult.RUN,
        status=PlanStatus.COMMISSIONED,
        commissioned=Commissioned(by=STARTER, at=AT),
    )
    with pytest.raises(RunError, match="does not have"):
        await w.engine.start(
            StartRun(
                plan=plan,
                work=w.work,
                budget=BUDGET,
                process_version="p@1",
                actor=STARTER,
                tenant=TENANT,
                carried=(unknown,),
            )
        )
    assert CORRECTION["class"] == "correction"


# --- the plan started from the incident, by the composition (ADR-0179 §3) ------------------------


async def test_a_result_defect_starts_its_remediation_run_once_from_the_correction() -> None:
    w = await World(rule("book"), derive("post", "book"), level=4).setup()
    wrong = await w.start()
    objects = w.engine._objects
    corrected = await CorrectResultHandler(w.runs, w.persistence, objects, w.ledger).execute(
        CorrectResult(tenant=TENANT, run_id=wrong.id, step_id="book", value=2, actor=STARTER)
    )
    incidents = MemoryRepository(w.persistence, Incident)
    incident = Incident(
        id="inc_1",
        tenant=TENANT,
        kind=IncidentKind.RESULT_DEFECT,
        process_id="p",
        process_version="p@1",
        run_id=wrong.id,
        rule="exact-or-sourced",
        facts={"step": "book", "found": "corrected", "verdict": "escalate"},
        raised_at=AT,
    )
    async with w.persistence.transaction(TENANT):
        await incidents.put(TENANT, incident)
    remedies = Remedies(
        w.engine,
        w.runs,
        incidents,
        CommissionPlanHandler(
            MemoryRepository(w.persistence, Command),
            MemoryRepository(w.persistence, Plan),
            w.persistence,
            w.clock,
            FakeIdentifiers(),
        ),
        w.ledger,
        w.persistence,
        w.clock,
        FakeIdentifiers(),
    )
    run = await remedies.start(TENANT, "inc_1")
    assert run.remedy == Remedy(incident_id="inc_1", run_id=wrong.id, step_id="book")
    book = run.step_run("book")
    assert book.done and book.checkpoint is not None and book.checkpoint.result_digest == corrected
    assert not run.step_run("post").done, "what is built on it runs again"
    again = await remedies.start(TENANT, "inc_1")
    assert again.id == run.id
    async with w.persistence.transaction(TENANT):
        started = [e for e in await w.ledger.of_kinds(TENANT, ("remediation.started",))]
    assert len(started) == 1 and started[0].refs.incident_id == "inc_1"
    assert started[0].refs.run_id == run.id


async def test_a_sample_judged_wrong_waits_for_a_correction_before_its_remediation() -> None:
    w = await World(rule("book"), derive("post", "book")).setup()
    wrong = await w.start()
    incidents = MemoryRepository(w.persistence, Incident)
    async with w.persistence.transaction(TENANT):
        await incidents.put(
            TENANT,
            Incident(
                id="inc_2",
                tenant=TENANT,
                kind=IncidentKind.RESULT_DEFECT,
                process_id="p",
                process_version="p@1",
                run_id=wrong.id,
                rule="none",
                facts={"step": "book", "found": "sampled", "verdict": "continue"},
                raised_at=AT,
            ),
        )
    remedies = Remedies(
        w.engine,
        w.runs,
        incidents,
        CommissionPlanHandler(
            MemoryRepository(w.persistence, Command),
            MemoryRepository(w.persistence, Plan),
            w.persistence,
            w.clock,
            FakeIdentifiers(),
        ),
        w.ledger,
        w.persistence,
        w.clock,
        FakeIdentifiers(),
    )
    with pytest.raises(RemedyRefused, match="records it first"):
        await remedies.start(TENANT, "inc_2")
