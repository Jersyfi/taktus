"""Use cases: start a run from a commissioned plan, submit one for a runner, resume a halted
one, request a stop.

One engine, four entry points. `start` creates the run and executes it in this process;
`submit` creates the run and puts a job on the queue, so that a runner — this process or
another — executes it (`runner.py`); `resume` continues a halted or escalated run at its
boundary, starts a submitted one, or recovers a run whose instance stopped without halting it;
`request_stop` asks a running run to stop at its next boundary. Execution is sequential: one
step at a time, in the plan's order.

What happens around every step is the contract of ADR-0005 and is the same for every method:

1. estimate — every step, whatever its method: a worker step asks the worker; an `llm` step
   counts its prompt through the model adapter and bounds its output by the limit it sets; a
   connector call reserves what its operation declares one call consumes, a wait on one as
   many calls as it can make; a rule or a wait on the clock demands nothing, and that is exact.
   A step that cannot be estimated is refused, never admitted (ADR-0005), and the run halts with
   cause `no_estimate`;
2. admit — the estimate, scaled by the measured error of the adapter that gave it
   (`domain.service.budget`), is reserved against what remains of the line the run is held to —
   the budget less its margin (`domain.service.admission`); a step that does not fit is
   *rejected* before anything starts, and the run halts with cause `limit`. A worker receives its
   reservation as its `limits` and halts at its next boundary before crossing it (W-14);
3. run — through the worker port, the rule table, the connector port, or the clock;
4. persist — the step run with its checkpoint, artifacts and raw consumption is written before
   the next step is looked at; every state change and the ledger entry that describes it are
   one transaction of the unit of work, and a step that finished with a result gets its
   provenance record in that same transaction (ADR-0021): what it read and when, what it
   produced, the ledger entry it belongs to;
5. boundary — a stop requested meanwhile, or `stop_after`, takes effect here.

A worker step that is stopped mid-way ends `stopped` with the worker's checkpoint; resuming
hands that checkpoint back to the worker, which produces nothing it produced before it, and the
engine records no artifact twice even if it did. The worker's own step boundaries are persisted
as they arrive, so that an instance that dies mid-step loses at most the worker's current inner
step, not the whole step (ADR-0013 A).

A connector step (`rule: connector`) is where ADR-0005's promise meets the outside. The call
carries an idempotency key derived from run, step and the step's attempt — never stored, so a
step recovered after a crash derives the same key and a `marked` connector answers with the
original record. An outward effect the connector reports becomes an `egress.write` or
`egress.delivery` entry in the same transaction as `step.finished` (ADR-0022 §4). A classified
failure ends the step failed with the connector's cause; the engine retries nothing on its
own — a resume is a person's act, and for an operation the connector cannot recognise a repeat
of (`idempotency: none`) the reason says that resuming repeats the call (ADR-0024 §3).

A run can be a *rehearsal* (ADR-0030): an outward connector operation is not called, and the
step answers with the recorded response of the most recent real call of the same operation
through the same adapter (`application/query/recordings.py`); it finishes with outcome
`rehearsed`, writes no egress entry, and every ledger entry of the run carries
`rehearsal: true`. Reads, rules, llm and worker steps run as they do in any run.

A run a runner resumes on its claim is written under that claim (#107). Every transaction that
writes the run first asks the queue whether the claim is still the runner's (`Queue.fence`),
and the queue keeps it so until the transaction ends. When another runner has claimed the job
meanwhile — this one was cut off for longer than the lease — the write is refused with
`ClaimLost`, nothing of it lands, and the engine does nothing more for the run. Two runners
therefore never both commit to one run.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from taktus.components.run.application.query.recordings import RecordedResponses
from taktus.components.run.domain.model import (
    INTERRUPTIBLE,
    RESUMABLE,
    BacklogRule,
    Cause,
    Checkpoint,
    CheckRule,
    ClaimLost,
    ConnectorRule,
    ConstantRule,
    LlmWork,
    NoConnector,
    NoWorker,
    ReadyRule,
    RoadmapRule,
    RuleFailed,
    Run,
    RunError,
    RunState,
    StepRun,
    StepState,
    TemplateRule,
    UnknownRun,
    UnsupportedWork,
    VerifyArtifactRule,
    WaitUntil,
    WaitWork,
    Work,
    WorkerWork,
    artifact_references,
    parse_work,
    referenced_values,
    references,
    resolve,
    select,
)
from taktus.components.run.domain.service import budget as budgeting
from taktus.components.run.domain.service import provenance, rules
from taktus.components.run.domain.service.admission import admit, remaining
from taktus.components.run.domain.service.capacity import (
    CapacityDemand,
    CapacityRules,
    admit_capacity,
)
from taktus.components.run.domain.service.rehearsal import REHEARSED
from taktus.components.run.ports import ConnectorPool, ModelPool, WorkerPool
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.connector import (
    CallContext,
    CallFailed,
    ConnectorError,
    EffectReport,
    Operation,
    ResolvedConnector,
    Result,
    idempotency_key,
)
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.model import Calculability, ModelError, PriceTable, Prompt, price
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import ProvenanceStore, Repository, Tenant, UnitOfWork
from taktus.ports.platform import Platform
from taktus.ports.queue import RUN_EXECUTE, Claim, Job, Queue
from taktus.ports.telemetry import Span, Telemetry
from taktus.ports.worker import (
    ArtifactProduced,
    Assignment,
    AssignmentFinished,
    Callback,
    ConsumptionReported,
    Context,
    Frame,
    Limits,
    Outcome,
    StepBoundary,
    StopRequest,
    Task,
    Worker,
    WorkerError,
)
from taktus.shared.v1 import (
    QUANTITIES,
    Artifact,
    Consumption,
    ConsumptionQuantities,
    Digest,
    InputKind,
    LedgerEntry,
    LedgerRefs,
    Method,
    Plan,
    PriceKinds,
    ProvenanceInput,
    Step,
    StepId,
    add_tokens_by_model,
)
from taktus.shared.v1.consumption import MODEL_NAME_PATTERN

SOURCE_REF_LENGTH = 200
"""How much of an operation and its input a provenance source reference keeps (ADR-0021 §4
bounds an input to 384 bytes)."""


@dataclass(frozen=True)
class StartRun:
    plan: Plan
    work: Mapping[StepId, Mapping[str, Any]]
    budget: Limits
    process_version: str
    actor: str
    tenant: Tenant
    stop_after: int | None = None
    inputs: Mapping[str, Any] = field(default_factory=dict)
    """What `$input` references in the work resolve to."""
    margin: float | None = None
    """The share of every limit held back from the first step on (ADR-0005); None takes the
    engine's configured margin."""
    rehearsal: bool = False
    """A rehearsal: no outward connector operation acts (ADR-0030)."""

    @property
    def identity(self) -> str:
        """On whose behalf the run acts: whoever commissioned the plan, else the actor."""
        commissioned = self.plan.commissioned
        return commissioned.by if commissioned is not None else self.actor


@dataclass(frozen=True)
class ResumeRun:
    """Continue a run at its boundary. A halted or escalated run continues where it stopped; a
    submitted run that never started starts. A run still marked as executing is *recovered*:
    the instance that ran it is taken to be gone, the step it was inside is set back to its
    last persisted boundary, and the run continues. The caller asserts that no instance is
    executing the run: the runner's claim on the run's job asserts it (`runner.py`) and fences
    every write against a runner that lost the claim (`claim`); `taktusctl run --resume` is an
    operator's explicit act."""

    run_id: str
    actor: str
    tenant: Tenant
    budget: Limits | None = None  # a changed limit; None keeps the run's
    stop_after: int | None = None
    on_claim: bool = False
    """Resumed because a runner claimed the run's job. A runner can die after the run's last
    state was committed and before it completed the job; the next runner then claims a job
    whose run has already ended. Such a run — finished, escalated, or halted for any cause but
    a stop — is returned as it is, nothing executes, and the runner completes the job: what
    waits for a person stays with the person (issue #73)."""
    claim: Claim | None = None
    """The runner's claim on the run's job. Every write of the run is fenced by it: once
    another runner has claimed the job, the write is refused with `ClaimLost` (#107). None for
    an operator's resume, which no claim stands behind."""


def _ended(run: Run) -> bool:
    """Whether a run has ended in a way a runner's claim does not continue."""
    if run.state in (RunState.FINISHED, RunState.ESCALATED):
        return True
    return run.state is RunState.HALTED and run.cause is not Cause.STOP


@dataclass(frozen=True)
class Trace:
    """What the provenance record of a step needs beyond the step run itself: what the step
    read, and the version the adapter declared — and, for a connector step whose effect left
    the system, the egress entry to write beside `step.finished` (ADR-0022 §4)."""

    inputs: tuple[ProvenanceInput, ...] = ()
    adapter_version: str | None = None
    egress: EffectReport | None = None
    rehearsed: bool = False
    """The step answered from a recording instead of acting outward (ADR-0030)."""


