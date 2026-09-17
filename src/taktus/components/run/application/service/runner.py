"""The runner: claims runs from the queue and executes them, several instances side by side.

One runner serves the tenants it is given. In a loop it claims due jobs — up to its free
slots, for each tenant in turn — and executes each in a task of its own through the engine's
`resume`, which starts a submitted run, continues a halted one, or recovers one whose runner
died. While a run executes, a heartbeat renews the claim's lease; a runner that dies stops
renewing, the lease expires, and another runner claims the job and recovers the run at its
last boundary (ADR-0013 A). A runner whose lease was lost while it was still executing — the
database was unreachable for longer than the lease — stops the run at its next boundary and
gives the job up: two runners never execute one run.

What happens when a run ends decides the job:

- finished, halted by admission control, escalated — the job is *completed*: nothing here can
  continue the run, and a person raises the budget or repairs and resumes;
- halted because *this runner* was told to shut down — the job is *released*: another runner,
  or this one after its restart, resumes the run at the boundary it stopped at;
- the engine raised — the job is *released* and counted as an attempt; after the queue's limit
  of attempts the job stays for a person.

`stop()` is the shutdown of ADR-0005 in operation: no new claim; every running run is asked to
stop at its next step boundary, and the running worker step may finish up to the ceiling; then
the jobs are released and `stop()` returns. Nothing here reads the clock or sleeps except
through the clock port.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field

from taktus.components.run.application.service.execute_run import ResumeRun, RunEngine
from taktus.components.run.domain.model import Cause, Run, RunState
from taktus.ports.clock import Clock
from taktus.ports.persistence import Tenant, UnitOfWork
from taktus.ports.queue import RUN_EXECUTE, Job, Queue


@dataclass(frozen=True)
class RunnerOptions:
    tenants: Sequence[Tenant]
    claimant: str
    """How this runner names itself on the claims it holds; unique among live runners."""
    concurrency: int = 4
    poll_seconds: float = 1.0
    heartbeat_seconds: float = 20.0
    """How often a held lease is renewed; a third of the lease is a safe value."""
    actor: str = "taktusd"
    """Who the ledger names as the actor of `run.resumed` and `run.recovered`."""


@dataclass
class Outcome:
    """What the runner did with one job, for tests and the log."""

    tenant: Tenant
    job: Job
    run: Run | None = None
    disposition: str = "unknown"  # completed | released | lost
    error: str | None = None


@dataclass
class _Executing:
    tenant: Tenant
    job: Job
    run_id: str
    task: asyncio.Task[Outcome] | None = None
    lost: bool = False
    stop_requested: bool = False


@dataclass
class Runner:
    engine: RunEngine
    queue: Queue
    work: UnitOfWork
    clock: Clock
    options: RunnerOptions
    _executing: dict[str, _Executing] = field(default_factory=dict, init=False)
    _stopping: bool = field(default=False, init=False)
    _outcomes: list[Outcome] = field(default_factory=list, init=False)
    _woken: asyncio.Event = field(default_factory=asyncio.Event, init=False)

    @property
    def outcomes(self) -> Sequence[Outcome]:
        """Every job this runner finished with, in order."""
        return tuple(self._outcomes)

    @property
    def executing(self) -> int:
        return len(self._executing)

    async def run(self) -> None:
        """Claim and execute until `stop()`; returns once every run has landed."""
        while not self._stopping:
            claimed = await self._claim_round()
            if claimed == 0:
                await self._idle()
        await self._drain()

    async def stop(self) -> None:
        """No new claim from now on; running runs stop at their next boundary. Returns when
        `run()` can return: every job released or completed."""
        self._stopping = True
        self._woken.set()
        for executing in list(self._executing.values()):
            if not executing.stop_requested:
                executing.stop_requested = True
                await self.engine.request_stop(executing.run_id)
        await self._drain()

    # --- claiming --------------------------------------------------------------------------------

    async def _claim_round(self) -> int:
        claimed = 0
        for tenant in self.options.tenants:
            free = self.options.concurrency - len(self._executing)
            if free <= 0 or self._stopping:
                break
            async with self.work.transaction(tenant):
                jobs = await self.queue.claim(tenant, self.options.claimant, free)
            for job in jobs:
                self._start(tenant, job)
                claimed += 1
        return claimed

    def _start(self, tenant: Tenant, job: Job) -> None:
        run_id = str(job.payload.get("run_id", ""))
        executing = _Executing(tenant, job, run_id)
        executing.task = asyncio.create_task(self._execute(executing), name=f"run:{run_id}")
        self._executing[job.id] = executing

    async def _idle(self) -> None:
        """Wait one poll interval, or less when `stop()` wakes the loop."""
        self._woken.clear()
        sleeper = asyncio.ensure_future(self.clock.sleep(self.options.poll_seconds))
        waker = asyncio.ensure_future(self._woken.wait())
        done, pending = await asyncio.wait({sleeper, waker}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            task.result()

    async def _drain(self) -> None:
        tasks = [e.task for e in self._executing.values() if e.task is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # --- executing one job -----------------------------------------------------------------------

    async def _execute(self, executing: _Executing) -> Outcome:
        outcome = Outcome(executing.tenant, executing.job)
        heartbeat = asyncio.create_task(
            self._heartbeat(executing), name=f"lease:{executing.job.id}"
        )
        try:
            if executing.job.kind != RUN_EXECUTE or not executing.run_id:
                outcome.error = f"job {executing.job.id!r} is not a run to execute"
                await self._complete(executing)
                outcome.disposition = "completed"
                return outcome
            try:
                run = await self.engine.resume(
                    ResumeRun(
                        run_id=executing.run_id,
                        actor=self.options.actor,
                        tenant=executing.tenant,
                    )
                )
            except Exception as error:  # every failure of one run is one outcome, not a crash
                outcome.error = f"{type(error).__name__}: {error}"
                await self._release(executing)
                outcome.disposition = "released"
                return outcome
            outcome.run = run
            if executing.lost:
                outcome.disposition = "lost"
                return outcome
            if (
                run.state is RunState.HALTED
                and run.cause is Cause.STOP
                and executing.stop_requested
            ):
                await self._release(executing)
                outcome.disposition = "released"
            else:
                await self._complete(executing)
                outcome.disposition = "completed"
            return outcome
        finally:
            heartbeat.cancel()
            self._executing.pop(executing.job.id, None)
            self._outcomes.append(outcome)

    async def _heartbeat(self, executing: _Executing) -> None:
        """Renew the lease while the run executes. A renewal that fails means the claim is no
        longer ours: the run is asked to stop at its boundary and the job is left alone."""
        while True:
            await self.clock.sleep(self.options.heartbeat_seconds)
            renewed = await self._renew(executing)
            if renewed is None:
                continue  # an unreachable store is a missed heartbeat, not a lost lease
            if not renewed:
                executing.lost = True
                executing.stop_requested = True
                await self.engine.request_stop(executing.run_id)
                return

    async def _renew(self, executing: _Executing) -> bool | None:
        """True renewed, False lost, None unknown (the store did not answer)."""
        try:
            async with self.work.transaction(executing.tenant):
                return await self.queue.extend(
                    executing.tenant, executing.job.id, self.options.claimant
                )
        except Exception:  # the next heartbeat asks again; the lease decides
            return None

    async def _release(self, executing: _Executing) -> None:
        async with self.work.transaction(executing.tenant):
            await self.queue.release(executing.tenant, executing.job.id, self.options.claimant)

    async def _complete(self, executing: _Executing) -> None:
        async with self.work.transaction(executing.tenant):
            await self.queue.complete(executing.tenant, executing.job.id, self.options.claimant)
