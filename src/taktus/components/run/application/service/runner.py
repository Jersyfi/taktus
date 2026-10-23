"""The runner: claims runs from the queue and executes them, several instances side by side.

One runner serves the tenants it is given. In a loop it claims due jobs up to its free slots,
one job per tenant in turn, starting each round with the next tenant, so that a tenant with much
queued work holds back no other (issue #319). It executes each in a task of its own through the
engine's `resume`, which starts a submitted run, continues a halted one, or recovers one whose
runner died. While a run executes, a heartbeat renews the claim's lease; a runner that dies
stops renewing, the lease expires, and another runner claims the job and recovers the run at its
last boundary (ADR-0013 A).

A runner can also lose its claim while it is alive: it could not reach the database, or was
paused, for longer than the lease, and another runner claimed the job. Every write of the run
is made under the claim and checks it in its own transaction (`ResumeRun.claim`, #107). The
first write after the takeover — the end of the step the runner was inside, or its next
boundary — is refused, nothing of it lands, and the runner gives the run up without touching
the job. A heartbeat that finds the claim gone asks the run to stop at its boundary as well, so
that a worker step ends before it has to be refused. Two runners never both commit to one run.

What happens when a run ends decides the job:

- finished, halted by admission control, escalated — the job is *completed*: nothing here can
  continue the run, and a person raises the budget or repairs and resumes;
- halted because *this runner* was told to shut down — the job is *released*: another runner,
  or this one after its restart, resumes the run at the boundary it stopped at;
- halted because the step's worker was at capacity — the job is *deferred*: given back to be
  claimed again after a delay that doubles with every answer of the same wait, up to a cap.
  The run waits at its boundary, holding no slot of any runner and no place at the worker; the
  runner that claims the job next asks the worker again, and the step's ceiling turns a wait
  that does not end into an escalation (ADR-0037). A model's provider at its rate limit is
  waited for the same way; where it named its delay in `Retry-After`, the job is deferred by
  that delay instead (ADR-0043);
- halted because a `wait` step parked — the job is *deferred* to the wait's next check, which
  the step's block names. A wait for time or for an outside system holds no place meanwhile,
  as a wait for a person does not either (ADR-0103);
- the engine raised — the job is *released* and counted as an attempt. The next claim recovers
  the run, once, so a cause that raises again is recovered again: a step whose adapter fails
  ends the step instead, with its cause, and never raises (#589). At the job's last attempt
  (`max_attempts`) a step that raises fails with what it raised, and the run escalates for it:
  the job is completed and the run is with a person, not `running` for nobody (#591). An
  exception outside every step still releases the job, which then stays for a person;
- the claim was lost — the job is another runner's and stays untouched; the loss is recorded as
  `run.claim_lost` in the run's chain, so that a person hears of it (ADR-0106);
- a person took the running step over — the claim passed to the take-over with the step's
  state, and the job is the person's until they hand the result back or their lease ends
  (ADR-0128). The runner leaves it alone. A take-over asked on the job is read with every
  renewal of the lease, and handed to the engine, which stops the step at its boundary.

Every outcome is handed to `on_outcome`, which the daemon writes to its log: a run that did not
finish names the step it ended at and why (#589). The runner itself keeps only the latest
`outcomes_kept` of them, so that a runner that runs for weeks holds no more for it than a runner
that ran an hour; `finished` counts all of them (#592).

The same holds for a run that had already ended when its job was claimed: a runner that died
after the run's last state was committed and before it completed the job leaves exactly that.
The engine executes nothing for it (`ResumeRun.on_claim`), and the job is completed.

`stop()` is the shutdown of ADR-0005 in operation: no new claim; every running run is asked to
stop at its next step boundary, and the running worker step may finish up to the ceiling; then
the jobs are released and `stop()` returns. Nothing here reads the clock or sleeps except
through the clock port.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from taktus.components.run.application.service.execute_run import ResumeRun, RunEngine
from taktus.components.run.domain.model import Cause, ClaimLost, Run, RunState, StepState
from taktus.components.run.domain.service import waiting
from taktus.ports.clock import Clock
from taktus.ports.identity import ServedTenants
from taktus.ports.persistence import Tenant, UnitOfWork
from taktus.ports.queue import RUN_EXECUTE, Claim, Job, Queue, TakeoverAsked


@dataclass(frozen=True)
class RunnerOptions:
    tenants: ServedTenants
    """The tenants this runner serves, asked again at every claim round (ADR-0104)."""
    claimant: str
    """How this runner names itself on the claims it holds; unique among live runners."""
    concurrency: int = 4
    poll_seconds: float = 1.0
    heartbeat_seconds: float = 20.0
    """How often a held lease is renewed; a third of the lease is a safe value."""
    actor: str = "taktusd"
    """Who the ledger names as the actor of `run.resumed` and `run.recovered`."""
    max_attempts: int = 5
    """The queue's limit of attempts, which the composition reads from the queue it wires.
    At a job's last attempt, a step that raises fails and the run escalates (#591)."""
    wait_first_seconds: float = 1.0
    """How long a run whose worker was at capacity waits before it is tried again the first
    time; every further answer of the same wait doubles it (ADR-0037)."""
    wait_cap_seconds: float = 60.0
    """The longest delay between two tries of a waiting run."""
    on_outcome: Callable[[Outcome], None] | None = None
    """Told of every job this runner finished with, for the log (#589). What it raises is
    swallowed: telling must never take the runner down."""
    outcomes_kept: int = 1000
    """How many of the latest outcomes the runner keeps for `outcomes`; older ones are dropped,
    and the log has had them through `on_outcome` (#592)."""