@dataclass(frozen=True)
class EngineOptions:
    step_ceiling_seconds: int = 300
    """How long a running worker step may take to finish after a stop was requested."""
    prices: PriceTable | None = None
    """The price table money is computed at. None: no model is priced, and a budget in a
    currency says so when it is set."""
    margin: float = 0.0
    """The named safety margin a run is held with unless its command names one
    (`TAKTUS_BUDGET_MARGIN`)."""
    seeds: tuple[budgeting.Seed, ...] = budgeting.SEED
    """What calibration starts from for an adapter nothing has measured yet."""
    uncalibrated_margin: float = budgeting.UNCALIBRATED_MARGIN
    """What a worker with no calibration history reserves beyond its estimate (DEC-0034)."""
    capacity: CapacityRules = field(default_factory=CapacityRules)
    """What admission against the platform holds a job to (docs/architecture/platform.md)."""
    unit_memory_bytes: int | None = None
    """The memory limit of the execution unit a worker step starts on this platform; None when
    a worker step starts none here — a worker reached by endpoint runs elsewhere."""


@dataclass(frozen=True)
class _Demand:
    """What a step is estimated to use, or why it cannot be estimated, and the adapter the
    estimate came from."""

    quantities: ConsumptionQuantities | None
    why_not: str | None = None
    adapter: str | None = None
    capabilities: tuple[str, ...] = ()


NOTHING = ConsumptionQuantities()
"""The demand of a rule or a wait on the clock: nothing, and exactly so."""


