"""A worker connected outbound to one instance serves the runner of another, across restarts of
either (ADR-0156 §4, ADR-0013 A, issue #625), against PostgreSQL.

Two instances share one database and nothing else. B serves the host of the outbound binding;
the reference worker connects to B and opens no port. A runs the runner, and reaches the worker
through the relay in the database. A worker step runs on it to its end:

- while B, the instance the worker is connected to, restarts in the middle of the step: the
  stream A reads falls silent, A asks the worker's state and reads on from its last event, and
  the step finishes under the one assignment it was given;
- while A, the runner's instance, restarts in the middle of the step: it stops the step at its
  worker's boundary, and the runner of the instance that comes up continues the run from the
  checkpoint over the same binding.

A message sent to the step through B reaches the worker that A's runner follows. The removal
test withholds the connected worker as it withholds one at an endpoint.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from adapters.workers.test_connected import NAME, connected, hosting
from fakes.identity import FixedTenants
from fakes.maturity import VERIFIED
from fakes.ports import free_port
from sqlalchemy import text

from integration.test_removal_test import EXAMPLE, load, result_of, run_removal
from integration.test_removal_test import TENANT as REMOVAL_TENANT
from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.memory import MemoryObjectStore, MemoryRelay
from taktus.adapters.driven.postgres import PostgresRelay
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.connected import connected_worker
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.process.application.service.register_version import RegisterProcessVersion
from taktus.components.run.application.service import (
    RunEngine,
    Runner,
    RunnerOptions,
    StartRun,
    SteerStep,
)
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.components.run.domain.service import provenance
from taktus.composition.local import LocalWiring
from taktus.ports.objectstore import ObjectStore
from taktus.ports.worker import ComputeLimit, Limits, Worker
from taktus.shared.v1 import (
    Commissioned,
    ExactnessClass,
    Fallback,
    InputKind,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    Step,
)

from .test_runner_fence import Instance

TENANT = f"connected_{os.urandom(4).hex()}"
KEY = "k-" + os.urandom(8).hex()
ADAPTER = f"worker.{NAME}"


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


def engine(instance: Instance, objects: ObjectStore, worker: Worker) -> RunEngine:
    return RunEngine(
        maturities=VERIFIED,
        runs=instance.runs,
        work=instance.persistence,
        objects=objects,
        ledger=instance.ledger,
        provenance=instance.provenance,
        workers=StaticWorkerPool([(ADAPTER, worker)], connected=frozenset({ADAPTER})),
        clock=instance.clock,
        ids=instance.ids,
        telemetry=NoTelemetry(),
        queue=instance.queue,
    )


def runner(instance: Instance, engine: RunEngine, name: str) -> Runner:
    return Runner(
        engine=engine,
        queue=instance.queue,
        work=instance.persistence,
        clock=instance.clock,
        options=RunnerOptions(
            tenants=FixedTenants((TENANT,)),
            claimant=name,
            concurrency=1,
            poll_seconds=0.05,
            heartbeat_seconds=0.1,
        ),
    )


async def submit(instance: Instance, objects: ObjectStore, worker: Worker) -> Run:
    step = Step(
        id="w",
        method=Method.WORKER,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        fallback=Fallback(when="x", to=Method.HUMAN),
        requires=("shell.script",),
    )
    plan = Plan(
        id=f"pln_{os.urandom(4).hex()}",
        command_id="cmd_1",
        goal="g",
        autonomy_level=3,
        steps=(step,),
        results_in=PlanResult.RUN,
        status=PlanStatus.COMMISSIONED,
        commissioned=Commissioned(by="idn_t", at=instance.clock.now()),
    )
    return await engine(instance, objects, worker).submit(
        StartRun(
            plan=plan,
            work={"w": {"task": {"goal": "g", "acceptance": ["a"]}}},
            budget=Limits(compute=ComputeLimit(seconds=60, resource_class="cpu.small")),
            process_version="p@1",
            actor="idn_t",
            tenant=TENANT,
        )
    )


async def stored(instance: Instance, run_id: str) -> Run:
    async with instance.persistence.transaction(TENANT):
        run = await instance.runs.get(TENANT, run_id)
    assert run is not None
    return run


async def until(condition: Any, seconds: float = 60.0) -> None:
    async with asyncio.timeout(seconds):
        while not await condition():  # noqa: ASYNC110 — the state polled is the database's
            await asyncio.sleep(0.05)


async def verified(instance: Instance, run: Run) -> list[str]:
    async with instance.persistence.transaction(TENANT):
        entries = list(await instance.ledger.entries(TENANT, run.id))
        records = list(await instance.provenance.of_run(TENANT, run.id))
        assert (await instance.ledger.verify(TENANT)).intact
    assert provenance.verify(run, records, entries).intact
    return [e.kind for e in entries]


async def test_a_restart_of_the_instance_the_worker_is_connected_to_resumes_the_step(
    instances: tuple[Instance, Instance], tmp_path: Path
) -> None:
    a, b = instances
    objects = MemoryObjectStore()
    port = free_port()
    base = f"http://127.0.0.1:{port}/workers/{NAME}/relay"
    async with connected_worker(PostgresRelay(a.persistence), ADAPTER, idle_timeout=2.0) as w:
        run = await submit(a, objects, w)
        first = runner(a, engine(a, objects, w), "a")
        task = asyncio.create_task(first.run())
        try:
            with connected(base, tmp_path, KEY, "--step-seconds", "1.0"):
                async with hosting(PostgresRelay(b.persistence), {NAME: KEY}, port):

                    async def bounded() -> bool:
                        return (await stored(a, run.id)).step_run("w").assignment_seq > 2

                    await until(bounded)
                    # Through B: a message reaches the worker A's runner follows (ADR-0156 §8).
                    await engine(b, objects, w).steer(
                        SteerStep(
                            run_id=run.id,
                            step_id="w",
                            text="keep going",
                            actor="idn_person",
                            tenant=TENANT,
                        )
                    )

                    async def received() -> bool:
                        return bool((await stored(a, run.id)).step_run("w").messages)

                    await until(received)
                # B is down. The worker keeps polling; the stream A reads falls silent.
                await asyncio.sleep(1.5)
                assert (await stored(a, run.id)).state is RunState.RUNNING
                async with hosting(PostgresRelay(b.persistence), {NAME: KEY}, port):
                    # B is up again on the same address; the worker reconnects to it.

                    async def finished() -> bool:
                        return (await stored(a, run.id)).state is RunState.FINISHED

                    await until(finished)
        finally:
            await first.stop()
            await asyncio.wait_for(task, 10)
    done = await stored(a, run.id)
    assert done.step_run("w").state is StepState.SUCCEEDED
    kinds = await verified(a, done)
    assert kinds.count("step.assigned") == 1, "one assignment, followed across the restart"
    assert "step.message_received" in kinds
    async with a.persistence.transaction(TENANT):
        records = list(await a.provenance.of_run(TENANT, run.id))
    (record,) = [r for r in records if r.step_id == "w"]
    assert [i.kind for i in record.inputs if i.kind is InputKind.MESSAGE] == [InputKind.MESSAGE]


async def test_a_restart_of_the_runner_s_instance_resumes_the_run_at_its_boundary(
    instances: tuple[Instance, Instance], tmp_path: Path
) -> None:
    a, b = instances
    objects = MemoryObjectStore()
    async with (
        hosting(PostgresRelay(b.persistence), {NAME: KEY}, free_port()) as base,
        connected_worker(PostgresRelay(a.persistence), ADAPTER) as w,
    ):
        with connected(base, tmp_path, KEY, "--step-seconds", "0.6"):
            run = await submit(a, objects, w)
            first = runner(a, engine(a, objects, w), "a")
            task = asyncio.create_task(first.run())

            async def bounded() -> bool:
                return (await stored(a, run.id)).step_run("w").checkpoint is not None

            await until(bounded)
            await first.stop()  # the instance is restarted: the step stops at its boundary
            await asyncio.wait_for(task, 30)
            halted = await stored(a, run.id)
            assert halted.state is RunState.HALTED and halted.step_run("w").checkpoint is not None

            again = Instance.open(str(a.persistence.engine.url.render_as_string(False)))
            try:
                async with connected_worker(PostgresRelay(again.persistence), ADAPTER) as w2:
                    second = runner(again, engine(again, objects, w2), "a2")
                    task = asyncio.create_task(second.run())

                    async def finished() -> bool:
                        return (await stored(again, run.id)).state is RunState.FINISHED

                    try:
                        await until(finished)
                    finally:
                        await second.stop()
                        await asyncio.wait_for(task, 10)
            finally:
                await again.persistence.close()
    done = await stored(a, run.id)
    assert done.step_run("w").state is StepState.SUCCEEDED
    ids = [x.id for x in done.step_run("w").artifacts]
    assert len(ids) == len(set(ids)), "nothing the worker produced is recorded twice"
    await verified(a, done)


async def test_the_removal_test_withholds_a_connected_worker_as_one_at_an_endpoint(
    tmp_path: Path,
) -> None:
    relay = MemoryRelay()
    key_file = tmp_path / "connect.key"
    key_file.write_text(KEY)
    configuration = EnvironmentConfiguration(
        {
            "TAKTUS_WORKERS": NAME,
            f"TAKTUS_WORKER_{NAME.upper()}_EXECUTION": "connected",
            f"TAKTUS_WORKER_{NAME.upper()}_CONNECT_KEY_FILE": str(key_file),
        }
    )
    async with hosting(relay, {NAME: KEY}, free_port()) as base:
        with connected(base, tmp_path, KEY):
            async with LocalWiring(configuration).services(
                state_dir=tmp_path / "state", worker_endpoint="http://unused", relay=relay
            ) as services:
                await services.register_version.execute(
                    RegisterProcessVersion(load(EXAMPLE), tenant=REMOVAL_TENANT)
                )
                run = await run_removal(services, ADAPTER)
                assert run.state is RunState.FINISHED, run.reason
                exercised = (await result_of(services, run, "exercise"))["output"]
    assert exercised["verdict"] == "changed", json.dumps(exercised)
    assert exercised["configuration"]["adapter"] == ADAPTER
    assert exercised["configuration"]["binding"] == "outbound", "taken under the binding"
    (process,) = exercised["processes"]
    assert process["withheld"]["at_step"] == "compute", "withheld, the step has no worker"