@dataclass
class Outcome:
    """What the runner did with one job, for tests and the log."""

    tenant: Tenant
    job: Job
    run: Run | None = None
    disposition: str = "unknown"  # completed | released | deferred | lost | taken_over
    error: str | None = None

    @property
    def step(self) -> str | None:
        """The step the run ended at when it did not finish: the first that failed or was
        refused, else the first that stopped. None for a finished run or no run."""
        if self.run is None or self.run.state is RunState.FINISHED:
            return None
        for states in ((StepState.FAILED, StepState.REJECTED), (StepState.STOPPED,)):
            for step_run in self.run.step_runs:
                if step_run.state in states:
                    return step_run.step_id
        return None


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
    _outcomes: deque[Outcome] = field(init=False)
    _finished: int = field(default=0, init=False)
    _woken: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _turn: int = field(default=0, init=False)
    """Which served tenant the next claim round starts with."""

    def __post_init__(self) -> None:
        self._outcomes = deque(maxlen=max(self.options.outcomes_kept, 0))

    @property
    def outcomes(self) -> Sequence[Outcome]:
        """The latest jobs this runner finished with, in order, at most `outcomes_kept`."""
        return tuple(self._outcomes)

    @property
    def finished(self) -> int:
        """How many jobs this runner finished with since it began, kept or dropped."""
        return self._finished

    @property
    def executing(self) -> int:
        return len(self._executing)

    async def run(self) -> None:
        """Claim and execute until `stop()`; returns once every run has landed. A round that
        claims nothing waits one poll interval, or until a run ends and frees its place."""
        while not self._stopping:
            # Cleared before the round: a run that ends during it wakes the next wait at once.
            self._woken.clear()
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
        """Fill the free places one job per tenant at a time, round robin. A tenant with nothing
        due drops out of the round; the next round starts one tenant further on."""
        served = list(await self.options.tenants.served())
        if not served:
            return 0
        start = self._turn % len(served)
        self._turn = start + 1
        waiting = served[start:] + served[:start]
        claimed = 0
        while waiting and not self._stopping:
            still: list[Tenant] = []
            for tenant in waiting:
                if self.options.concurrency - len(self._executing) <= 0 or self._stopping:
                    return claimed
                async with self.work.transaction(tenant):
                    jobs = await self.queue.claim(tenant, self.options.claimant, 1)
                for job in jobs:
                    self._start(tenant, job)
                    claimed += 1
                if jobs:
                    still.append(tenant)
            waiting = still
        return claimed

    def _start(self, tenant: Tenant, job: Job) -> None:
        run_id = str(job.payload.get("run_id", ""))
        executing = _Executing(tenant, job, run_id)
        executing.task = asyncio.create_task(self._execute(executing), name=f"run:{run_id}")
        self._executing[job.id] = executing

    async def _idle(self) -> None:
        """Wait one poll interval, or less when `stop()` or a run that ended wakes the loop."""
        if self._woken.is_set():
            return
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
                        on_claim=True,
                        claim=Claim(
                            job_id=executing.job.id,
                            claimant=self.options.claimant,
                            attempt=executing.job.attempts,
                        ),
                        # The queue counts claims less deferrals towards its limit.
                        last_attempt=executing.job.attempts - executing.job.deferrals
                        >= self.options.max_attempts,
                    )
                )
            except ClaimLost as lost:
                # Another runner holds the job and executes the run: nothing here touches either.
                executing.lost = True
                outcome.error = str(lost)
                outcome.disposition = "lost"
                await self._note_lost(executing, outcome)
                return outcome
            except Exception as error:  # every failure of one run is one outcome, not a crash
                # The engine notes the step it raised in (#589).
                notes = "".join(f"; {note}" for note in getattr(error, "__notes__", ()))
                outcome.error = f"{type(error).__name__}: {error}{notes}"
                await self._release(executing)
                outcome.disposition = "released"
                return outcome
            outcome.run = run
            if self.engine.passed(executing.run_id):
                # The claim passed to a person who took the step over: the job is theirs.
                outcome.disposition = "taken_over"
                return outcome
            if executing.lost:
                outcome.disposition = "lost"
                await self._note_lost(executing, outcome)
                return outcome
            if run.state is RunState.HALTED and run.cause is Cause.CAPACITY:
                await self._defer(executing, run)
                outcome.disposition = "deferred"
            elif run.state is RunState.HALTED and run.cause is Cause.PARKED:
                await self._park(executing, run)
                outcome.disposition = "deferred"
            elif (
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
            if self._executing.get(executing.job.id) is executing:
                # A later claim of the same job by this runner is another entry; it stays.
                del self._executing[executing.job.id]
            self._outcomes.append(outcome)
            self._finished += 1
            if self.options.on_outcome is not None:
                with contextlib.suppress(Exception):
                    self.options.on_outcome(outcome)
            # A place is free: the loop claims again now, not after its poll interval.
            self._woken.set()

    async def _heartbeat(self, executing: _Executing) -> None:
        """Renew the lease while the run executes. A renewal that fails means the claim is no
        longer ours: the run is asked to stop at its boundary and the job is left alone, and
        so is the worker's assignment, which the runner holding the claim now adopts
        (ADR-0038). A renewal also reads a take-over asked on the job, which the engine
        serves at the step's next boundary (ADR-0128); a claim the engine passed to a take-over
        is not lost."""
        while True:
            await self.clock.sleep(self.options.heartbeat_seconds)
            renewed = await self._renew(executing)
            if renewed is None:
                continue  # an unreachable store is a missed heartbeat, not a lost lease
            if renewed:
                asked = await self._asked(executing)
                if asked is not None:
                    await self.engine.takeover_asked(executing.run_id, asked)
                continue
            if self.engine.passed(executing.run_id):
                return
            executing.lost = True
            executing.stop_requested = True
            self.engine.relinquish(executing.run_id)
            return

    async def _note_lost(self, executing: _Executing, outcome: Outcome) -> None:
        """Record the lost claim in the run's chain, for the person who must look at the
        runners (ADR-0106 §2). A recording that fails is said in the outcome, and the runner
        goes on."""
        try:
            await self.engine.record_claim_lost(executing.tenant, executing.run_id)
        except Exception as error:  # noting a loss must never take the runner down
            outcome.error = f"{outcome.error or 'claim lost'}; not recorded: {type(error).__name__}"

    async def _renew(self, executing: _Executing) -> bool | None:
        """True renewed, False lost, None unknown (the store did not answer)."""
        try:
            async with self.work.transaction(executing.tenant):
                return await self.queue.extend(
                    executing.tenant, executing.job.id, self.options.claimant
                )
        except Exception:  # the next heartbeat asks again; the lease decides
            return None

    async def _asked(self, executing: _Executing) -> TakeoverAsked | None:
        """The take-over asked on the job, if any; None also when the store did not answer,
        and the next heartbeat reads again."""
        try:
            async with self.work.transaction(executing.tenant):
                return await self.queue.takeover_asked(executing.tenant, executing.job.id)
        except Exception:  # the next heartbeat asks again
            return None

    async def _release(self, executing: _Executing) -> None:
        async with self.work.transaction(executing.tenant):
            await self.queue.release(executing.tenant, executing.job.id, self.options.claimant)

    async def _defer(self, executing: _Executing, run: Run) -> None:
        """Give the job back for later: after the delay the provider named in its
        `Retry-After`, recorded with the step's block, never sooner than the first delay; else
        after the delay that doubles with every answer of the same wait (ADR-0037, ADR-0043)."""
        waiting_step = run.next_step_run()
        waits = 1 if waiting_step is None else waiting_step.waits
        named = (
            None
            if waiting_step is None or waiting_step.block is None
            else waiting_step.block.retry_after_seconds
        )
        seconds = (
            waiting.delay(waits, self.options.wait_first_seconds, self.options.wait_cap_seconds)
            if named is None
            else max(named, self.options.wait_first_seconds)
        )
        async with self.work.transaction(executing.tenant):
            await self.queue.defer(
                executing.tenant, executing.job.id, self.options.claimant, seconds
            )

    async def _park(self, executing: _Executing, run: Run) -> None:
        """Give the job back until the parked wait's next check, holding no place meanwhile
        (ADR-0103). A check already due defers by nothing."""
        checks = [
            s.block.next_check_at
            for s in run.step_runs
            if s.block is not None and s.block.next_check_at is not None
        ]
        check_at = min(checks) if checks else None
        seconds = (
            self.options.wait_first_seconds
            if check_at is None
            else max(0.0, (check_at - self.clock.now()).total_seconds())
        )
        async with self.work.transaction(executing.tenant):
            await self.queue.defer(
                executing.tenant, executing.job.id, self.options.claimant, seconds
            )

    async def _complete(self, executing: _Executing) -> None:
        async with self.work.transaction(executing.tenant):
            await self.queue.complete(executing.tenant, executing.job.id, self.options.claimant)