class RunEngine:
    def __init__(
        self,
        *,
        runs: Repository[Run],
        work: UnitOfWork,
        objects: ObjectStore,
        ledger: Ledger,
        provenance: ProvenanceStore,
        workers: WorkerPool,
        clock: Clock,
        ids: Identifiers,
        telemetry: Telemetry,
        queue: Queue | None = None,
        options: EngineOptions | None = None,
        connectors: ConnectorPool | None = None,
        models: ModelPool | None = None,
        platform: Platform | None = None,
        recordings: RecordedResponses | None = None,
    ) -> None:
        self._runs = runs
        self._work = work
        self._objects = objects
        self._ledger = ledger
        self._provenance = provenance
        self._workers = workers
        self._connectors = connectors
        self._models = models
        self._platform = platform
        self._recordings = recordings or RecordedResponses(runs, work, objects)
        self._clock = clock
        self._ids = ids
        self._telemetry = telemetry
        self._queue = queue
        self._options = options or EngineOptions()
        self._stop_requested: set[str] = set()
        self._inflight: dict[str, tuple[Worker, str]] = {}
        self._observed: dict[str, list[budgeting.Observation]] = {}
        self._limit_halts: set[str] = set()
        self._claim: ContextVar[Claim | None] = ContextVar("claim", default=None)
        """The claim the run executing in this task is written under (#107). Held per task,
        not per run: a runner that lost a claim and claimed the same job again executes the
        run twice for a moment, and only the later claim may write."""

    # --- entry points --------------------------------------------------------------------------

    async def start(self, command: StartRun) -> Run:
        # One trace from the first entry to the last: every entry of this invocation carries it.
        async with self._telemetry.span("run", {"process.version": command.process_version}) as s:
            run = await self._create(command)
            s.set_attribute("run.id", run.id)
            return await self._execute(await self._launch(run), command.stop_after, s)

    async def submit(self, command: StartRun) -> Run:
        """Create the run and hand it to a runner: the run in state `planned` and the job that
        names it land in one transaction, so that a run without a job and a job without a run
        are both impossible. Which runner executes it, and when, is the queue's business."""
        if self._queue is None:
            raise RunError("no queue is wired; submit needs one, start does not")
        async with self._telemetry.span("run.submit", {"process.version": command.process_version}):
            return await self._create(command, enqueue=True)

    async def resume(self, command: ResumeRun) -> Run:
        if command.claim is None:
            return await self._resume(command)
        if self._queue is None:
            raise RunError("a resume under a claim needs the queue that fences it; none is wired")
        token = self._claim.set(command.claim)
        try:
            return await self._resume(command)
        except ClaimLost:
            # The runner that took the job over executes the run; nothing here may.
            self._stop_requested.discard(command.run_id)
            raise
        finally:
            self._claim.reset(token)

    async def _resume(self, command: ResumeRun) -> Run:
        async with self._telemetry.span("run", {"run.id": command.run_id}) as span:
            async with self._work.transaction(command.tenant):
                run = await self._runs.get(command.tenant, command.run_id)
            if run is None:
                raise UnknownRun(command.run_id)
            span.set_attribute("process.version", run.process_version)
            if command.on_claim and _ended(run):
                return run
            if command.budget is not None and command.budget != run.budget:
                run = run.model_copy(update={"budget": command.budget})
                await self._state_budget(run, command.actor)
            if run.state in RESUMABLE:
                run = await self._commit(
                    run.to(RunState.RUNNING), "run.resumed", actor=command.actor
                )
            elif run.state is RunState.PLANNED and run.in_flight() is None:
                run = await self._launch(run)  # submitted, never started: this is its start
            elif run.state in INTERRUPTIBLE:
                run = await self._recover(run, command.actor)
            else:
                raise UnknownRun(f"run {run.id!r} is {run.state} and cannot be resumed")
            return await self._execute(run, command.stop_after, span)

    async def _create(self, command: StartRun, *, enqueue: bool = False) -> Run:
        now = self._clock.now()
        run = Run(
            id=self._ids.new("run"),
            plan_id=command.plan.id,
            process_version=command.process_version,
            tenant=command.tenant,
            identity=command.identity,
            autonomy_level=command.plan.autonomy_level,
            budget=command.budget,
            margin=self._options.margin if command.margin is None else command.margin,
            steps=command.plan.steps,
            work=command.work,
            inputs=dict(command.inputs),
            rehearsal=command.rehearsal,
            created_at=now,
            updated_at=now,
        )
        self._check_executable(run)
        job = None
        if enqueue:
            job = Job(id=self._ids.new("job"), kind=RUN_EXECUTE, payload={"run_id": run.id})
        run = await self._commit(run, "run.created", actor=command.actor, enqueue=job)
        await self._state_budget(run, command.actor)
        return run

    async def _state_budget(self, run: Run, actor: str | None) -> None:
        """Say what the budget can promise when it is set, not afterwards (principle 8): the
        budget, the margin, the line the run is held to, how each limited kind is held and
        why, the price table money is computed at, and the margin a worker without history
        reserves — with the statement, where an operator set it below the floor, that it is
        (DEC-0047) — one document, its digest in the
        ledger as `budget.set`, so that money stays recomputable from the ledger."""
        models: list[tuple[str, Calculability, bool]] = []
        worker_steps: list[str] = []
        for step in run.steps:
            work = parse_work(step, run.work.get(step.id), run.inputs)
            if isinstance(work, WorkerWork):
                worker_steps.append(step.id)
            if not isinstance(work, LlmWork) or self._models is None:
                continue
            resolved = await self._models.resolve(work.purpose)
            if resolved is None or any(m[0] == resolved.adapter for m in models):
                continue
            prices = self._options.prices
            priced = prices is not None and (resolved.version or "") in prices.prices
            models.append((resolved.adapter, resolved.model.calculability(), priced))
        by_assignment = (
            [f"the worker step(s) {', '.join(worker_steps)}"]
            if worker_steps and run.budget.currency is not None
            else []
        )
        promises = budgeting.promise(run.budget, models, by_assignment)
        table = self._options.prices
        table_digest = None
        if table is not None:
            table_digest = await self._objects.put(_canonical(table.document()))
        statement = {
            "budget": run.budget.document(),
            "margin": run.margin,
            "held": budgeting.held(run.budget, run.margin).document(),
            "promises": [p.document() for p in promises],
            "models": [
                {"adapter": adapter, "declaration": c.document(), "priced": priced}
                for adapter, c, priced in models
            ],
            "price_table": None
            if table is None
            else {"version": table.version, "digest": table_digest},
            "uncalibrated_margin": {
                "value": self._options.uncalibrated_margin,
                "floor": budgeting.MARGIN_FLOOR,
                "below_floor": budgeting.below_floor(self._options.uncalibrated_margin),
            },
        }
        digest = await self._objects.put(_canonical(statement))
        async with self._work.transaction(run.tenant):
            await self._fence(run)
            await self._record(run, "budget.set", actor=actor, digest=digest)

    async def _launch(self, run: Run) -> Run:
        run = await self._commit(run.to(RunState.ADMITTED))
        return await self._commit(run.to(RunState.RUNNING), "run.started")

    async def _recover(self, run: Run, actor: str) -> Run:
        """The instance executing this run stopped without halting it. The step it was inside
        goes back to its last persisted boundary — the worker's checkpoint if one arrived, its
        start otherwise — and is admitted again; steps before it are kept as they are. That is
        the "at most one step of work is lost" of ADR-0005, made true across a restart."""
        interrupted = run.in_flight()
        if interrupted is not None:
            interrupted = interrupted.to(
                StepState.STOPPED,
                reason="the instance stopped while this step was in flight",
                finished_at=self._clock.now(),
            )
            run = run.with_step_run(interrupted)
        if run.state is RunState.PLANNED:
            run = run.to(RunState.ADMITTED)
        if run.state is RunState.ADMITTED:
            run = run.to(RunState.RUNNING)
        return await self._commit(run, "run.recovered", step=interrupted, actor=actor)

    async def request_stop(self, run_id: str) -> None:
        """Takes effect at the next step boundary. A running worker step is asked to stop as
        well and may finish up to the ceiling."""
        self._stop_requested.add(run_id)
        inflight = self._inflight.get(run_id)
        if inflight is not None:
            worker, assignment_id = inflight
            await worker.stop(
                assignment_id,
                StopRequest(
                    reason="stop requested", ceiling_seconds=self._options.step_ceiling_seconds
                ),
            )

    # --- the loop ------------------------------------------------------------------------------

    def _check_executable(self, run: Run) -> None:
        """Every step has an executor and every `$from` names a dependency, before anything
        runs: a run never fails in the middle for a reason known at the start."""
        ancestors: dict[StepId, set[StepId]] = {}
        for step in run.steps:
            ancestors[step.id] = set()
            for dependency in step.dependencies:
                ancestors[step.id] |= {dependency, *ancestors[dependency]}
            work = parse_work(step, run.work.get(step.id), run.inputs)
            for value in referenced_values(work):
                for referenced in references(value):
                    if referenced not in ancestors[step.id]:
                        raise UnsupportedWork(
                            step.id, f"$from {referenced!r} is not a dependency of this step"
                        )

    async def _execute(self, run: Run, stop_after: int | None, span: Span) -> Run:
        try:
            self._observed[run.id] = await self._observations(run.tenant)
            return await self._steps(run, stop_after, span)
        finally:
            self._observed.pop(run.id, None)
            self._limit_halts.discard(run.id)

    async def _steps(self, run: Run, stop_after: int | None, span: Span) -> Run:
        refused = await self._platform_refuses(None)
        if refused is not None:
            return await self._end(run, RunState.HALTED, Cause.LIMIT, refused, span)
        completed_now = 0
        while (step_run := run.next_step_run()) is not None:
            step = run.step(step_run.step_id)
            run, step_run = await self._execute_step(run, step, step_run)
            if step_run.state is StepState.REJECTED:
                cause = Cause.NO_ESTIMATE if step_run.estimate is None else Cause.LIMIT
                return await self._end(run, RunState.HALTED, cause, step_run.reason, span)
            if step_run.state is StepState.FAILED:
                return await self._end(
                    run, RunState.ESCALATED, Cause.FAILURE, step_run.reason, span
                )
            if step_run.state is StepState.STOPPED:
                cause = Cause.LIMIT if run.id in self._limit_halts else Cause.STOP
                self._limit_halts.discard(run.id)
                return await self._end(run, RunState.HALTED, cause, step_run.reason, span)
            completed_now += 1
            # The boundary: a stop requested meanwhile takes effect here.
            if run.id in self._stop_requested or (
                stop_after is not None and completed_now >= stop_after
            ):
                return await self._end(
                    run, RunState.HALTED, Cause.STOP, "stop requested at the boundary", span
                )
        return await self._end(run, RunState.FINISHED, None, None, span)

    async def _end(
        self, run: Run, state: RunState, cause: Cause | None, reason: str | None, span: Span
    ) -> Run:
        self._stop_requested.discard(run.id)
        span.set_attribute("run.state", state)
        if cause is not None:
            span.set_attribute("run.cause", cause)
        outcome = "succeeded" if state is RunState.FINISHED else str(cause)
        return await self._commit(run.to(state, cause, reason), f"run.{state}", outcome=outcome)

    async def _execute_step(self, run: Run, step: Step, step_run: StepRun) -> tuple[Run, StepRun]:
        async with self._telemetry.span(
            "step", {"run.id": run.id, "step.id": step.id, "step.method": step.method}
        ) as span:
            work = parse_work(step, run.work.get(step.id), run.inputs)
            if isinstance(work, WorkerWork):
                return await self._worker_step(run, step, step_run, work, span)
            return await self._local_step(run, step, step_run, work, span)

    # --- rule and wait steps ---------------------------------------------------------------------

    async def _local_step(
        self, run: Run, step: Step, step_run: StepRun, work: Work, span: Span
    ) -> tuple[Run, StepRun]:
        # A rule, a wait or a connector call demands nothing of any limit that could be
        # estimated: admission is a formality, recorded so that every step run reads the same
        # in the ledger. A retry after a failure the connector called not retryable is a new
        # attempt with a new idempotency key; every other resume continues the attempt.
        attempt = step_run.attempt
        if step_run.state is StepState.FAILED and not step_run.retryable:
            attempt += 1
        try:
            demand = await self._demand(run, step, work)
        except RuleFailed as failure:
            return await self._failed_before(run, step_run, span, str(failure), None, None)
        except _StepFailed as failure:
            return await self._failed_before(
                run, step_run, span, failure.reason, failure.adapter, failure.retryable
            )
        run, step_run, admitted = await self._admit(
            run, step, step_run, demand, span, retryable=None, attempt=attempt
        )
        if not admitted:
            return run, step_run
        step_run = step_run.to(StepState.RUNNING, started_at=self._clock.now())
        run = await self._commit(run.with_step_run(step_run), "step.started", step=step_run)
        trace = Trace()
        consumption: Consumption | None = None
        try:
            result_digest: str | None = None
            artifacts: tuple[Artifact, ...] = ()
            if isinstance(work, WaitWork):
                if work.until is None:
                    await self._clock.sleep(work.seconds)
                else:
                    step_run, consumption = await self._wait_until(run, step_run, work.until, span)
            else:
                value, trace, consumption, adapter = await self._evaluate(run, step_run, work, span)
                if adapter is not None:
                    step_run = step_run.model_copy(update={"adapter": adapter})
                content = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
                result_digest = await self._objects.put(content)
                artifacts = (
                    Artifact(
                        id="result",
                        kind="result",
                        digest=result_digest,
                        media_type="application/json",
                        size_bytes=len(content),
                        created_at=self._clock.now(),
                    ),
                )
        except RuleFailed as failure:
            span.record_failure("rule failed")
            step_run = step_run.to(
                StepState.FAILED, reason=str(failure), finished_at=self._clock.now()
            )
            run = await self._commit(
                run.with_step_run(step_run), "step.finished", step=step_run, outcome="failed"
            )
            return run, step_run
        except _StepFailed as failure:
            span.record_failure(failure.outcome)
            step_run = step_run.to(
                StepState.FAILED,
                adapter=failure.adapter,
                consumption=failure.consumption,
                reason=failure.reason,
                retryable=failure.retryable,
                finished_at=self._clock.now(),
            )
            run = await self._commit(
                run.with_step_run(step_run), "step.finished", step=step_run, outcome="failed"
            )
            return run, step_run
        now = self._clock.now()
        checkpoint = Checkpoint(
            ref=f"ckpt/{run.id}/{step.id}",
            step_id=step.id,
            taken_at=now,
            artifact_ids=tuple(a.id for a in artifacts),
            result_digest=result_digest,
        )
        step_run = step_run.to(
            StepState.SUCCEEDED,
            artifacts=artifacts,
            checkpoint=checkpoint,
            consumption=consumption,
            finished_at=now,
        )
        run = await self._commit(
            run.with_step_run(step_run),
            "step.finished",
            step=step_run,
            outcome=REHEARSED if trace.rehearsed else "succeeded",
            trace=trace,
        )
        _measured(span, step_run)
        return run, step_run

    async def _evaluate(
        self, run: Run, step_run: StepRun, work: Work, span: Span
    ) -> tuple[Any, Trace, Consumption | None, str | None]:
        """The rule's value, what the rule read to produce it, what it consumed, and the
        adapter that served it where one did."""
        if isinstance(work, ConstantRule):
            return rules.constant(work), Trace(), None, None
        if isinstance(work, VerifyArtifactRule):
            producer = run.step_run(work.step)
            artifact = producer.artifact(work.artifact)
            content = None if artifact is None else await self._objects.get(artifact.digest)
            observed_at = self._clock.now()
            value = rules.verify_artifact(work, artifact, content)
            if artifact is None:  # unreachable: the rule refuses a missing artifact
                raise RuleFailed(f"step {work.step!r} produced no artifact {work.artifact!r}")
            verified = ProvenanceInput(
                kind=InputKind.ARTIFACT,
                run_id=run.id,
                step_id=producer.step_id,
                artifact_id=artifact.id,
                digest=artifact.digest,
                observed_at=observed_at,
            )
            return value, Trace(inputs=(verified,)), None, None
        if isinstance(work, CheckRule):
            values, read = await self._resolved(
                run, [condition.value for condition in work.conditions]
            )
            return rules.check(work, values), Trace(inputs=read), None, None
        if isinstance(work, ReadyRule):
            (issue, records, issues), read = await self._resolved(
                run, [work.issue, work.open_records, work.open_issues]
            )
            return rules.ready(work, issue, records, issues), Trace(inputs=read), None, None
        if isinstance(work, BacklogRule):
            (issues, records), read = await self._resolved(run, [work.issues, work.open_records])
            return rules.backlog(work, issues, records), Trace(inputs=read), None, None
        if isinstance(work, RoadmapRule):
            (text, issues), read = await self._resolved(run, [work.roadmap, work.issues])
            return rules.roadmap(work, text, issues), Trace(inputs=read), None, None
        if isinstance(work, TemplateRule):
            (values,), read = await self._resolved(run, [work.values])
            return rules.template(work, values), Trace(inputs=read), None, None
        if isinstance(work, ConnectorRule):
            return await self._connector_call(run, step_run, work, span)
        if isinstance(work, LlmWork):
            return await self._llm_step(run, step_run, work, span)
        raise UnsupportedWork(step_run.step_id, f"no evaluator for {type(work).__name__}")

    # --- estimate and admission -----------------------------------------------------------------

    def _line(self, run: Run) -> Limits:
        """The line the run is held to: its budget less its margin."""
        return budgeting.held(run.budget, run.margin)

    async def _demand(self, run: Run, step: Step, work: Work) -> _Demand:
        """What a local step is estimated to use before it runs — or why it cannot be. A step
        whose adapter is not configured fails here, as it would when called, and its reason
        says which; a step whose adapter cannot estimate is refused by the caller."""
        if isinstance(work, WaitWork) and work.until is not None:
            resolved = await self._connector(step.id, work.until.capability)
            operation = resolved.declaration.operation(work.until.operation)
            if operation is None:
                raise _StepFailed(
                    reason=str(NoConnector(step.id, work.until.operation)),
                    retryable=True,
                    consumption=None,
                    adapter=resolved.adapter,
                    outcome="no connector",
                )
            if operation.demand is None:
                return _Demand(None, _undeclared(operation.name), resolved.adapter)
            calls = int(work.until.timeout_seconds // work.until.poll_seconds) + 1
            return _Demand(_times(operation.demand.document(), calls), adapter=resolved.adapter)
        if isinstance(work, ConnectorRule):
            resolved = await self._connector(step.id, work.capability)
            operation = resolved.declaration.operation(work.operation)
            if operation is None:
                raise _StepFailed(
                    reason=str(NoConnector(step.id, work.operation)),
                    retryable=True,
                    consumption=None,
                    adapter=resolved.adapter,
                    outcome="no connector",
                )
            if operation.demand is None:
                return _Demand(None, _undeclared(operation.name), resolved.adapter)
            return _Demand(_times(operation.demand.document(), 1), adapter=resolved.adapter)
        if isinstance(work, LlmWork):
            return await self._llm_demand(run, step, work)
        return _Demand(NOTHING)

    async def _llm_demand(self, run: Run, step: Step, work: LlmWork) -> _Demand:
        """Input counted before the call, output bounded by the limit the step sets; money at
        the price table, with every input token priced as the dearest input kind, because
        whether it will be read from a cache is not knowable before the call."""
        resolved = None if self._models is None else await self._models.resolve(work.purpose)
        if resolved is None:
            raise _StepFailed(
                reason=f"no model is configured for the purpose {work.purpose!r} "
                "(TAKTUS_MODEL_ENDPOINT, TAKTUS_MODEL_NAME)",
                retryable=True,
                consumption=None,
                adapter=None,
                outcome="no model",
            )
        (values,), _ = await self._resolved(run, [work.values])
        rendered = rules.template(
            TemplateRule(rule="template", text=work.prompt, values=work.values), values
        )
        prompt = Prompt(system=work.system, user=rendered, max_output_tokens=work.max_output_tokens)
        declaration = resolved.model.calculability()
        counted = await resolved.model.count(prompt)
        if counted is None:
            return _Demand(
                None,
                f"{resolved.adapter} cannot count a prompt's input before the call "
                f"(input_count {declaration.input_count}), so the step has no estimate",
                resolved.adapter,
            )
        demand: dict[str, Any] = {"tokens_in": counted, "tokens_out": work.max_output_tokens}
        model = resolved.version or ""
        if re.fullmatch(MODEL_NAME_PATTERN, model):
            demand["tokens_by_model"] = {
                model: PriceKinds(input=counted, output=work.max_output_tokens)
            }
        table = self._options.prices
        if run.budget.currency is not None:
            if table is None or model not in table.prices:
                return _Demand(
                    None,
                    f"the budget limits money and the price table has no price for {model!r}: "
                    "the step's cost cannot be estimated",
                    resolved.adapter,
                )
            prices = table.prices[model]
            dearest = max(prices.get("input", 0.0), prices.get("cache_write", 0.0))
            bound = price(
                {model: PriceKinds(input=counted, output=work.max_output_tokens)},
                table.model_copy(update={"prices": {model: {**prices, "input": dearest}}}),
            )
            if not bound.complete:
                return _Demand(
                    None,
                    f"the price table prices {model!r} without "
                    + ", ".join(bound.unpriced)
                    + ": the step's cost cannot be estimated",
                    resolved.adapter,
                )
            demand["currency"] = {table.currency: bound.amount}
        return _Demand(ConsumptionQuantities.model_validate(demand), adapter=resolved.adapter)

    async def _admit(
        self,
        run: Run,
        step: Step,
        step_run: StepRun,
        demand: _Demand,
        span: Span,
        **changes: Any,
    ) -> tuple[Run, StepRun, bool]:
        """Reserve the step's demand against what remains of the line the run is held to, or
        refuse it: for want of an estimate, or because the reservation does not fit. What is
        reserved is the estimate scaled by the measured error of its adapter; the ledger
        carries the estimate on `step.admitted` and, where the two differ, the reservation on
        `step.reserved`."""
        adapter = demand.adapter or step_run.adapter
        if demand.quantities is None:
            span.record_failure("no estimate")
            step_run = step_run.to(
                StepState.REJECTED,
                adapter=adapter,
                estimate=None,
                reservation=None,
                reason="refused, not admitted: " + (demand.why_not or "no estimate"),
                **changes,
            )
            run = await self._commit(
                run.with_step_run(step_run), "step.rejected", step=step_run, outcome="no_estimate"
            )
            return run, step_run, False
        scale, _ = (
            ({}, "")
            if adapter is None
            else budgeting.scale_for(
                adapter,
                step.method,
                demand.capabilities,
                self._observed.get(run.id, []),
                self._options.seeds,
                self._options.uncalibrated_margin,
                budgeting.models_of(demand.quantities),
            )
        )
        reservation = budgeting.reserve(demand.quantities, scale)
        line = self._line(run)
        verdict = admit(reservation, remaining(line, _without(run, step_run.step_id)), line)
        refused = (
            await self._platform_refuses(self._options.unit_memory_bytes)
            if step.method is Method.WORKER and verdict.fits
            else None
        )
        if refused is not None:
            span.record_failure("rejected by the platform")
            step_run = step_run.to(
                StepState.REJECTED,
                adapter=adapter,
                estimate=demand.quantities,
                reservation=reservation,
                reason=refused,
                **changes,
            )
            run = await self._commit(
                run.with_step_run(step_run),
                "step.rejected",
                step=step_run,
                outcome="rejected_by_capacity",
            )
            return run, step_run, False
        if not verdict.fits:
            span.record_failure("rejected by admission control")
            step_run = step_run.to(
                StepState.REJECTED,
                adapter=adapter,
                estimate=demand.quantities,
                reservation=reservation,
                reason="does not fit the remaining budget: " + "; ".join(verdict.findings),
                **changes,
            )
            run = await self._commit(
                run.with_step_run(step_run),
                "step.rejected",
                step=step_run,
                outcome="rejected_by_admission",
            )
            return run, step_run, False
        step_run = step_run.to(
            StepState.ADMITTED,
            adapter=adapter,
            estimate=demand.quantities,
            reservation=reservation,
            reason=None,
            **changes,
        )
        run = await self._commit(run.with_step_run(step_run), "step.admitted", step=step_run)
        if reservation != demand.quantities:
            run = await self._commit(run, "step.reserved", step=step_run, outcome="calibrated")
        return run, step_run, True

    async def _platform_refuses(self, memory_bytes: int | None) -> str | None:
        """Why the platform cannot hold what is about to start, or None: memory for the unit a
        worker step starts here, and storage above its refusal share for anything at all. What
        the platform could not observe refuses nothing (docs/architecture/platform.md)."""
        if self._platform is None:
            return None
        verdict = admit_capacity(
            await self._platform.observe(),
            CapacityDemand(memory_bytes=memory_bytes),
            self._options.capacity,
        )
        if verdict.fits:
            return None
        return "the platform cannot hold it: " + "; ".join(verdict.findings)

    async def _failed_before(
        self,
        run: Run,
        step_run: StepRun,
        span: Span,
        reason: str,
        adapter: str | None,
        retryable: bool | None,
    ) -> tuple[Run, StepRun]:
        """A step that failed while it was being estimated — its adapter is not configured,
        a reference in its prompt does not resolve — fails at its boundary like one that
        failed while running; nothing was admitted and nothing started."""
        span.record_failure("failed before admission")
        step_run = step_run.to(
            StepState.FAILED,
            adapter=adapter,
            reason=reason,
            retryable=retryable,
            finished_at=self._clock.now(),
        )
        run = await self._commit(
            run.with_step_run(step_run), "step.finished", step=step_run, outcome="failed"
        )
        return run, step_run

    async def _observations(self, tenant: Tenant) -> list[budgeting.Observation]:
        """Every pair of estimate and actual in the tenant's ledger, oldest first: a step's
        `step.admitted` and the `step.finished` of the same step after it. The calibration
        is a statistic over these, and so reproducible from the ledger (ADR-0005 §4)."""
        estimates: dict[tuple[str, str], Consumption] = {}
        observed: list[budgeting.Observation] = []
        async with self._work.transaction(tenant):
            entries = await self._ledger.entries(tenant)
        for entry in entries:
            run_id, step_id = entry.refs.run_id, entry.refs.step_id
            if run_id is None or step_id is None or entry.rehearsal:
                continue  # a rehearsal replays recorded answers: it measures no adapter
            if entry.kind == "step.admitted" and entry.consumption is not None:
                estimates[(run_id, step_id)] = entry.consumption
            elif entry.kind == "step.finished" and entry.outcome == "stopped":
                # A stopped step used part of what it was estimated for: its partial actual
                # against its whole estimate would read as an overestimate. It measures nothing.
                estimates.pop((run_id, step_id), None)
            elif entry.kind == "step.finished" and entry.consumption is not None:
                estimate = estimates.pop((run_id, step_id), None)
                if estimate is None or entry.adapter is None or entry.method is None:
                    continue
                observed.append(
                    budgeting.Observation(
                        adapter=entry.adapter,
                        method=entry.method,
                        estimate=estimate,
                        actual=entry.consumption,
                    )
                )
        return observed

    # --- llm steps ------------------------------------------------------------------------------

    async def _llm_step(
        self, run: Run, step_run: StepRun, work: LlmWork, span: Span
    ) -> tuple[Any, Trace, Consumption | None, str]:
        """One completion from the model configured for the purpose. The text that leaves the
        step is the model's, once it passes the pattern; the tokens are counted; the model
        that answered goes into the provenance as the adapter's version, because a variable
        method is reproducible only at a pinned one."""
        resolved = None if self._models is None else await self._models.resolve(work.purpose)
        if resolved is None:
            raise _StepFailed(
                reason=f"no model is configured for the purpose {work.purpose!r} "
                "(TAKTUS_MODEL_ENDPOINT, TAKTUS_MODEL_NAME)",
                retryable=True,
                consumption=None,
                adapter=None,
                outcome="no model",
            )
        (values,), read = await self._resolved(run, [work.values])
        rendered = rules.template(
            TemplateRule(rule="template", text=work.prompt, values=work.values), values
        )
        prompt = Prompt(system=work.system, user=rendered, max_output_tokens=work.max_output_tokens)
        span.set_attribute("adapter", resolved.adapter)
        attributes: dict[str, str | int] = {
            "run.id": run.id,
            "step.id": step_run.step_id,
            "adapter": resolved.adapter,
            "model.purpose": work.purpose,
        }
        try:
            async with self._telemetry.span("model.complete", attributes) as call:
                completion = await resolved.model.complete(prompt)
                call.set_attribute("model.name", completion.model)
                call.set_attribute("model.finish", completion.finish)
        except ModelError as error:
            raise _StepFailed(
                reason=str(error),
                retryable=True,
                consumption=None,
                adapter=resolved.adapter,
                outcome="model unavailable",
            ) from error
        consumption = Consumption(
            tokens_in=completion.tokens_in,
            tokens_out=completion.tokens_out,
            tokens_by_model=None
            if completion.by_kind is None or not re.fullmatch(MODEL_NAME_PATTERN, completion.model)
            else {completion.model: completion.by_kind},
        )
        if completion.finish == "length":
            raise _StepFailed(
                reason=f"the model stopped at the output limit of {work.max_output_tokens} "
                "tokens; the answer is cut off and does not leave the step",
                retryable=True,
                consumption=consumption,
                adapter=resolved.adapter,
                outcome="answer cut off",
            )
        if work.pattern is not None and re.search(work.pattern, completion.text) is None:
            raise _StepFailed(
                reason=f"the model's answer does not match {work.pattern!r}; nothing leaves the "
                "step (a variable method proposes, the check decides)",
                retryable=True,
                consumption=consumption,
                adapter=resolved.adapter,
                outcome="answer failed the check",
            )
        trace = Trace(inputs=read, adapter_version=completion.model)
        return (
            {"text": completion.text, "model": completion.model},
            trace,
            consumption,
            resolved.adapter,
        )

    # --- connector steps ------------------------------------------------------------------------

    async def _connector(self, step_id: StepId, capability: str) -> ResolvedConnector:
        """The connector configured for the capability. None configured is a failed step, not
        an exception: the run escalates at the boundary with the reason, and a resume after
        the configuration changed retries it (the same as a model that is not configured)."""
        resolved = None
        if self._connectors is not None:
            resolved = await self._connectors.resolve(capability)
        if resolved is None:
            raise _StepFailed(
                reason=str(NoConnector(step_id, capability)),
                retryable=True,
                consumption=None,
                adapter=None,
                outcome="no connector",
            )
        return resolved

    async def _connector_call(
        self, run: Run, step_run: StepRun, work: ConnectorRule, span: Span
    ) -> tuple[Any, Trace, Consumption | None, str]:
        """One operation, called once for this attempt of the step. What comes back is the
        result as the contract shapes it — output, effect, consumption — and, for an outward
        effect, the egress entry the commit writes beside `step.finished`."""
        resolved = await self._connector(step_run.step_id, work.capability)
        operation = resolved.declaration.operation(work.operation)
        if operation is None:
            raise _StepFailed(
                reason=str(NoConnector(step_run.step_id, work.operation)),
                retryable=True,
                consumption=None,
                adapter=resolved.adapter,
                outcome="no connector",
            )
        (input,), read = await self._resolved(run, [work.input])
        if work.expect and operation.outward:
            raise UnsupportedWork(
                step_run.step_id, "only a reading carries an expectation; a write acts once"
            )
        span.set_attribute("adapter", resolved.adapter)
        if run.rehearsal and operation.outward:
            return await self._rehearsed(run, resolved, operation, read)
        result = await self._call(run, step_run, resolved, operation, input, work.credentials, span)
        document = result.document()
        unmet = [why for e in work.expect if (why := rules.unmet(e, document["output"]))]
        if unmet:
            # The reading fails its own step, so that a resume reads again: the state outside
            # may be what was expected by then (issue #31).
            raise _StepFailed(
                reason=f"{operation.name} did not show what the step expects: "
                + "; ".join(unmet)
                + ". A resume reads it again",
                retryable=True,
                consumption=result.consumption,
                adapter=resolved.adapter,
                outcome="reading not as expected",
            )
        inputs = list(read)
        if not operation.outward:
            inputs.append(self._source(operation, input, document["output"]))
        egress = result.effect if operation.outward else None
        trace = Trace(inputs=tuple(inputs), adapter_version=resolved.version, egress=egress)
        return document, trace, result.consumption, resolved.adapter

    # --- rehearsal (ADR-0030) ------------------------------------------------------------------

    async def _rehearsed(
        self,
        run: Run,
        resolved: ResolvedConnector,
        operation: Operation,
        read: tuple[ProvenanceInput, ...],
    ) -> tuple[Any, Trace, Consumption | None, str]:
        """An outward operation in a rehearsal: nothing is sent. The step answers with the
        recorded response of the most recent real call of the operation through the adapter,
        reads it as that run's result, and consumes nothing. Without a recording the step
        fails: the process cannot be rehearsed past it."""
        found = await self._recordings.response(run.tenant, resolved.adapter, operation.name)
        if found is None:
            raise _StepFailed(
                reason=f"rehearsal: no recorded response for {operation.name} through "
                f"{resolved.adapter} — it has never been called for real on this instance",
                retryable=False,
                consumption=None,
                adapter=resolved.adapter,
                outcome="no recording",
            )
        recording, document = found
        recorded = ProvenanceInput(
            kind=InputKind.RESULT,
            run_id=recording.run_id,
            step_id=recording.step_id,
            digest=recording.digest,
            observed_at=self._clock.now(),
        )
        replayed = {
            **document,
            "rehearsed_from": {"run_id": recording.run_id, "step_id": recording.step_id},
        }
        trace = Trace(inputs=(*read, recorded), adapter_version=resolved.version, rehearsed=True)
        return replayed, trace, None, resolved.adapter

    # --- end of rehearsal ----------------------------------------------------------------------

    async def _call(
        self,
        run: Run,
        step_run: StepRun,
        resolved: ResolvedConnector,
        operation: Operation,
        input: Mapping[str, Any],
        credentials: tuple[Any, ...],
        span: Span,
    ) -> Result:
        context = CallContext(
            tenant=run.tenant,
            identity=run.identity,
            run_id=run.id,
            step_id=step_run.step_id,
            attempt=step_run.attempt,
            idempotency_key=idempotency_key(run.id, step_run.step_id, step_run.attempt),
            credentials=credentials,
            autonomy_level=run.autonomy_level,
        )
        attributes: dict[str, str | int] = {
            "run.id": run.id,
            "step.id": step_run.step_id,
            "adapter": resolved.adapter,
            "connector.operation": operation.name,
            "connector.effect": str(operation.effect),
            "connector.attempt": step_run.attempt,
        }
        try:
            async with self._telemetry.span("connector.call", attributes) as call:
                result = await resolved.connector.call(operation.name, context, input)
                if result.effect.replayed is not None:
                    call.set_attribute("connector.replayed", result.effect.replayed)
        except CallFailed as failed:
            error = failed.error
            reason = f"{operation.name} failed: {error.cause} — {error.detail}"
            if error.effect == "unknown" and not operation.repeatable:
                reason += (
                    "; the operation cannot recognise a repeat (idempotency: none), so the run "
                    "did not retry it. Check the target system whether the effect happened "
                    "before resuming: resuming repeats the call"
                )
            raise _StepFailed(
                reason=reason,
                retryable=error.retryable,
                consumption=error.consumption,
                adapter=resolved.adapter,
                outcome="connector failed",
            ) from failed
        except ConnectorError as broken:
            # The connector did not answer, or answered outside the contract: whether the
            # call acted is unknown unless the operation recognises a repeat.
            reason = f"{operation.name}: {broken}"
            if operation.outward and not operation.repeatable:
                reason += (
                    "; the operation cannot recognise a repeat (idempotency: none), so the run "
                    "did not retry it. Check the target system whether the effect happened "
                    "before resuming: resuming repeats the call"
                )
            raise _StepFailed(
                reason=reason,
                retryable=not operation.outward or operation.repeatable,
                consumption=None,
                adapter=resolved.adapter,
                outcome="connector unreachable",
            ) from broken
        if result.effect.kind != operation.effect:
            raise _StepFailed(
                reason=f"{operation.name} reported effect {result.effect.kind}, declared "
                f"{operation.effect}: the connector broke its contract",
                retryable=False,
                consumption=result.consumption,
                adapter=resolved.adapter,
                outcome="connector broke the contract",
            )
        return result

    def _source(
        self, operation: Operation, input: Mapping[str, Any], output: Any
    ) -> ProvenanceInput:
        """A read through a connector is an external source the step read, with the digest of
        what it answered: the moment and the content, so that "since when" stays answerable."""
        canonical = json.dumps(output, ensure_ascii=False, sort_keys=True).encode("utf-8")
        given = json.dumps(input, ensure_ascii=False, sort_keys=True)
        ref = f"{operation.name} {given}"
        return ProvenanceInput(
            kind=InputKind.SOURCE,
            capability=operation.capability,
            ref=ref if len(ref) <= SOURCE_REF_LENGTH else ref[: SOURCE_REF_LENGTH - 1] + "…",
            digest=_digest(canonical),
            observed_at=self._clock.now(),
        )

    async def _wait_until(
        self, run: Run, step_run: StepRun, until: WaitUntil, span: Span
    ) -> tuple[StepRun, Consumption | None]:
        """Poll a read operation until the selected part of its output is expected, within
        the timeout. A wait produces no result (ADR-0018); what it consumed is counted."""
        resolved = await self._connector(step_run.step_id, until.capability)
        operation = resolved.declaration.operation(until.operation)
        if operation is None:
            raise _StepFailed(
                reason=str(NoConnector(step_run.step_id, until.operation)),
                retryable=True,
                consumption=None,
                adapter=resolved.adapter,
                outcome="no connector",
            )
        if operation.outward:
            raise UnsupportedWork(step_run.step_id, "a wait reads an external state, never writes")
        (input,), _ = await self._resolved(run, [until.input])
        step_run = step_run.model_copy(update={"adapter": resolved.adapter})
        used: dict[str, Any] = {}
        waited = 0.0
        while True:
            result = await self._call(
                run, step_run, resolved, operation, input, until.credentials, span
            )
            _accumulate(used, result.consumption)
            try:
                observed = select(result.output, until.select)
            except KeyError:
                observed = None
            if observed in until.expect:
                span.set_attribute("wait.observed", str(observed))
                return step_run, _consumption(used)
            if waited >= until.timeout_seconds:
                raise _StepFailed(
                    reason=f"waited {waited:.0f}s for {until.operation} {until.select} to be one "
                    f"of {list(until.expect)}; last observed {observed!r}",
                    retryable=True,
                    consumption=_consumption(used),
                    adapter=resolved.adapter,
                    outcome="wait timed out",
                )
            await self._clock.sleep(until.poll_seconds)
            waited += until.poll_seconds

    async def _resolved(
        self, run: Run, values: list[Any]
    ) -> tuple[list[Any], tuple[ProvenanceInput, ...]]:
        """The values with every `$from` reference replaced, and what was read to do so."""
        referenced: set[StepId] = set()
        artifacts: set[tuple[StepId, str]] = set()
        for value in values:
            referenced |= references(value)
            artifacts |= artifact_references(value)
        results, read = await self._results(run, referenced, artifacts)
        contents: dict[str, Any] = {}
        for step_id, artifact_id in artifacts:
            contents[f"{step_id}/{artifact_id}"] = await self._artifact_content(
                run, step_id, artifact_id
            )
        try:
            return [resolve(value, results, contents) for value in values], read
        except KeyError as missing:
            raise RuleFailed(f"reference to {missing.args[0]!r} cannot be resolved") from missing

    async def _artifact_content(self, run: Run, step_id: StepId, artifact_id: str) -> Any:
        artifact = run.step_run(step_id).artifact(artifact_id)
        if artifact is None:
            raise RuleFailed(f"step {step_id!r} produced no artifact {artifact_id!r}")
        content = await self._objects.get(artifact.digest)
        if content is None:
            raise RuleFailed(f"the content of artifact {artifact_id!r} is not available")
        text = content.decode("utf-8", errors="replace")
        if (artifact.media_type or "").startswith("application/json"):
            try:
                return json.loads(text)
            except ValueError as error:
                raise RuleFailed(f"artifact {artifact_id!r} is not the JSON it claims") from error
        return text

    # --- worker steps ----------------------------------------------------------------------------

    async def _worker_step(
        self, run: Run, step: Step, step_run: StepRun, work: WorkerWork, span: Span
    ) -> tuple[Run, StepRun]:
        resolved = await self._workers.resolve(step.required_capabilities)
        if resolved is None:
            # No configured worker offers the capabilities: a failed step, the run escalates
            # at the boundary, and a resume after the configuration changed retries it.
            span.record_failure("no worker")
            step_run = step_run.to(
                StepState.FAILED,
                reason=str(NoWorker(step.id, step.required_capabilities)),
                retryable=True,
                finished_at=self._clock.now(),
            )
            run = await self._commit(
                run.with_step_run(step_run), "step.finished", step=step_run, outcome="failed"
            )
            return run, step_run
        adapter, worker = resolved.adapter, resolved.worker
        span.set_attribute("adapter", adapter)
        resuming = step_run.checkpoint if step_run.state is StepState.STOPPED else None
        left = remaining(self._line(run), run.consumed())
        (inputs,), read = await self._resolved(run, [work.task.inputs])
        trace = Trace(inputs=read, adapter_version=resolved.version)
        assignment = Assignment(
            assignment_id=self._ids.new("asg"),
            task=Task(
                goal=work.task.goal,
                acceptance=work.task.acceptance,
                inputs=inputs,
            ),
            credentials=work.credentials or None,
            context=Context(
                workspace=work.workspace,
                checkpoint_ref=None if resuming is None else resuming.ref,
            ),
            frame=Frame(
                autonomy_level=run.autonomy_level,
                allowed_tools=step.required_capabilities,
                allowed_hosts=work.allowed_hosts,
                max_steps=work.max_steps,
            ),
            # The worker sees what is left, never the whole budget: its own check (W-10) then
            # guards the same line the core guards here.
            limits=left if left is not None else run.budget,
            callback=Callback(events="sse"),
        )

        # 1 + 2: estimate and admit, before anything starts. A worker that cannot answer — an
        # execution unit that does not start, an endpoint that does not answer — fails the
        # step with that cause; the run escalates and nothing is left half done.
        call = {"run.id": run.id, "step.id": step.id, "adapter": adapter}
        try:
            async with self._telemetry.span("worker.estimate", call):
                estimate = await worker.estimate(assignment.estimate_request())
        except WorkerError as error:
            return await self._unavailable(run, step_run, adapter, span, error)
        demand = ConsumptionQuantities.model_validate(
            {**estimate.quantities(), "resource_class": estimate.resource_class}
        )
        run, step_run, admitted = await self._admit(
            run,
            step,
            step_run,
            _Demand(demand, adapter=adapter, capabilities=tuple(step.required_capabilities)),
            span,
        )
        if not admitted:
            return run, step_run
        # The worker's ceiling is what was reserved for it with its share of the margin, never
        # more than what is left of the whole budget: it halts at its next boundary before its
        # running total would cross it (W-14).
        reservation = step_run.reservation or demand
        assignment = assignment.model_copy(
            update={
                "limits": budgeting.ceiling(
                    budgeting.grow(reservation, run.margin),
                    remaining(run.budget, _without(run, step_run.step_id)),
                    run.budget,
                )
            }
        )

        # 3: run.
        call["assignment.id"] = assignment.assignment_id
        try:
            async with self._telemetry.span("worker.assign", call):
                state = await worker.assign(assignment)
        except WorkerError as error:
            return await self._unavailable(run, step_run, adapter, span, error)
        if state.status == "finished":
            # A rejection is a state, not an error: the worker's own check refused it.
            span.record_failure("rejected by the worker")
            step_run = step_run.to(
                StepState.REJECTED,
                assignment_id=assignment.assignment_id,
                reason=f"rejected by the worker: {state.reason or 'no reason given'}",
            )
            run = await self._commit(
                run.with_step_run(step_run),
                "step.rejected",
                step=step_run,
                outcome="rejected_by_worker",
            )
            return run, step_run
        step_run = step_run.to(
            StepState.RUNNING, assignment_id=assignment.assignment_id, started_at=self._clock.now()
        )
        run = await self._commit(run.with_step_run(step_run), "step.started", step=step_run)
        self._inflight[run.id] = (worker, assignment.assignment_id)
        if run.id in self._stop_requested:
            await self.request_stop(run.id)
        try:
            async with self._telemetry.span("worker.follow", call) as following:
                run, step_run = await self._follow(
                    run, step_run, worker, assignment.assignment_id, trace, span
                )
                following.set_attribute("step.state", step_run.state)
        except ClaimLost:
            # The runner that took the run over assigns the step again from its checkpoint;
            # this assignment has no one left to report to.
            with contextlib.suppress(Exception):
                await worker.stop(
                    assignment.assignment_id,
                    StopRequest(
                        reason="the claim on the run was lost",
                        ceiling_seconds=self._options.step_ceiling_seconds,
                    ),
                )
            raise
        finally:
            self._inflight.pop(run.id, None)
        _measured(span, step_run)
        return run, step_run

    async def _unavailable(
        self, run: Run, step_run: StepRun, adapter: str, span: Span, error: WorkerError
    ) -> tuple[Run, StepRun]:
        span.record_failure("worker unavailable")
        step_run = step_run.to(
            StepState.FAILED, adapter=adapter, reason=str(error), finished_at=self._clock.now()
        )
        run = await self._commit(
            run.with_step_run(step_run), "step.finished", step=step_run, outcome="failed"
        )
        return run, step_run

    async def _follow(
        self,
        run: Run,
        step_run: StepRun,
        worker: Worker,
        assignment_id: str,
        trace: Trace,
        span: Span,
    ) -> tuple[Run, StepRun]:
        """Read the stream to its end, persisting what arrives as it arrives."""
        # What an earlier attempt of this step used was used all the same: a resumed or
        # retried step accumulates on top of it, and the budget sees the whole.
        used: dict[str, Any] = {}
        if step_run.consumption is not None:
            used = dict(step_run.consumption.quantities())
            if step_run.consumption.resource_class is not None:
                used["resource_class"] = step_run.consumption.resource_class
        artifacts = list(step_run.artifacts)  # inherited from before the checkpoint on resume
        checkpoint_ref: str | None = (
            None if step_run.checkpoint is None else step_run.checkpoint.ref
        )
        finished: AssignmentFinished | None = None
        try:
            async for event in worker.events(assignment_id):
                if isinstance(event, ConsumptionReported):
                    _accumulate(used, event)
                elif isinstance(event, ArtifactProduced):
                    if any(a.id == event.artifact_id for a in artifacts):
                        continue  # produced before the checkpoint: never recorded twice
                    artifact = event.artifact()
                    content = await worker.artifact_bytes(assignment_id, artifact)
                    stored = await self._objects.put(content)
                    if stored != artifact.digest:
                        raise WorkerError(
                            f"artifact {artifact.id!r} hashes to {stored[:19]}…, not the "
                            f"announced {artifact.digest[:19]}…"
                        )
                    artifacts.append(artifact)
                elif isinstance(event, StepBoundary):
                    # The worker's own boundary: persisted now, so that an instance that dies
                    # after it resumes from here and not from the step's start.
                    checkpoint_ref = event.checkpoint_ref
                    step_run = step_run.model_copy(
                        update={
                            "artifacts": tuple(artifacts),
                            "consumption": _consumption(used),
                            "checkpoint": Checkpoint(
                                ref=checkpoint_ref,
                                step_id=step_run.step_id,
                                taken_at=self._clock.now(),
                                artifact_ids=tuple(a.id for a in artifacts),
                            ),
                        }
                    )
                    run = await self._commit(run.with_step_run(step_run))
                elif isinstance(event, AssignmentFinished):
                    finished = event
            if finished is None:
                raise WorkerError("the stream ended without assignment.finished")
        except WorkerError as error:
            span.record_failure("worker error")
            step_run = step_run.to(
                StepState.FAILED,
                artifacts=tuple(artifacts),
                consumption=_consumption(used),
                reason=str(error),
                finished_at=self._clock.now(),
            )
            run = await self._commit(
                run.with_step_run(step_run), "step.finished", step=step_run, outcome="failed"
            )
            return run, step_run

        now = self._clock.now()
        consumption = _consumption(used)
        if finished.outcome is Outcome.STOPPED:
            if finished.limit is not None:
                self._limit_halts.add(run.id)
            ref = finished.checkpoint_ref or checkpoint_ref
            checkpoint = (
                None
                if ref is None
                else Checkpoint(
                    ref=ref,
                    step_id=step_run.step_id,
                    taken_at=now,
                    artifact_ids=tuple(a.id for a in artifacts),
                )
            )
            step_run = step_run.to(
                StepState.STOPPED,
                artifacts=tuple(artifacts),
                consumption=consumption,
                checkpoint=checkpoint,
                reason=finished.reason
                or (
                    "stopped at the worker's step boundary"
                    if finished.limit is None
                    else f"the worker halted at its boundary before crossing its {finished.limit} "
                    "ceiling (W-14)"
                ),
                finished_at=now,
            )
            outcome = "stopped"
        elif finished.outcome is Outcome.SUCCEEDED:
            checkpoint = Checkpoint(
                ref=checkpoint_ref or f"ckpt/{run.id}/{step_run.step_id}",
                step_id=step_run.step_id,
                taken_at=now,
                artifact_ids=tuple(a.id for a in artifacts),
            )
            step_run = step_run.to(
                StepState.SUCCEEDED,
                artifacts=tuple(artifacts),
                consumption=consumption,
                checkpoint=checkpoint,
                finished_at=now,
            )
            outcome = "succeeded"
        else:
            span.record_failure(f"assignment {finished.outcome}")
            step_run = step_run.to(
                StepState.FAILED,
                artifacts=tuple(artifacts),
                consumption=consumption,
                reason=finished.reason or f"the assignment ended {finished.outcome}",
                finished_at=now,
            )
            outcome = "failed"
        run = await self._commit(
            run.with_step_run(step_run),
            "step.finished",
            step=step_run,
            outcome=outcome,
            trace=trace,
        )
        return run, step_run

    async def _results(
        self, run: Run, referenced: set[StepId], artifacts: set[tuple[StepId, str]] | None = None
    ) -> tuple[dict[StepId, Any], tuple[ProvenanceInput, ...]]:
        """What the referenced steps produced, for `$from` — and the same as provenance
        inputs: a result by digest, or every artifact by identifier and digest, each with the
        moment it was read. A step referenced only through one of its artifacts is read too."""
        results: dict[StepId, Any] = {}
        read: list[ProvenanceInput] = []
        wanted = referenced | {step_id for step_id, _ in (artifacts or set())}
        for step_run in run.step_runs:
            if not step_run.done or step_run.step_id not in wanted:
                continue
            observed_at = self._clock.now()
            checkpoint = step_run.checkpoint
            if checkpoint is not None and checkpoint.result_digest is not None:
                content = await self._objects.get(checkpoint.result_digest)
                results[step_run.step_id] = None if content is None else json.loads(content)
                read.append(
                    ProvenanceInput(
                        kind=InputKind.RESULT,
                        run_id=run.id,
                        step_id=step_run.step_id,
                        digest=checkpoint.result_digest,
                        observed_at=observed_at,
                    )
                )
            else:
                results[step_run.step_id] = {
                    "artifacts": [a.document() for a in step_run.artifacts]
                }
                read.extend(
                    ProvenanceInput(
                        kind=InputKind.ARTIFACT,
                        run_id=run.id,
                        step_id=step_run.step_id,
                        artifact_id=artifact.id,
                        digest=artifact.digest,
                        observed_at=observed_at,
                    )
                    for artifact in step_run.artifacts
                )
        return results, tuple(read)

    # --- persistence and the ledger --------------------------------------------------------------

    async def _commit(
        self,
        run: Run,
        kind: str | None = None,
        *,
        step: StepRun | None = None,
        outcome: str | None = None,
        actor: str | None = None,
        trace: Trace | None = None,
        enqueue: Job | None = None,
    ) -> Run:
        """One transaction: the run as it now is, and — when `kind` is given — the ledger entry
        that says what changed. Either both land or neither does. A step that finished with a
        result gets its provenance record in the same transaction, bound to that entry; a job
        to `enqueue` lands in it too."""
        run = run.model_copy(update={"updated_at": self._clock.now()})
        async with self._work.transaction(run.tenant):
            await self._fence(run)
            await self._runs.put(run.tenant, run)
            if enqueue is not None and self._queue is not None:
                await self._queue.enqueue(run.tenant, enqueue)
            if kind is not None:
                entry = await self._record(run, kind, step=step, outcome=outcome, actor=actor)
                if step is not None and trace is not None and step.done:
                    await self._provenance.append(
                        run.tenant,
                        provenance.record(
                            run,
                            step,
                            id=self._ids.new("prov"),
                            inputs=trace.inputs,
                            entry=entry,
                            adapter_version=trace.adapter_version,
                            at=self._clock.now(),
                        ),
                    )
                    if trace.egress is not None:
                        # The effect left the system: the egress entry names the step's
                        # result artifact and the digest of what went out (ADR-0022 §4).
                        await self._record(
                            run,
                            f"egress.{trace.egress.kind}",
                            step=step,
                            outcome="replayed" if trace.egress.replayed else "acted",
                            digest=trace.egress.content_digest,
                        )
        return run

    async def _fence(self, run: Run) -> None:
        """Inside a transaction that writes the run: refuse it unless the claim the run is
        executed under is still this runner's. The queue keeps the claim from being taken
        until the transaction ends, so the writes land under the claim or not at all."""
        claim = self._claim.get()
        if claim is None or self._queue is None:
            return
        if not await self._queue.fence(run.tenant, claim):
            raise ClaimLost(
                f"run {run.id!r}: job {claim.job_id!r} was claimed again after "
                f"{claim.claimant!r} claimed it (attempt {claim.attempt}); the write is refused"
            )

    async def _record(
        self,
        run: Run,
        kind: str,
        *,
        step: StepRun | None = None,
        outcome: str | None = None,
        actor: str | None = None,
        digest: Digest | None = None,
    ) -> LedgerEntry:
        refs = LedgerRefs(
            tenant=run.tenant,
            plan_id=run.plan_id,
            process_version=run.process_version,
            run_id=run.id,
            step_id=None if step is None else step.step_id,
            assignment_id=None if step is None else step.assignment_id,
            artifact_ids=None
            if step is None or not step.artifacts
            else tuple(a.id for a in step.artifacts),
            actor=actor,
            # The trace this entry is recorded in: what joins the ledger and the telemetry.
            trace_id=self._telemetry.current_trace_id(),
        )
        consumption: Consumption | None = None
        if step is not None:
            if kind in ("step.admitted", "step.rejected") and step.estimate is not None:
                quantities = step.estimate.quantities()
                if quantities:
                    consumption = Consumption.model_validate(
                        {**quantities, "resource_class": step.estimate.resource_class}
                    )
            elif step.consumption is not None:
                consumption = step.consumption
        if digest is None and step is not None and step.checkpoint is not None:
            digest = step.checkpoint.result_digest
        return await self._ledger.record(
            run.tenant,
            Fact(
                kind=kind,
                refs=refs,
                method=None if step is None else step.method,
                adapter=None if step is None else step.adapter,
                consumption=consumption,
                outcome=outcome,
                content_digest=digest,
                rehearsal=True if run.rehearsal else None,  # ADR-0030
            ),
        )


@dataclass(frozen=True)
class _StepFailed(Exception):
    """A local step that did not complete for a reason that is not a rule's: the connector
    refused, vanished or broke its contract, a wait ran out. Carries what the step run records."""

    reason: str
    retryable: bool | None
    consumption: Consumption | None
    adapter: str | None
    outcome: str


def _digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _canonical(document: Any) -> bytes:
    return json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _undeclared(operation: str) -> str:
    return (
        f"the operation {operation} declares no demand, so a call to it has no estimate; its "
        "connector must declare what one call consumes (contracts/connector/v1, Demand)"
    )


def _times(demand: Mapping[str, Any], calls: int) -> ConsumptionQuantities:
    """A declared demand for `calls` calls."""
    quantities: dict[str, Any] = {}
    for name, value in demand.items():
        if name == "currency":
            quantities[name] = {code: amount * calls for code, amount in value.items()}
        else:
            quantities[name] = value * calls
    if "compute_seconds" in quantities:
        quantities["resource_class"] = "connector"
    return ConsumptionQuantities.model_validate(quantities)


def _without(run: Run, step_id: StepId) -> ConsumptionQuantities:
    """What the run has used and reserved, the given step's own earlier use included but not
    its reservation: the step is being admitted again, and its old reservation is replaced."""
    for step_run in run.step_runs:
        if step_run.step_id == step_id and step_run.reservation is not None:
            return run.with_step_run(step_run.model_copy(update={"reservation": None})).consumed()
    return run.consumed()


def _measured(span: Span, step_run: StepRun) -> None:
    """What the step used, as span attributes: quantities and their class, never content."""
    span.set_attribute("step.state", step_run.state)
    consumption = step_run.consumption
    if consumption is None:
        return
    for name, value in consumption.quantities().items():
        if name == "tokens_by_model":
            continue  # model names are configuration, and the totals are already attributes
        if name == "currency" and isinstance(value, dict):
            for code, amount in value.items():
                span.set_attribute(f"consumption.currency.{code}", float(amount))
        elif isinstance(value, int | float):
            span.set_attribute(f"consumption.{name}", value)
    if consumption.resource_class is not None:
        span.set_attribute("consumption.resource_class", consumption.resource_class)


def _accumulate(used: dict[str, Any], event: ConsumptionQuantities) -> None:
    for name, value in event.quantities().items():
        if name == "tokens_by_model":
            used[name] = add_tokens_by_model(used.get(name), value)
        elif name == "currency" and isinstance(value, dict):
            totals: dict[str, float] = used.setdefault("currency", {})
            for code, amount in value.items():
                totals[code] = totals.get(code, 0.0) + amount
        elif isinstance(value, int | float):
            used[name] = used.get(name, 0) + value
    if event.resource_class is not None:
        used["resource_class"] = event.resource_class


def _consumption(used: dict[str, Any]) -> Consumption | None:
    if not any(name in used for name in QUANTITIES):
        return None
    return Consumption.model_validate(used)
