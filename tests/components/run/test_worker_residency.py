"""A worker step goes only to a worker the tenant's residency rule admits (ADR-0157, #411).

Every worker declares where it stores what it is sent, or declares nothing and counts as
`elsewhere`. The pool passes over a worker outside the location the step permits — the tenant's
rule for the step's data class, or its own — for the next one. When only workers outside it
offer the capabilities, the step fails before anything is assigned, and its reason names the
rule and the worker passed over (UC-11.1 §2, principle 11).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fakes import FakeClock, FakeIdentifiers, FakeMaturities, FakeWorker

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
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.ports.model import Permitted
from taktus.ports.worker import ComputeLimit, Limits
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

AT = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
TENANT = "t"
PERSON = "idn_operator"
CHANGE = "change.implement"


class Rule:
    """A tenant's residency rule: its own location, narrowed per data class."""

    def __init__(self, own: Permitted = "anywhere", **classes: Permitted) -> None:
        self.own = own
        self.classes = classes

    async def permitted(self, tenant: str, data_class: str | None) -> Permitted:
        if data_class is not None and data_class in self.classes:
            return self.classes[data_class]
        return self.own


def worker(location: str | None) -> FakeWorker:
    return FakeWorker(capabilities_offered=(CHANGE,), data_location=location)


async def run_once(
    workers: list[tuple[str, FakeWorker]], rule: Rule | None, data_class: str | None = None
) -> Run:
    clock = FakeClock(AT)
    persistence = MemoryPersistence()
    engine = RunEngine(
        runs=MemoryRepository(persistence, Run),
        work=persistence,
        objects=MemoryObjectStore(),
        ledger=ChainedLedger(MemoryLedgerStore(persistence), clock),
        provenance=MemoryProvenanceStore(persistence),
        workers=StaticWorkerPool(list(workers)),
        clock=clock,
        ids=FakeIdentifiers(),
        telemetry=NoTelemetry(),
        maturities=FakeMaturities(),
        residency=rule,
    )
    step = Step(
        id="implement",
        method=Method.WORKER,
        reason="a change is implemented as a whole by a worker",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        fallback=Fallback(when="no worker may be handed the change", to=Method.HUMAN),
        requires=(CHANGE,),
    )
    work: dict[str, Any] = {
        "task": {"goal": "implement the change", "acceptance": ["the change is there"]}
    }
    if data_class is not None:
        work["data_class"] = data_class
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
    return await engine.start(
        StartRun(
            plan=plan,
            work={step.id: work},
            budget=Limits(compute=ComputeLimit(seconds=10, resource_class="cpu.small")),
            process_version="factory@1",
            actor=PERSON,
            tenant=TENANT,
        )
    )


async def test_a_worker_outside_the_rule_is_passed_over_for_the_next() -> None:
    abroad, inside = worker("elsewhere"), worker("eu")
    run = await run_once([("worker.abroad", abroad), ("worker.inside", inside)], Rule("eu"))
    assert run.state is RunState.FINISHED, run.reason
    assert abroad.assignments == [] and len(inside.assignments) == 1


async def test_a_worker_that_declares_nothing_counts_as_elsewhere() -> None:
    silent, own = worker(None), worker("own")
    run = await run_once([("worker.silent", silent), ("worker.own", own)], Rule("eu"))
    assert run.state is RunState.FINISHED, run.reason
    assert silent.assignments == [] and len(own.assignments) == 1


async def test_only_workers_outside_the_rule_fail_the_step_naming_the_rule() -> None:
    """A tenant with an EU residency cannot be handed to a worker that stores elsewhere: the
    step fails before anything is assigned, and the reason says why."""
    abroad = worker("elsewhere")
    run = await run_once([("worker.abroad", abroad)], Rule("eu"))
    assert abroad.assignments == [] and abroad.estimates == []
    step_run = run.step_run("implement")
    assert step_run.state is StepState.FAILED
    reason = step_run.reason or ""
    assert "residency rule admits (eu)" in reason and "worker.abroad" in reason
    assert "stores elsewhere" in reason


async def test_the_step_s_data_class_narrows_the_rule() -> None:
    inside, own = worker("eu"), worker("own")
    rule = Rule("eu", personal="own")
    run = await run_once([("worker.inside", inside), ("worker.own", own)], rule, "personal")
    assert run.state is RunState.FINISHED, run.reason
    assert inside.assignments == [] and len(own.assignments) == 1
    run = await run_once([("worker.inside", inside), ("worker.own", own)], rule)
    assert len(inside.assignments) == 1


async def test_a_tenant_without_a_rule_takes_the_first_worker_as_before() -> None:
    abroad, inside = worker("elsewhere"), worker("eu")
    run = await run_once([("worker.abroad", abroad), ("worker.inside", inside)], None)
    assert run.state is RunState.FINISHED, run.reason
    assert len(abroad.assignments) == 1 and inside.assignments == []
