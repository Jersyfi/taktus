"""A runner dies while its worker holds the step's assignment (issue #130, ADR-0038).

Two instances share one PostgreSQL database and one reference worker, reached over HTTP: each
has its own connection pool, engine and runner, as two `taktusd` processes would. Runner A
claims a run with one worker step and stops at a chosen point. From there on it neither renews
its lease nor writes, as a process that was killed does not. The worker keeps what A handed
over. The lease runs out, runner B claims the job and recovers the run. Three points:

- `accepted`: the worker has accepted the assignment, and A has not committed `step.started`;
- `running`: A has persisted the worker's first inner boundary, and the step runs on;
- `late`: A has committed `step.assigned` and its post has not reached the worker. Here A is
  not dead but cut off: once B has recovered the run, A's post arrives.

Each instance reaches the worker through a recorder, so the test knows every assignment the
worker accepted, every 409 it answered and every stop it received. Afterwards:

- the ledger names every assignment the worker accepted, before the worker accepted it;
- every accepted assignment was continued to its end by the run, or received a stop — here
  every one was continued, so no stop was sent at all;
- the worker accepted one assignment for the step: no second ran beside it, and by the
  worker's own accept and finish times nothing overlapped;
- every output of the step exists once, and the ledger and provenance chains verify.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal

import httpx
import pytest
from fakes.maturity import VERIFIED
from sqlalchemy import text

from taktus.adapters.driven.memory import MemoryObjectStore
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.http import HttpWorker
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.run.application.service import (
    RunEngine,
    Runner,
    RunnerOptions,
    StartRun,
)
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.components.run.domain.service import provenance
from taktus.ports.worker import (
    ArtifactList,
    Assignment,
    AssignmentExists,
    AssignmentId,
    AssignmentState,
    Capabilities,
    ComputeLimit,
    Estimate,
    EstimateRequest,
    Event,
    Limits,
    StopRequest,
)
from taktus.shared.v1 import (
    Artifact,
    Commissioned,
    ExactnessClass,
    Fallback,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    Step,
)

from .test_runner_fence import Instance as FenceInstance

TENANT = f"handover_{os.urandom(4).hex()}"


class Instance(FenceInstance):
    """The fence test's view of the shared database, in this test's own tenant."""

    @classmethod
    def open(cls, url: str) -> Instance:
        base = FenceInstance.open(url)
        return cls(**{f: getattr(base, f) for f in base.__dataclass_fields__})

    def runner(self, engine: RunEngine, name: str, *, heartbeat: float) -> Runner:
        return Runner(
            engine=engine,
            queue=self.queue,
            work=self.persistence,
            clock=self.clock,
            options=RunnerOptions(
                tenants=(TENANT,),
                claimant=name,
                concurrency=1,
                poll_seconds=0.05,
                heartbeat_seconds=heartbeat,
            ),
        )

    async def run(self, run_id: str) -> Run:
        async with self.persistence.transaction(TENANT):
            run = await self.runs.get(TENANT, run_id)
        assert run is not None
        return run

    async def kinds(self, run_id: str) -> list[str]:
        async with self.persistence.transaction(TENANT):
            return [e.kind for e in await self.ledger.entries(TENANT, run_id)]


COMMANDS = 12  # times --step-seconds 0.1 in the worker: a step of about a second and a half

type Point = Literal["accepted", "running", "late"]


class Dead(Exception):
    """Raised in a stopped runner when the test ends, so that its task can be collected."""


@dataclass
class Log:
    """What the worker was told and answered, through every instance."""

    accepted: list[tuple[str, str]] = field(default_factory=list)
    """(instance, assignment id) for every post the worker answered 201."""
    exists: list[tuple[str, str]] = field(default_factory=list)
    """(instance, assignment id) for every post the worker answered 409."""
    stops: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Gate:
    """Where runner A stops, and what it does when the test lets it go on."""

    point: Point
    reached: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)
    go_on: bool = False

    async def hold(self) -> None:
        self.reached.set()
        await self.release.wait()
        if not self.go_on:
            raise Dead


class Recorder:
    """One instance's way to the worker: the HTTP adapter, recorded, with A's stopping point."""

    def __init__(self, inner: HttpWorker, name: str, log: Log, gate: Gate | None) -> None:
        self.inner, self.name, self.log, self.gate = inner, name, log, gate

    def _at(self, point: Point) -> bool:
        gate = self.gate
        if gate is None or gate.point != point or gate.reached.is_set():
            return False
        return True

    async def capabilities(self) -> Capabilities:
        return await self.inner.capabilities()

    async def estimate(self, request: EstimateRequest) -> Estimate:
        return await self.inner.estimate(request)

    async def assign(self, assignment: Assignment) -> AssignmentState:
        if self._at("late"):
            assert self.gate is not None
            await self.gate.hold()
        try:
            state = await self.inner.assign(assignment)
        except AssignmentExists:
            self.log.exists.append((self.name, assignment.assignment_id))
            raise
        self.log.accepted.append((self.name, assignment.assignment_id))
        if self._at("accepted"):
            assert self.gate is not None
            await self.gate.hold()
        return state

    async def events(self, assignment_id: AssignmentId, *, after: int = 0) -> AsyncIterator[Event]:
        async for event in self.inner.events(assignment_id, after=after):
            yield event
            # Asked for the next event: the engine has committed the boundary it was given.
            if event.type == "step.boundary" and self._at("running"):
                assert self.gate is not None
                await self.gate.hold()

    async def state(self, assignment_id: AssignmentId) -> AssignmentState:
        return await self.inner.state(assignment_id)

    async def stop(self, assignment_id: AssignmentId, request: StopRequest) -> AssignmentState:
        self.log.stops.append((self.name, assignment_id))
        return await self.inner.stop(assignment_id, request)

    async def artifacts(self, assignment_id: AssignmentId) -> ArtifactList:
        return await self.inner.artifacts(assignment_id)

    async def artifact_bytes(self, assignment_id: AssignmentId, artifact: Artifact) -> bytes:
        return await self.inner.artifact_bytes(assignment_id, artifact)


@pytest.fixture
async def instances(postgres_url: str) -> AsyncIterator[tuple[Instance, Instance]]:
    a, b = Instance.open(postgres_url), Instance.open(postgres_url)
    async with a.persistence.engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('taktus.tenant', :t, true)"), {"t": TENANT}
        )
        await connection.execute(
            text(
                "INSERT INTO tenant (id, name, created_at) VALUES (:t, :t, now()) "
                "ON CONFLICT DO NOTHING"  # one tenant for the three points
            ),
            {"t": TENANT},
        )
    try:
        yield a, b
    finally:
        await a.persistence.close()
        await b.persistence.close()


def engine(instance: Instance, worker: Recorder) -> RunEngine:
    return RunEngine(
        maturities=VERIFIED,
        runs=instance.runs,
        work=instance.persistence,
        objects=MemoryObjectStore(),
        ledger=instance.ledger,
        provenance=instance.provenance,
        workers=StaticWorkerPool([("worker.script", worker)]),
        clock=instance.clock,
        ids=instance.ids,
        telemetry=NoTelemetry(),
        queue=instance.queue,
    )


async def submit(engine: RunEngine, instance: Instance) -> str:
    step = Step(
        id="compute",
        method=Method.WORKER,
        reason="running commands needs a shell, which a worker offers",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        fallback=Fallback(when="the assignment fails", to=Method.HUMAN),
        requires=("shell.script",),
    )
    commands = [f"echo {n}" for n in range(1, COMMANDS + 1)]
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
    run = await engine.submit(
        StartRun(
            plan=plan,
            work={
                "compute": {
                    "task": {
                        "goal": "run the commands",
                        "acceptance": ["every command ran"],
                        "inputs": {"commands": commands},
                    },
                    "max_steps": COMMANDS,
                }
            },
            budget=Limits(compute=ComputeLimit(seconds=60, resource_class="cpu.small")),
            process_version="p@1",
            actor="idn_t",
            tenant=TENANT,
            margin=0.0,
        )
    )
    return run.id


@pytest.mark.parametrize("point", ["accepted", "running", "late"])
async def test_an_assignment_a_stopped_runner_handed_over_is_adopted_not_repeated(
    instances: tuple[Instance, Instance], worker_endpoint: str, point: Point
) -> None:
    a, b = instances
    log, gate = Log(), Gate(point)
    http_a, http_b = HttpWorker(worker_endpoint), HttpWorker(worker_endpoint)
    engine_a = engine(a, Recorder(http_a, "a", log, gate))
    engine_b = engine(b, Recorder(http_b, "b", log, None))
    run_id = await submit(engine_a, a)
    first = a.runner(engine_a, "a", heartbeat=3600)  # stopped: no renewal once at the gate
    second = b.runner(engine_b, "b", heartbeat=0.3)
    tasks = [asyncio.create_task(first.run())]
    try:
        async with asyncio.timeout(20):
            await gate.reached.wait()
        stopped_at = await a.run(run_id)
        compute = stopped_at.step_run("compute")
        assert compute.assignment_open and compute.assignment_id is not None
        if point == "running":
            assert compute.state is StepState.RUNNING and compute.checkpoint is not None
        else:
            assert compute.state is StepState.ADMITTED, "A died before step.started"
        kinds_a = await a.kinds(run_id)
        assert kinds_a[-1] == ("step.started" if point == "running" else "step.assigned")

        tasks.append(asyncio.create_task(second.run()))
        async with asyncio.timeout(60):
            while not second.outcomes:  # noqa: ASYNC110 — the state polled is the runner's
                await asyncio.sleep(0.02)
        assert second.outcomes[0].disposition == "completed", second.outcomes[0].error
        if point == "late":
            # A comes back and posts what it had recorded: the worker answers 409.
            gate.go_on = True
            gate.release.set()
            async with asyncio.timeout(20):
                while not first.outcomes:  # noqa: ASYNC110 — the state polled is the runner's
                    await asyncio.sleep(0.02)
            assert first.outcomes[0].disposition == "lost", first.outcomes[0]
            assert log.exists == [("a", compute.assignment_id)], "A's late post was refused"
        # What the worker was asked to stop while the runs were the runners' own; stopping
        # the runners below asks a stopped runner to stop what it still holds.
        stops = {asg for _, asg in log.stops}
    finally:
        gate.release.set()
        await first.stop()
        await second.stop()
        for task in tasks:
            await asyncio.wait_for(task, timeout=20)
        await http_a.close()
        await http_b.close()

    finished = await b.run(run_id)
    assert finished.state is RunState.FINISHED, (finished.state, finished.reason)
    compute_done = finished.step_run("compute")
    assert [x.id for x in compute_done.artifacts] == [
        f"output-{n}" for n in range(1, COMMANDS + 1)
    ], "every output, once"
    assert not compute_done.assignment_open

    # Every assignment the worker accepted is named in the ledger.
    async with a.persistence.transaction(TENANT):
        entries = list(await a.ledger.entries(TENANT, run_id))
        verification = await a.ledger.verify(TENANT)
        records = list(await a.provenance.of_run(TENANT, run_id))
    accepted = {asg for _, asg in log.accepted}
    assigned = {e.refs.assignment_id for e in entries if e.kind == "step.assigned"}
    assert accepted <= assigned, (accepted, assigned)

    # Every accepted assignment was continued to its end by the run, or was stopped.
    ended = {e.refs.assignment_id for e in entries if e.kind == "step.finished"}
    assert accepted <= ended | stops, (accepted, ended, stops)
    assert stops == set(), "every assignment was continued; none needed a stop"

    # One assignment executed the step; by the worker's own times nothing ran beside it.
    assert len(accepted) == 1, log.accepted
    assert [name for name, _ in log.accepted] == (["b"] if point == "late" else ["a"])
    async with httpx.AsyncClient(base_url=worker_endpoint) as client:
        for asg in accepted:
            state = (await client.get(f"/v1/assignments/{asg}")).json()
            assert state["status"] == "finished" and state["outcome"] == "succeeded", state

    kinds = [e.kind for e in entries]
    recovered = kinds.index("run.recovered")
    assert kinds[:recovered] == kinds_a, "nothing from A after it stopped"
    assert kinds.count("run.finished") == 1
    if point == "late":
        assert "step.adopted" not in kinds, "the worker never had A's assignment: B posted it"
        assert kinds.count("step.started") == 1
    else:
        assert kinds.count("step.adopted") == 1, "B adopted what A handed over"
        assert kinds.count("step.started") == (1 if point == "running" else 0)
    assert verification.intact, verification.findings
    chain = provenance.verify(finished, records, entries)
    assert chain.intact, chain.findings
