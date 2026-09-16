"""Use cases: start a run from a commissioned plan, resume a halted one, request a stop.

One engine, three entry points. `start` creates the run and executes it; `resume` continues a
halted or escalated run at its boundary; `request_stop` asks a running run to stop at its next
boundary. Execution is sequential: one step at a time, in the plan's order.

What happens around every step is the contract of ADR-0005 and is the same for every method:

1. estimate — a worker step asks the worker; a rule or wait step demands nothing;
2. admit — the estimate is checked against what remains of the budget (`domain.service.
   admission`); a step that does not fit is *rejected* before anything starts, and the run halts
   with cause `limit`;
3. run — through the worker port, the rule table, or the clock;
4. persist — the step run with its checkpoint, artifacts and raw consumption is written before
   the next step is looked at;
5. boundary — a stop requested meanwhile, or `stop_after`, takes effect here.

A worker step that is stopped mid-way ends `stopped` with the worker's checkpoint; resuming
hands that checkpoint back to the worker, which produces nothing it produced before it, and the
engine records no artifact twice even if it did.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from taktus.components.run.domain.model import (
    RESUMABLE,
    Cause,
    Checkpoint,
    ConstantRule,
    NoWorker,
    RuleFailed,
    Run,
    RunState,
    StepRun,
    StepState,
    UnknownRun,
    UnsupportedWork,
    VerifyArtifactRule,
    WaitWork,
    Work,
    WorkerWork,
    parse_work,
    references,
    resolve,
)
from taktus.components.run.domain.service import rules
from taktus.components.run.domain.service.admission import admit, remaining
from taktus.components.run.ports import WorkerPool
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Repository
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
    LedgerRefs,
    Plan,
    Step,
    StepId,
)


@dataclass(frozen=True)
class StartRun:
    plan: Plan
    work: Mapping[StepId, Mapping[str, Any]]
    budget: Limits
    process_version: str
    actor: str
    tenant: str | None = None
    stop_after: int | None = None


@dataclass(frozen=True)
class ResumeRun:
    run_id: str
    actor: str
    budget: Limits | None = None  # a changed limit; None keeps the run's
    stop_after: int | None = None


@dataclass(frozen=True)
class EngineOptions:
    step_ceiling_seconds: int = 300
    """How long a running worker step may take to finish after a stop was requested."""


class RunEngine:
    def __init__(
        self,
        *,
        runs: Repository[Run],
        objects: ObjectStore,
        ledger: Ledger,
        workers: WorkerPool,
        clock: Clock,
        ids: Identifiers,
        telemetry: Telemetry,
        options: EngineOptions | None = None,
    ) -> None:
        self._runs = runs
        self._objects = objects
        self._ledger = ledger
        self._workers = workers
        self._clock = clock
        self._ids = ids
        self._telemetry = telemetry
        self._options = options or EngineOptions()
        self._stop_requested: set[str] = set()
        self._inflight: dict[str, tuple[Worker, str]] = {}

    # --- entry points --------------------------------------------------------------------------

    async def start(self, command: StartRun) -> Run:
        now = self._clock.now()
        run = Run(
            id=self._ids.new("run"),
            plan_id=command.plan.id,
            process_version=command.process_version,
            tenant=command.tenant,
            autonomy_level=command.plan.autonomy_level,
            budget=command.budget,
            steps=command.plan.steps,
            work=command.work,
            created_at=now,
            updated_at=now,
        )
        self._check_executable(run)
        await self._save(run)
        await self._record(run, "run.created", actor=command.actor)
        run = await self._save(run.to(RunState.ADMITTED))
        run = await self._save(run.to(RunState.RUNNING))
        await self._record(run, "run.started")
        return await self._execute(run, command.stop_after)

    async def resume(self, command: ResumeRun) -> Run:
        run = await self._runs.get(command.run_id)
        if run is None:
            raise UnknownRun(command.run_id)
        if run.state not in RESUMABLE:
            raise UnknownRun(f"run {run.id!r} is {run.state} and cannot be resumed")
        if command.budget is not None:
            run = run.model_copy(update={"budget": command.budget})
        run = await self._save(run.to(RunState.RUNNING))
        await self._record(run, "run.resumed", actor=command.actor)
        return await self._execute(run, command.stop_after)

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
            work = parse_work(step, run.work.get(step.id))
            if isinstance(work, WorkerWork):
                for referenced in references(work.task.inputs):
                    if referenced not in ancestors[step.id]:
                        raise UnsupportedWork(
                            step.id, f"$from {referenced!r} is not a dependency of this step"
                        )

    async def _execute(self, run: Run, stop_after: int | None) -> Run:
        async with self._telemetry.span(
            "run", {"run.id": run.id, "process.version": run.process_version}
        ) as span:
            completed_now = 0
            while (step_run := run.next_step_run()) is not None:
                step = run.step(step_run.step_id)
                run, step_run = await self._execute_step(run, step, step_run)
                if step_run.state is StepState.REJECTED:
                    return await self._end(run, RunState.HALTED, Cause.LIMIT, step_run.reason, span)
                if step_run.state is StepState.FAILED:
                    return await self._end(
                        run, RunState.ESCALATED, Cause.FAILURE, step_run.reason, span
                    )
                if step_run.state is StepState.STOPPED:
                    return await self._end(run, RunState.HALTED, Cause.STOP, step_run.reason, span)
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
        run = await self._save(run.to(state, cause, reason))
        span.set_attribute("run.state", state)
        if cause is not None:
            span.set_attribute("run.cause", cause)
        outcome = "succeeded" if state is RunState.FINISHED else str(cause)
        await self._record(run, f"run.{state}", outcome=outcome)
        return run

    async def _execute_step(self, run: Run, step: Step, step_run: StepRun) -> tuple[Run, StepRun]:
        async with self._telemetry.span(
            "step", {"run.id": run.id, "step.id": step.id, "step.method": step.method}
        ) as span:
            work = parse_work(step, run.work.get(step.id))
            if isinstance(work, WorkerWork):
                return await self._worker_step(run, step, step_run, work, span)
            return await self._local_step(run, step, step_run, work, span)

    # --- rule and wait steps ---------------------------------------------------------------------

    async def _local_step(
        self, run: Run, step: Step, step_run: StepRun, work: Work, span: Span
    ) -> tuple[Run, StepRun]:
        # A rule or a wait demands nothing of any limit: admission is a formality, recorded so
        # that every step run reads the same in the ledger.
        step_run = step_run.to(StepState.ADMITTED, estimate=None, reason=None)
        run = await self._save(run.with_step_run(step_run))
        await self._record(run, "step.admitted", step=step_run)
        step_run = step_run.to(StepState.RUNNING, started_at=self._clock.now())
        run = await self._save(run.with_step_run(step_run))
        await self._record(run, "step.started", step=step_run)
        try:
            result_digest: str | None = None
            artifacts: tuple[Artifact, ...] = ()
            if isinstance(work, WaitWork):
                await self._clock.sleep(work.seconds)
            else:
                value = await self._evaluate(run, work)
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
            run = await self._save(run.with_step_run(step_run))
            await self._record(run, "step.finished", step=step_run, outcome="failed")
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
            StepState.SUCCEEDED, artifacts=artifacts, checkpoint=checkpoint, finished_at=now
        )
        run = await self._save(run.with_step_run(step_run))
        await self._record(run, "step.finished", step=step_run, outcome="succeeded")
        return run, step_run

    async def _evaluate(self, run: Run, work: Work) -> Any:
        if isinstance(work, ConstantRule):
            return rules.constant(work)
        if isinstance(work, VerifyArtifactRule):
            producer = run.step_run(work.step)
            artifact = producer.artifact(work.artifact)
            content = None if artifact is None else await self._objects.get(artifact.digest)
            return rules.verify_artifact(work, artifact, content)
        raise UnsupportedWork("?", f"no evaluator for {type(work).__name__}")  # unreachable

    # --- worker steps ----------------------------------------------------------------------------

    async def _worker_step(
        self, run: Run, step: Step, step_run: StepRun, work: WorkerWork, span: Span
    ) -> tuple[Run, StepRun]:
        resolved = await self._workers.resolve(step.required_capabilities)
        if resolved is None:
            raise NoWorker(step.id, step.required_capabilities)
        adapter, worker = resolved
        span.set_attribute("adapter", adapter)
        resuming = step_run.checkpoint if step_run.state is StepState.STOPPED else None
        left = remaining(run.budget, run.consumed())
        assignment = Assignment(
            assignment_id=self._ids.new("asg"),
            task=Task(
                goal=work.task.goal,
                acceptance=work.task.acceptance,
                inputs=resolve(work.task.inputs, await self._results(run)),
            ),
            context=Context(
                workspace=work.workspace,
                checkpoint_ref=None if resuming is None else resuming.ref,
            ),
            frame=Frame(
                autonomy_level=run.autonomy_level,
                allowed_tools=step.required_capabilities,
                forbidden=work.forbidden,
                max_steps=work.max_steps,
            ),
            # The worker sees what is left, never the whole budget: its own check (W-10) then
            # guards the same line the core guards here.
            limits=left if left is not None else run.budget,
            callback=Callback(events="sse"),
        )

        # 1 + 2: estimate and admit, before anything starts.
        estimate = await worker.estimate(assignment.estimate_request())
        demand = ConsumptionQuantities.model_validate(
            {**estimate.quantities(), "resource_class": estimate.resource_class}
        )
        admission = admit(demand, left, run.budget)
        if not admission.fits:
            span.record_failure("rejected by admission control")
            step_run = step_run.to(
                StepState.REJECTED,
                adapter=adapter,
                estimate=demand,
                reason="does not fit the remaining budget: " + "; ".join(admission.findings),
            )
            run = await self._save(run.with_step_run(step_run))
            await self._record(run, "step.rejected", step=step_run, outcome="rejected_by_admission")
            return run, step_run
        step_run = step_run.to(StepState.ADMITTED, adapter=adapter, estimate=demand, reason=None)
        run = await self._save(run.with_step_run(step_run))
        await self._record(run, "step.admitted", step=step_run)

        # 3: run.
        state = await worker.assign(assignment)
        if state.status == "finished":
            # A rejection is a state, not an error: the worker's own check refused it.
            span.record_failure("rejected by the worker")
            step_run = step_run.to(
                StepState.REJECTED,
                assignment_id=assignment.assignment_id,
                reason=f"rejected by the worker: {state.reason or 'no reason given'}",
            )
            run = await self._save(run.with_step_run(step_run))
            await self._record(run, "step.rejected", step=step_run, outcome="rejected_by_worker")
            return run, step_run
        step_run = step_run.to(
            StepState.RUNNING, assignment_id=assignment.assignment_id, started_at=self._clock.now()
        )
        run = await self._save(run.with_step_run(step_run))
        await self._record(run, "step.started", step=step_run)
        self._inflight[run.id] = (worker, assignment.assignment_id)
        if run.id in self._stop_requested:
            await self.request_stop(run.id)
        try:
            run, step_run = await self._follow(
                run, step_run, worker, assignment.assignment_id, span
            )
        finally:
            self._inflight.pop(run.id, None)
        return run, step_run

    async def _follow(
        self, run: Run, step_run: StepRun, worker: Worker, assignment_id: str, span: Span
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
                    checkpoint_ref = event.checkpoint_ref
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
            run = await self._save(run.with_step_run(step_run))
            await self._record(run, "step.finished", step=step_run, outcome="failed")
            return run, step_run

        now = self._clock.now()
        consumption = _consumption(used)
        if finished.outcome is Outcome.STOPPED:
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
                reason=finished.reason or "stopped at the worker's step boundary",
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
        run = await self._save(run.with_step_run(step_run))
        await self._record(run, "step.finished", step=step_run, outcome=outcome)
        return run, step_run

    async def _results(self, run: Run) -> dict[StepId, Any]:
        """What every finished step produced, for `$from`."""
        results: dict[StepId, Any] = {}
        for step_run in run.step_runs:
            if not step_run.done:
                continue
            checkpoint = step_run.checkpoint
            if checkpoint is not None and checkpoint.result_digest is not None:
                content = await self._objects.get(checkpoint.result_digest)
                results[step_run.step_id] = None if content is None else json.loads(content)
            else:
                results[step_run.step_id] = {
                    "artifacts": [a.document() for a in step_run.artifacts]
                }
        return results

    # --- persistence and the ledger --------------------------------------------------------------

    async def _save(self, run: Run) -> Run:
        run = run.model_copy(update={"updated_at": self._clock.now()})
        await self._runs.put(run)
        return run

    async def _record(
        self,
        run: Run,
        kind: str,
        *,
        step: StepRun | None = None,
        outcome: str | None = None,
        actor: str | None = None,
    ) -> None:
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
        digest = None
        if step is not None and step.checkpoint is not None:
            digest = step.checkpoint.result_digest
        await self._ledger.record(
            Fact(
                kind=kind,
                refs=refs,
                method=None if step is None else step.method,
                adapter=None if step is None else step.adapter,
                consumption=consumption,
                outcome=outcome,
                content_digest=digest,
            )
        )


def _accumulate(used: dict[str, Any], event: ConsumptionReported) -> None:
    for name, value in event.quantities().items():
        if name == "currency" and isinstance(value, dict):
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
