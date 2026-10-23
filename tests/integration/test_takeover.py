"""A person takes over a running step and hands it back, against PostgreSQL (ADR-0128, #404).

Two instances share one database, as two `taktusd` processes would: A runs the runner, B serves
the HTTP surface and has no runner. A person asks the take-over through B while A's worker is
inside the step. A stops the worker at its boundary and passes its claim to the take-over; no
runner claims the job while the person holds it, however short the runners' lease; the person
hands the result back through B under the take-over's claim; A continues the run to its end.
The step's block, with the take-over it holds, round-trips through the step run's row, and the
ledger and provenance chains verify.

The same path against the memory adapters, with the lapse and the fence, is in
`tests/components/run/test_takeover.py`.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fakes import FakeWorker, InnerStep
from fakes.identity import FixedTenants
from fakes.maturity import VERIFIED
from sqlalchemy import text

from taktus.adapters.driven.memory import MemoryObjectStore
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.run.application.service import (
    HandBack,
    RunEngine,
    Runner,
    RunnerOptions,
    StartRun,
    TakeOver,
)
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.components.run.domain.model.block import TAKEN_OVER
from taktus.components.run.domain.service import provenance
from taktus.ports.objectstore import ObjectStore
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

from .test_runner_fence import Instance

TENANT = f"takeover_{os.urandom(4).hex()}"


@pytest.fixture
async def instances(postgres_url: str) -> AsyncIterator[tuple[Instance, Instance]]:
    a, b = Instance.open(postgres_url), Instance.open(postgres_url)
    async with a.persistence.engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('taktus.tenant', :t, true)"), {"t": TENANT}
        )
        await connection.execute(
            text("INSERT INTO tenant (id, name, created_at) VALUES (:t, :t, now())"), {"t": TENANT}
        )
    try:
        yield a, b
    finally:
        await a.persistence.close()
        await b.persistence.close()


def engine(instance: Instance, objects: ObjectStore, worker: FakeWorker) -> RunEngine:
    return RunEngine(
        maturities=VERIFIED,
        runs=instance.runs,
        work=instance.persistence,
        objects=objects,
        ledger=instance.ledger,
        provenance=instance.provenance,
        workers=StaticWorkerPool([("worker.fake", worker)]),
        clock=instance.clock,
        ids=instance.ids,
        telemetry=NoTelemetry(),
        queue=instance.queue,
    )


def runner(instance: Instance, engine: RunEngine) -> Runner:
    return Runner(
        engine=engine,
        queue=instance.queue,
        work=instance.persistence,
        clock=instance.clock,
        options=RunnerOptions(
            tenants=FixedTenants((TENANT,)),
            claimant="a",
            concurrency=1,
            poll_seconds=0.05,
            heartbeat_seconds=0.1,
        ),
    )


def definitions() -> tuple[tuple[Step, dict[str, Any]], ...]:
    worker = Step(
        id="w",
        method=Method.WORKER,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        fallback=Fallback(when="x", to=Method.HUMAN),
        requires=("shell.script",),
    )
    after = Step(
        id="r",
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.EXACT,
        depends_on=("w",),
    )
    return (
        (worker, {"task": {"goal": "g", "acceptance": ["a"]}}),
        (after, {"rule": "constant", "value": 1}),
    )


async def stored(instance: Instance, run_id: str) -> Run:
    async with instance.persistence.transaction(TENANT):
        run = await instance.runs.get(TENANT, run_id)
    assert run is not None
    return run


async def until(condition: Any, seconds: float = 20.0) -> None:
    async with asyncio.timeout(seconds):
        while not await condition():  # noqa: ASYNC110 — the state polled is the database's
            await asyncio.sleep(0.05)


async def test_a_step_taken_over_through_one_instance_is_handed_back_and_finished_by_another(
    instances: tuple[Instance, Instance],
) -> None:
    a, b = instances
    objects = MemoryObjectStore()  # the instances' shared object store
    worker = FakeWorker(
        script=(InnerStep("one", artifacts=(("out-1", b"1\n"),)), InnerStep("two")),
        inner_seconds=0.3,
    )
    engine_a, engine_b = engine(a, objects, worker), engine(b, objects, worker)
    plan = Plan(
        id=f"pln_{os.urandom(4).hex()}",
        command_id="cmd_1",
        goal="g",
        autonomy_level=3,
        steps=tuple(step for step, _ in definitions()),
        results_in=PlanResult.RUN,
        status=PlanStatus.COMMISSIONED,
        commissioned=Commissioned(by="idn_t", at=a.clock.now()),
    )
    run = await engine_b.submit(
        StartRun(
            plan=plan,
            work={step.id: work for step, work in definitions()},
            budget=Limits(compute=ComputeLimit(seconds=10, resource_class="cpu.small")),
            process_version="p@1",
            actor="idn_t",
            tenant=TENANT,
        )
    )
    first = runner(a, engine_a)
    task = asyncio.create_task(first.run())
    try:

        async def running() -> bool:
            return (await stored(a, run.id)).step_run("w").state is StepState.RUNNING

        await until(running)
        takeover = await engine_b.take_over(
            TakeOver(run_id=run.id, step_id="w", actor="idn_person", tenant=TENANT)
        )

        async def served() -> bool:
            return bool(first.outcomes)

        await until(served)
        assert first.outcomes[0].disposition == "taken_over", first.outcomes[0].error
        held = await stored(b, run.id)
        block = held.step_run("w").block
        assert block is not None and block.cause == TAKEN_OVER
        assert block.takeover is not None and block.takeover.id == takeover, "round-trips"
        state = await engine_b.takeover_state(TENANT, run.id, takeover)
        assert state["step_id"] == "w" and state["artifacts"][0]["id"] == "out-1"

        await asyncio.sleep(1.5)  # beyond the runners' lease of one second
        assert len(first.outcomes) == 1, "no runner claimed the job the person holds"

        await engine_b.hand_back(
            HandBack(
                run_id=run.id,
                takeover=takeover,
                result={"done": True},
                actor="idn_person",
                tenant=TENANT,
            )
        )

        async def finished() -> bool:
            return (await stored(a, run.id)).state is RunState.FINISHED

        await until(finished)
    finally:
        await first.stop()
        await asyncio.wait_for(task, timeout=10)

    done = await stored(a, run.id)
    assert done.step_run("w").method is Method.HUMAN
    assert len(worker.assignments) == 1, "nobody worked the step twice"
    async with a.persistence.transaction(TENANT):
        verification = await a.ledger.verify(TENANT)
        entries = list(await a.ledger.entries(TENANT, run.id))
        records = list(await a.provenance.of_run(TENANT, run.id))
    assert verification.intact, verification.findings
    kinds = [e.kind for e in entries]
    assert "run.claim_lost" not in kinds
    assert kinds.count("step.taken_over") == 1
    chain = provenance.verify(done, records, entries)
    assert chain.intact, chain.findings
