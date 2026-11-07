"""A stop of a process, of the tenant and of the instance, by a person or by a rule (ADR-0256,
UC-7.2).

Runs of two processes, `p` and `q`, on fake workers. A stop of `p` halts every run of `p` at its
next boundary — a run inside a worker step at the worker's boundary, a run between steps before
its next step is handed on — and leaves `q` alone. A stop of the tenant halts both. A stop of
the instance is a stop of each tenant it serves. None asks a person for a reason, at any level.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from taktus.components.run.application.service import StartRun
from taktus.components.run.domain.model import (
    AdapterStop,
    Cause,
    Run,
    RunState,
    StepState,
    StopScope,
    StopState,
)
from taktus.composition.stops import RuleStops
from taktus.ports.worker import Event
from taktus.shared.v1 import (
    Commissioned,
    ExactnessClass,
    Fallback,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    Step,
)

from .test_adapter_stop import AT, BUDGET, OPERATOR, TENANT, Harness


def plan(level: int = 3, steps: int = 1) -> tuple[Plan, dict[str, Any]]:
    made = tuple(
        Step(
            id=f"do{n}",
            method=Method.WORKER,
            reason="r",
            rejected=(),
            exactness=ExactnessClass.TOLERANT,
            fallback=Fallback(when="x", to=Method.HUMAN),
            requires=("shell.script",),
            depends_on=(f"do{n - 1}",) if n else None,
        )
        for n in range(steps)
    )
    work = {
        s.id: {"task": {"goal": "g", "acceptance": ["a"], "inputs": None}, "max_steps": 100}
        for s in made
    }
    return (
        Plan(
            id="pln_1",
            command_id="cmd_1",
            goal="g",
            autonomy_level=level,
            steps=made,
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by="idn_t", at=AT),
        ),
        work,
    )


async def start(h: Harness, process: str, *, level: int = 3, steps: int = 1) -> Run:
    planned, work = plan(level, steps)
    return await h.engine.start(
        StartRun(
            plan=planned,
            work=work,
            budget=BUDGET,
            process_version=f"{process}@1",
            actor="idn_t",
            tenant=TENANT,
        )
    )


def harness() -> Harness:
    """Both processes run on the same worker: a stop of a process is not one of an adapter."""
    return Harness()


async def test_a_stop_of_a_process_halts_its_run_at_the_worker_s_boundary_and_others_go_on() -> (
    None
):
    h = harness()
    asked: dict[str, bool] = {}

    async def on_event(event: Event) -> None:
        if event.type != "step.started" or event.seq != 1 or asked:
            return
        stop = await h.stops.request_process(TENANT, "p", OPERATOR)
        asked["run_0001"] = await h.engine.stops_held("run_0001")
        assert stop.scope is StopScope.PROCESS and stop.process == "p"

    h.stopped.on_event = on_event
    stopped = await start(h, "p", steps=2)
    other = await start(h, "q", steps=2)

    assert asked == {stopped.id: True}, "the runner reads the stop at its renewal"
    assert stopped.state is RunState.HALTED and stopped.cause is Cause.STOP
    first = stopped.step_run("do0")
    assert first.state is StepState.STOPPED and first.checkpoint is not None, "at its boundary"
    assert stopped.step_run("do1").state is StepState.PLANNED, "no further step handed on"
    assert other.state is RunState.FINISHED, "a run of another process goes on"

    [confirmed] = await h.stops.confirm(TENANT)
    assert confirmed.stopped == (stopped.id,) and confirmed.requested_by == OPERATOR
    entries = await h.entries()
    requested = next(e for e in entries if e.kind == "stop.requested")
    assert requested.outcome == "process" and requested.refs.actor == OPERATOR
    held = next(e for e in entries if e.kind == "stop.confirmed")
    assert held.outcome == "held" and held.refs.actor == OPERATOR, "addressed to the requester"


async def test_a_held_stop_of_a_process_hands_no_step_on_until_a_person_lifts_it() -> None:
    h = harness()
    stop = await h.stops.request_process(TENANT, "p", OPERATOR)
    assert await h.stops.request_process(TENANT, "p", "idn_other") == stop, "one stop per process"
    halted = await start(h, "p")
    assert halted.state is RunState.HALTED and halted.cause is Cause.STOP
    assert stop.id in (halted.reason or "")
    assert not h.stopped.assignments, "nothing was handed on"
    shown = await h.stops.show(TENANT, stop.id)
    assert shown.stop.state is StopState.CONFIRMED and shown.stop.stopped == (halted.id,)
    assert (await h.resume(halted)).state is RunState.HALTED, "held after confirming"
    await h.stops.lift(TENANT, stop.id, OPERATOR)
    assert (await h.resume(halted)).state is RunState.FINISHED, "a person resumes it"


@pytest.mark.parametrize("level", [1, 2, 3, 4])
async def test_a_person_stops_the_tenant_at_every_level_without_a_reason(level: int) -> None:
    h = harness()
    stop = await h.stops.request_tenant(TENANT, OPERATOR)
    first, second = await start(h, "p", level=level), await start(h, "q", level=level)
    for run in (first, second):
        assert run.state is RunState.HALTED and run.cause is Cause.STOP
    [confirmed] = await h.stops.confirm(TENANT)
    assert confirmed.id == stop.id and confirmed.scope is StopScope.TENANT
    assert confirmed.stopped == tuple(sorted((first.id, second.id)))


async def test_a_stop_of_the_instance_is_a_stop_of_each_tenant_it_serves() -> None:
    h = harness()
    stops = await h.stops.request_everywhere(["t", "u", "t"], OPERATOR)
    assert [(s.tenant, s.scope) for s in stops] == [
        ("t", StopScope.TENANT),
        ("u", StopScope.TENANT),
    ]
    assert (await start(h, "p")).state is RunState.HALTED
    assert [s.id for s in await h.stops.confirm("u")] == [stops[1].id], "confirmed per tenant"


async def test_a_rule_s_stop_names_the_rule_and_the_incident_and_no_person() -> None:
    h = harness()
    stop_id = await RuleStops(h.stops).stop_process(
        TENANT, "p", rule="exact-left-under-a-legal-anchor", incident="inc_1"
    )
    halted = await start(h, "p")
    assert halted.state is RunState.HALTED and "the rule exact-left" in (halted.reason or "")
    [confirmed] = await h.stops.confirm(TENANT)
    assert confirmed.id == stop_id and confirmed.rule == "exact-left-under-a-legal-anchor"
    assert confirmed.incident == "inc_1"
    entries = await h.entries()
    requested = next(e for e in entries if e.kind == "stop.requested")
    assert requested.refs.actor is None and requested.refs.incident_id == "inc_1"
    assert requested.content_digest is not None
    content = await h.objects.get(requested.content_digest)
    assert content is not None
    assert json.loads(content)["rule"] == "exact-left-under-a-legal-anchor"


def test_a_stop_names_what_its_scope_needs_and_nothing_else() -> None:
    base: dict[str, Any] = {
        "id": "stp_1",
        "tenant": TENANT,
        "requested_by": OPERATOR,
        "requested_at": AT,
        "created_at": AT,
    }
    with pytest.raises(ValueError, match="names a process"):
        AdapterStop(**base, scope=StopScope.PROCESS)
    with pytest.raises(ValueError, match="names an adapter"):
        AdapterStop(**base, scope=StopScope.TENANT, adapter="worker.coding")
    with pytest.raises(ValueError, match="rule"):
        AdapterStop(**base, scope=StopScope.TENANT, rule="r")
    adapter = AdapterStop(**base, adapter="worker.coding")
    assert "scope" not in adapter.document(), "written as the release before wrote it"


async def test_a_person_s_stop_and_a_rule_s_are_never_one() -> None:
    h = Harness()
    with pytest.raises(ValueError, match="never both"):
        await h.stops.request_process(TENANT, "p", OPERATOR, rule="r", incident="inc_1")
    await asyncio.sleep(0)
