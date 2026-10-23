"""A change held to the process's evaluation cases, and drift measured on the same cases
(UC-4.18, ADR-0134).

- **Start.** An evaluation runs every case of the process's set as a rehearsal (ADR-0030): for a
  change, on the active version and on the proposal; for drift, on the active version alone.
  Every run goes the one path every run takes: a command, a commissioned plan, a run submitted
  to the queue.
- **Advance.** Once every case run has settled, the judges run: one rehearsal of one step on a
  language model per case, side and judge. Once those have settled, the evaluation is scored by
  the rules of `process/domain/service/scoring.py`, and its verdict recorded.
- **Hold.** A proposal that changes a step is commissioned only once its evaluation passed, or
  against its verdict with a person's reason (`ProposalActs.commission`).
- **Drift.** While it leads, the scheduler starts a drift evaluation at every slot of a process's
  evaluation schedule, advances every evaluation that is not scored, and proposes a case for
  every correction of a scored step. A drift of a process that sends outward raises an incident.

This is wiring, because each act crosses components — process, command, run and governance —
and only the composition root may hold them all (`composition/README.md`).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

import structlog

from taktus.components.command.application.service import CommissionPlan, CommissionPlanHandler
from taktus.components.governance.application.service import Drifts, DriftSeen
from taktus.components.process.application.service.proposals import ProposalError
from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.process.domain.model import (
    CaseState,
    CorrectedCase,
    Evaluation,
    EvaluationCase,
    Process,
    ProcessVersion,
    Proposal,
    Scorer,
)
from taktus.components.process.domain.model.evaluation import (
    OVERRIDABLE,
    CaseResult,
    CaseRun,
    EvaluationState,
    Override,
    Purpose,
    Score,
    Side,
    SideResult,
    Verdict,
)
from taktus.components.process.domain.service import schedule, scoring
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import (
    ConnectorRule,
    Run,
    RunError,
    RunState,
    StepState,
    WorkerWork,
    parse_work,
)
from taktus.components.run.domain.model.run import Cause
from taktus.components.run.domain.service.maturation import CORRECTED
from taktus.composition.pools import Pools
from taktus.composition.tenancy import this_round
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.identity import IdentityResolver, ServedTenants
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.ports.worker import Limits
from taktus.shared.v1 import (
    AutonomyLevel,
    Command,
    ExactnessClass,
    Intent,
    LedgerRefs,
    Method,
    ReplyTo,
    Step,
)
from taktus.shared.v1.step import Fallback, Rejected

CHANNEL = "channel.web"
STARTED = "evaluation.started"
SCORED = "evaluation.scored"
OVERRIDDEN = "evaluation.overridden"
CASE_PROPOSED = "evaluation.case_proposed"
CASE_WITHHELD = "evaluation.case_withheld"
CASE_CONFIRMED = "evaluation.case_confirmed"
CASE_REJECTED = "evaluation.case_rejected"
INTERVAL_SECONDS = 60
"""How often the scheduler looks: as the watch over expected runs (ADR-0107 §3)."""
JUDGE = "judge"
"""The one step of a judge's run."""
JUDGE_SYSTEM = (
    "You judge an answer against a target answer by the criterion you are given. Answer with "
    "one number from 0 to 1, where 1 means the answer fully meets the criterion against the "
    "target and 0 means it does not at all. Answer with the number and nothing else."
)
JUDGE_PROMPT = (
    "Criterion: ${criterion}\n\nTarget answer:\n${target}\n\nAnswer to judge:\n${result}\n"
)
STILL_GOING = frozenset({Cause.CAPACITY, Cause.PARKED})
"""A halted run with one of these causes is tried again by its runner: it has not settled."""

type Outward = Callable[[ProcessVersion], Awaitable[bool]]

log = structlog.get_logger("taktusd")


def settled(run: Run | None) -> bool:
    """Whether a run can go no further without a person (ADR-0134 §3). A run that is missing
    has settled too: nothing will come of it."""
    if run is None:
        return True
    if run.state in (RunState.FINISHED, RunState.ESCALATED, RunState.WAITING_HUMAN):
        return True
    return run.state is RunState.HALTED and run.cause not in STILL_GOING


def outward_by(pools: Pools) -> Outward:
    """Whether a version sends anything outward: a step calls a connector operation declared
    outward, or is a worker step whose frame allows hosts (ADR-0134 §5). A step whose work
    cannot be read counts as one that does: strict, because the answer decides an incident."""

    async def outward(version: ProcessVersion) -> bool:
        examples = {name: given.example for name, given in version.inputs.items()}
        for step in version.ordered():
            try:
                work = parse_work(step, version.work.get(step.id), examples)
            except RunError:
                return True
            if isinstance(work, WorkerWork) and work.allowed_hosts:
                return True
            if isinstance(work, ConnectorRule) and await pools.outward(work):
                return True
        return False

    return outward


async def _always(version: ProcessVersion) -> bool:
    return True


def _key(index: int, scorer: Scorer) -> str:
    return f"{scorer.step}.{index}"


def _derived(prefix: str, *parts: str) -> str:
    return prefix + hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:20]


class Evaluations:
    def __init__(
        self,
        *,
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
        evaluations: Repository[Evaluation],
        cases: Repository[CorrectedCase],
        runs: Repository[Run],
        commission: CommissionPlanHandler,
        engine: RunEngine,
        identities: IdentityResolver,
        drifts: Drifts,
        ledger: Ledger,
        objects: ObjectStore,
        work: UnitOfWork,
        clock: Clock,
        ids: Identifiers,
        outward: Outward | None = None,
    ) -> None:
        """`outward` says whether a version sends anything outward; None, where no pools are
        known: every version does, so that a drift raises its incident rather than not."""
        self._processes = processes
        self._versions = versions
        self._evaluations = evaluations
        self._cases = cases
        self._runs = runs
        self._commission = commission
        self._engine = engine
        self._identities = identities
        self._drifts = drifts
        self._ledger = ledger
        self._objects = objects
        self._work = work
        self._clock = clock
        self._ids = ids
        self._outward = outward or _always

    # --- the set ---------------------------------------------------------------------------

    async def evaluation_set(
        self, tenant: Tenant, version: ProcessVersion
    ) -> tuple[tuple[EvaluationCase, ...], dict[str, str]]:
        """The process's evaluation set for its active version: the version's cases and every
        case a person confirmed for the process (ADR-0134 §1); and the cases left out, with why.
        A confirmed case whose target names a step the version does not score is left out; so is
        a case that keeps an input a step's scope names, while the tenant does not allow it."""
        spec = version.evaluation
        if spec is None:
            return (), {}
        async with self._work.transaction(tenant):
            confirmed = [
                c.case
                for c in await self._cases.list(tenant)
                if c.process_id == version.process_id
                and c.state is CaseState.CONFIRMED
                and c.case is not None
            ]
        allowed = (await self._drifts.configuration(tenant)).evaluation_subjects
        personal = scoring.personal_inputs(version)
        cases: list[EvaluationCase] = []
        left_out: dict[str, str] = {}
        for case in (*spec.cases, *confirmed):
            unscored = sorted(set(case.targets) - spec.scored_steps)
            held = sorted(personal & set(case.inputs))
            if unscored:
                left_out[case.id] = (
                    f"its target names {', '.join(unscored)}, which the version does not score"
                )
            elif held and not allowed:
                left_out[case.id] = (
                    f"it keeps the input(s) {', '.join(held)}, which a step's scope names as its "
                    "subject, and the tenant does not allow personal data in cases"
                )
            else:
                cases.append(case)
        return tuple(cases), left_out

    async def needed(self, tenant: Tenant, proposal: Proposal) -> bool:
        """Whether a proposal is held to the cases: it changes a step, and the set of the
        version it was made against is not empty (ADR-0134 §4)."""
        if not scoring.evaluated(proposal.difference):
            return False
        async with self._work.transaction(tenant):
            base = await self._versions.get(tenant, proposal.base_ref)
        if base is None:
            return False
        cases, _ = await self.evaluation_set(tenant, base)
        return bool(cases)

    # --- starting --------------------------------------------------------------------------

    async def start_change(self, tenant: Tenant, proposal: Proposal, by: str) -> Evaluation | None:
        """The proposal's evaluation beside the active version; None where it needs none."""
        if not await self.needed(tenant, proposal):
            return None
        async with self._work.transaction(tenant):
            base = await self._versions.get(tenant, proposal.base_ref)
        if base is None or base.evaluation is None:
            return None
        cases, left_out = await self.evaluation_set(tenant, base)
        candidate = parse_bundle(proposal.bundle)
        reference = f"{proposal.process_id}@proposal-{proposal.id}"
        evaluation = Evaluation(
            id=self._ids.new("evl"),
            tenant=tenant,
            process_id=proposal.process_id,
            purpose=Purpose.CHANGE,
            version=base.ref,
            proposal=proposal.id,
            candidate=reference,
            acting_for=by,
            cases=cases,
            scorers=base.evaluation.scorers,
            started_at=self._clock.now(),
        )
        runs = [
            *await self._run_side(tenant, evaluation, Side.ACTIVE, base, base.ref, left_out),
            *await self._run_side(
                tenant, evaluation, Side.PROPOSED, candidate, reference, left_out
            ),
        ]
        return await self._started(tenant, evaluation.model_copy(update={"runs": tuple(runs)}))

    async def start_drift(
        self, tenant: Tenant, process_id: str, *, slot: datetime | None = None
    ) -> Evaluation | None:
        """The active version on its cases with no change. None where the process has no active
        version with cases, nobody it acts for, or the slot was evaluated already."""
        async with self._work.transaction(tenant):
            process = await self._processes.get(tenant, process_id)
            version = (
                None
                if process is None or process.active_version is None
                else await self._versions.get(tenant, f"{process_id}@{process.active_version}")
            )
        if process is None or version is None or version.evaluation is None:
            return None
        if process.activated_by is None:
            log.warning(
                "no drift evaluation: nobody activated the process to act for",
                tenant=tenant,
                process=process_id,
            )
            return None
        cases, left_out = await self.evaluation_set(tenant, version)
        if not cases:
            return None
        evaluation_id = (
            self._ids.new("evl")
            if slot is None
            else _derived("evl_", tenant, process_id, slot.isoformat())
        )
        async with self._work.transaction(tenant):
            if await self._evaluations.get(tenant, evaluation_id) is not None:
                return None
        evaluation = Evaluation(
            id=evaluation_id,
            tenant=tenant,
            process_id=process_id,
            purpose=Purpose.DRIFT,
            version=version.ref,
            slot=slot,
            acting_for=process.activated_by,
            cases=cases,
            scorers=version.evaluation.scorers,
            started_at=self._clock.now(),
        )
        runs = await self._run_side(tenant, evaluation, Side.ACTIVE, version, version.ref, left_out)
        return await self._started(tenant, evaluation.model_copy(update={"runs": tuple(runs)}))

    async def _started(self, tenant: Tenant, evaluation: Evaluation) -> Evaluation:
        async with self._work.transaction(tenant):
            await self._evaluations.put(tenant, evaluation)
            await self._ledger.record(
                tenant,
                Fact(
                    kind=STARTED,
                    refs=LedgerRefs(
                        tenant=tenant,
                        process_version=evaluation.candidate or evaluation.version,
                        actor=evaluation.acting_for,
                    ),
                    outcome=evaluation.purpose.value,
                ),
            )
        return evaluation

    async def _run_side(
        self,
        tenant: Tenant,
        evaluation: Evaluation,
        side: Side,
        version: ProcessVersion,
        reference: str,
        left_out: Mapping[str, str],
    ) -> list[CaseRun]:
        runs = [
            CaseRun(case=case_id, side=side, left_out=why)
            for case_id, why in sorted(left_out.items())
        ]
        budget = self._budget(version)
        for case in evaluation.cases:
            if isinstance(budget, str):
                runs.append(CaseRun(case=case.id, side=side, left_out=budget))
                continue
            run = await self._submit(
                tenant,
                evaluation,
                run_id=f"{evaluation.id}-{side.value}-{case.id}",
                reference=reference,
                goal=f"evaluate {reference} on the case {case.id}",
                steps=version.ordered(),
                work={k: dict(v) for k, v in version.work.items()},
                budget=budget,
                inputs=dict(case.inputs),
                level=version.autonomy_level,
                actions=dict(version.autonomy.action_levels),
            )
            runs.append(CaseRun(case=case.id, side=side, run_id=run.id))
        return runs

    @staticmethod
    def _budget(version: ProcessVersion) -> Limits | str:
        """The version's budget for each case run, or why there is none."""
        if version.limits is None:
            return f"{version.ref} names no `limits`; a rehearsal needs a budget"
        try:
            return Limits.model_validate(dict(version.limits))
        except ValueError as error:
            return f"{version.ref}: `limits`: {error}"

    async def _submit(
        self,
        tenant: Tenant,
        evaluation: Evaluation,
        *,
        run_id: str,
        reference: str,
        goal: str,
        steps: Sequence[Step],
        work: Mapping[str, Mapping[str, Any]],
        budget: Limits,
        inputs: Mapping[str, Any],
        level: AutonomyLevel,
        actions: Mapping[str, AutonomyLevel],
    ) -> Run:
        """One rehearsal, through the one path every run takes. Its identifier is derived from
        the evaluation, so that a second start names the same run and creates none."""
        async with self._work.transaction(tenant):
            existing = await self._runs.get(tenant, run_id)
        if existing is not None:
            return existing
        placed = await self._identities.identity(tenant, evaluation.acting_for)
        if placed is None:
            raise ProposalError(
                "unknown", f"the identity {evaluation.acting_for!r} is not known to {tenant!r}"
            )
        command = Command(
            id=self._ids.new("cmd"),
            channel=CHANNEL,
            identity=placed.identity,
            org_path=placed.org_path,
            intent=Intent(raw=goal, recognised="process.evaluate"),
            context={"inputs": dict(inputs), "evaluation": evaluation.id},
            reply_to=ReplyTo(channel=CHANNEL, address="ledger"),
            received_at=self._clock.now(),
        )
        plan = await self._commission.execute(
            CommissionPlan(
                command=command, tenant=tenant, goal=goal, autonomy_level=level, steps=tuple(steps)
            )
        )
        return await self._engine.submit(
            StartRun(
                plan=plan,
                work=work,
                budget=budget,
                process_version=reference,
                actor=placed.identity,
                tenant=tenant,
                inputs=dict(inputs),
                rehearsal=True,
                run_id=run_id,
                actions=actions,
            )
        )

    # --- advancing and scoring -------------------------------------------------------------

    async def advance(self, tenant: Tenant, evaluation_id: str) -> Evaluation:
        """The evaluation, moved on as far as its runs allow: its judges started once every case
        run settled, and scored once every judge's run settled."""
        async with self._work.transaction(tenant):
            evaluation = await self._evaluations.get(tenant, evaluation_id)
        if evaluation is None:
            raise ProposalError("unknown", f"no evaluation {evaluation_id!r}")
        if evaluation.state is EvaluationState.SCORED:
            return evaluation
        runs = await self._runs_of(tenant, evaluation)
        if evaluation.state is EvaluationState.RUNNING:
            if not all(settled(runs.get(r.run_id)) for r in evaluation.runs if r.run_id):
                return evaluation
            judged = await self._judge(tenant, evaluation, runs)
            if judged is not None:
                async with self._work.transaction(tenant):
                    await self._evaluations.put(tenant, judged)
                return judged
        judges = await self._judge_runs(tenant, evaluation)
        if not all(settled(run) for run in judges.values()):
            return evaluation
        return await self._scored(tenant, evaluation, runs, judges)

    async def _runs_of(self, tenant: Tenant, evaluation: Evaluation) -> dict[str, Run]:
        found: dict[str, Run] = {}
        async with self._work.transaction(tenant):
            for case_run in evaluation.runs:
                if case_run.run_id is not None:
                    run = await self._runs.get(tenant, case_run.run_id)
                    if run is not None:
                        found[run.id] = run
        return found

    async def _judge_runs(self, tenant: Tenant, evaluation: Evaluation) -> dict[str, Run | None]:
        found: dict[str, Run | None] = {}
        async with self._work.transaction(tenant):
            for case_run in evaluation.runs:
                for run_id in case_run.judges.values():
                    found[run_id] = await self._runs.get(tenant, run_id)
        return found

    async def _judge(
        self, tenant: Tenant, evaluation: Evaluation, runs: Mapping[str, Run]
    ) -> Evaluation | None:
        """The evaluation with a judge's run for every case, side and judge whose step produced
        a result; None where no judge has anything to judge."""
        judges = [(i, s) for i, s in enumerate(evaluation.scorers) if s.judge]
        if not judges:
            return None
        cases = {case.id: case for case in evaluation.cases}
        async with self._work.transaction(tenant):
            version = await self._versions.get(tenant, evaluation.version)
        budget = (
            f"the version {evaluation.version} is no longer registered"
            if version is None
            else self._budget(version)
        )
        updated: list[CaseRun] = []
        started = False
        for case_run in evaluation.runs:
            run = None if case_run.run_id is None else runs.get(case_run.run_id)
            case = cases.get(case_run.case)
            started_here: dict[str, str] = {}
            if (
                run is not None
                and case is not None
                and version is not None
                and not isinstance(budget, str)
            ):
                for index, scorer in judges:
                    if scorer.step not in case.targets:
                        continue
                    produced = await self._result(run, scorer.step)
                    if produced is None:
                        continue
                    key = _key(index, scorer)
                    judge_run = await self._submit_judge(
                        tenant,
                        evaluation,
                        case_run,
                        key,
                        scorer,
                        target=case.targets[scorer.step],
                        result=produced[0],
                        budget=budget,
                        level=version.autonomy_level,
                    )
                    started_here[key] = judge_run.id
            started = started or bool(started_here)
            updated.append(case_run.model_copy(update={"judges": started_here}))
        if not started:
            return None
        return evaluation.model_copy(
            update={"runs": tuple(updated), "state": EvaluationState.JUDGING}
        )

    async def _submit_judge(
        self,
        tenant: Tenant,
        evaluation: Evaluation,
        case_run: CaseRun,
        key: str,
        scorer: Scorer,
        *,
        target: Any,
        result: str,
        budget: Limits,
        level: AutonomyLevel,
    ) -> Run:
        """One judge: a rehearsal of one step on a language model of the scorer's purpose. Its
        answer must be one number from 0 to 1, by the step's own pattern check."""
        step = Step(
            id=JUDGE,
            method=Method.LLM,
            reason=scorer.reason,
            rejected=scorer.rejected or (Rejected(method=Method.RULE, why=scorer.reason),),
            exactness=ExactnessClass.TOLERANT,
            fallback=scorer.fallback
            or Fallback(when="the answer is not one number from 0 to 1", to=Method.HUMAN),
        )
        work = {
            JUDGE: {
                "purpose": scorer.purpose,
                "system": JUDGE_SYSTEM,
                "prompt": JUDGE_PROMPT,
                "values": {
                    "criterion": {"$input": "criterion"},
                    "target": {"$input": "target"},
                    "result": {"$input": "result"},
                },
                "max_output_tokens": 16,
                "pattern": scoring.JUDGED.pattern,
            }
        }
        reference = f"{evaluation.process_id}@evaluation-{evaluation.id}"
        return await self._submit(
            tenant,
            evaluation,
            run_id=f"{evaluation.id}-{case_run.side.value}-{case_run.case}-{key}",
            reference=reference,
            goal=f"judge the case {case_run.case} of {reference} by {key}",
            steps=(step,),
            work=work,
            budget=budget,
            inputs={
                "criterion": scorer.criterion or "",
                "target": scoring.text_of(target),
                "result": result,
            },
            level=level,
            actions={},
        )

    async def _result(self, run: Run, step_id: str) -> tuple[str, str | None] | None:
        """The text of a step's result and the model that answered it, where the step produced
        one; None where it did not."""
        try:
            step_run = run.step_run(step_id)
        except KeyError:
            return None
        checkpoint = step_run.checkpoint
        if (
            step_run.state is not StepState.SUCCEEDED
            or checkpoint is None
            or checkpoint.result_digest is None
        ):
            return None
        content = await self._objects.get(checkpoint.result_digest)
        if content is None:
            return None
        value = json.loads(content)
        if (
            step_run.method is Method.LLM
            and isinstance(value, Mapping)
            and isinstance(value.get("text"), str)
        ):
            model = value.get("model")
            return value["text"], model if isinstance(model, str) else None
        return scoring.text_of(value), None

    async def _models(self, run: Run) -> dict[str, str]:
        """The model that answered each step on a language model, as the provider named it."""
        found: dict[str, str] = {}
        for step_run in run.step_runs:
            if step_run.method is not Method.LLM:
                continue
            produced = await self._result(run, step_run.step_id)
            if produced is not None and produced[1] is not None:
                found[step_run.step_id] = produced[1]
        return found

    async def _case(
        self,
        evaluation: Evaluation,
        case_run: CaseRun,
        runs: Mapping[str, Run],
        judges: Mapping[str, Run | None],
    ) -> CaseResult:
        if case_run.left_out is not None:
            return CaseResult(case=case_run.case, side=case_run.side, left_out=case_run.left_out)
        cases = {case.id: case for case in evaluation.cases}
        case = cases[case_run.case]
        run = None if case_run.run_id is None else runs.get(case_run.run_id)
        scores: list[Score] = []
        for index, scorer in enumerate(evaluation.scorers):
            if scorer.step not in case.targets:
                continue
            key = _key(index, scorer)
            target = case.targets[scorer.step]
            produced = None if run is None else await self._result(run, scorer.step)
            scores.append(await self._score(key, scorer, produced, target, case_run, judges))
        used = None if run is None else run.consumed()
        seconds = (
            None if run is None else max(0.0, (run.updated_at - run.created_at).total_seconds())
        )
        return CaseResult(
            case=case.id,
            side=case_run.side,
            run_id=case_run.run_id,
            run_state=None if run is None else run.state.value,
            score=scoring.mean(s.score for s in scores),
            scores=tuple(scores),
            models={} if run is None else await self._models(run),
            seconds=seconds,
            tokens_in=0 if used is None else used.tokens_in or 0,
            tokens_out=0 if used is None else used.tokens_out or 0,
        )

    async def _score(
        self,
        key: str,
        scorer: Scorer,
        produced: tuple[str, str | None] | None,
        target: Any,
        case_run: CaseRun,
        judges: Mapping[str, Run | None],
    ) -> Score:
        def made(value: float | None, how: Any) -> Score:
            return Score(
                scorer=key,
                step=scorer.step,
                method=scorer.method,
                exactness=scorer.exactness,
                score=value,
                how=how,
            )

        if produced is None:
            return made(0.0, "no result")
        text = produced[0]
        if not scorer.judge and scorer.rule is not None:
            return made(scoring.score(scorer.rule, text, target), "rule")
        judge_id = case_run.judges.get(key)
        judge = None if judge_id is None else judges.get(judge_id)
        answer = None
        if judge is not None and judge.state is RunState.FINISHED:
            answered = await self._result(judge, JUDGE)
            answer = None if answered is None else scoring.judged(answered[0])
        if answer is not None:
            return made(answer, "judge")
        if scorer.rule is not None:
            return made(scoring.score(scorer.rule, text, target), "fallback")
        return made(None, "person")

    async def _scored(
        self,
        tenant: Tenant,
        evaluation: Evaluation,
        runs: Mapping[str, Run],
        judges: Mapping[str, Run | None],
    ) -> Evaluation:
        results = tuple([await self._case(evaluation, r, runs, judges) for r in evaluation.runs])
        tolerance = (await self._drifts.configuration(tenant)).evaluation_tolerance
        active = scoring.side(Side.ACTIVE, evaluation.version, results)
        previous: Evaluation | None = None
        sides: tuple[SideResult, ...]
        if evaluation.purpose is Purpose.CHANGE:
            proposed = scoring.side(
                Side.PROPOSED, evaluation.candidate or evaluation.version, results
            )
            sides = (active, proposed)
            verdict = scoring.change(active, proposed, tolerance)
        else:
            previous = await self._previous(tenant, evaluation)
            sides = (active,)
            before = None if previous is None else _score_of(previous)
            verdict = scoring.drift(active, before, tolerance)
        scored = evaluation.model_copy(
            update={
                "state": EvaluationState.SCORED,
                "results": results,
                "sides": sides,
                "verdict": verdict,
                "tolerance": tolerance,
                "compared_with": None if previous is None else previous.id,
                "previous_score": None if previous is None else _score_of(previous),
                "scored_at": self._clock.now(),
            }
        )
        digest = await self._objects.put(
            json.dumps(scored.document(), ensure_ascii=False, sort_keys=True).encode("utf-8")
        )
        async with self._work.transaction(tenant):
            current = await self._evaluations.get(tenant, evaluation.id)
            if current is not None and current.state is EvaluationState.SCORED:
                return current
            await self._evaluations.put(tenant, scored)
            await self._ledger.record(
                tenant,
                Fact(
                    kind=SCORED,
                    refs=LedgerRefs(
                        tenant=tenant, process_version=evaluation.candidate or evaluation.version
                    ),
                    outcome=verdict.value,
                    content_digest=digest,
                ),
            )
        if verdict is Verdict.DRIFT and previous is not None:
            await self._drifted(tenant, scored, previous)
        return scored

    async def _previous(self, tenant: Tenant, evaluation: Evaluation) -> Evaluation | None:
        """The last scored drift evaluation of the same version, with a score."""
        async with self._work.transaction(tenant):
            found = [
                e
                for e in await self._evaluations.list(tenant)
                if e.process_id == evaluation.process_id
                and e.purpose is Purpose.DRIFT
                and e.version == evaluation.version
                and e.id != evaluation.id
                and e.state is EvaluationState.SCORED
                and _score_of(e) is not None
                and e.scored_at is not None
            ]
        return max(found, key=lambda e: (e.scored_at, e.id)) if found else None

    async def _drifted(self, tenant: Tenant, scored: Evaluation, previous: Evaluation) -> None:
        async with self._work.transaction(tenant):
            version = await self._versions.get(tenant, scored.version)
        if version is None or not await self._outward(version):
            log.warning(
                "a drift on the evaluation cases; the process sends nothing outward",
                tenant=tenant,
                evaluation=scored.id,
                process=scored.version,
            )
            return
        models: dict[str, str] = {}
        for result in previous.results:
            models.update({f"{step}@before": model for step, model in result.models.items()})
        for result in scored.results:
            models.update(result.models)
        score, before = _score_of(scored), _score_of(previous)
        if score is None or before is None:
            return
        await self._drifts.drifted(
            tenant,
            DriftSeen(
                process_version=scored.version,
                evaluation=scored.id,
                compared_with=previous.id,
                score=score,
                previous=before,
                tolerance=scored.tolerance or 0.0,
                models=models,
            ),
        )

    # --- holding a change ------------------------------------------------------------------

    async def hold(
        self, tenant: Tenant, proposal: Proposal, by: str, override: str | None = None
    ) -> Evaluation | None:
        """Nothing where the proposal may be commissioned; ProposalError where its evaluation
        has not passed and no person overrides it (ADR-0134 §4). An override is recorded with
        its reason before the proposal is commissioned."""
        if not await self.needed(tenant, proposal):
            return None
        if proposal.evaluation is None:
            raise ProposalError(
                "unevaluated",
                f"the proposal {proposal.id} changes a step and is held to the process's "
                "evaluation cases: rehearse it, which starts its evaluation",
            )
        evaluation = await self.advance(tenant, proposal.evaluation)
        if evaluation.state is not EvaluationState.SCORED or evaluation.verdict is None:
            raise ProposalError(
                "unevaluated",
                f"the evaluation {evaluation.id} is {evaluation.state.value}; the proposal is "
                "commissioned once it is scored",
            )
        if evaluation.verdict is Verdict.PASSED:
            return evaluation
        if override is None or not override.strip():
            raise ProposalError(evaluation.verdict.value, _refusal(evaluation))
        if evaluation.verdict not in OVERRIDABLE:
            raise ProposalError(evaluation.verdict.value, _refusal(evaluation))
        overridden = evaluation.model_copy(
            update={"override": Override(reason=override.strip(), at=self._clock.now())}
        )
        digest = await self._objects.put(override.strip().encode("utf-8"))
        async with self._work.transaction(tenant):
            await self._evaluations.put(tenant, overridden)
            await self._ledger.record(
                tenant,
                Fact(
                    kind=OVERRIDDEN,
                    refs=LedgerRefs(
                        tenant=tenant,
                        process_version=evaluation.candidate or evaluation.version,
                        actor=by,
                    ),
                    outcome=evaluation.verdict.value,
                    content_digest=digest,
                ),
            )
        return overridden

    # --- reading ---------------------------------------------------------------------------

    async def get(self, tenant: Tenant, process_id: str, evaluation_id: str) -> Evaluation:
        async with self._work.transaction(tenant):
            found = await self._evaluations.get(tenant, evaluation_id)
        if found is None or found.process_id != process_id:
            raise ProposalError("unknown", f"no evaluation {evaluation_id!r} of {process_id!r}")
        return found

    async def of_process(self, tenant: Tenant, process_id: str) -> list[Evaluation]:
        """The process's evaluations, newest first."""
        async with self._work.transaction(tenant):
            found = [e for e in await self._evaluations.list(tenant) if e.process_id == process_id]
        return sorted(found, key=lambda e: (e.started_at, e.id), reverse=True)

    async def cases_of(self, tenant: Tenant, process_id: str) -> list[CorrectedCase]:
        """The cases proposed from corrections, newest first."""
        async with self._work.transaction(tenant):
            found = [c for c in await self._cases.list(tenant) if c.process_id == process_id]
        return sorted(found, key=lambda c: (c.proposed_at, c.id), reverse=True)

    # --- cases from corrections ------------------------------------------------------------

    async def propose_cases(self, tenant: Tenant) -> list[CorrectedCase]:
        """A case for every correction of a step that a scorer of its process's active version
        scores, once (ADR-0134 §7)."""
        async with self._work.transaction(tenant):
            entries = list(await self._ledger.of_kinds(tenant, {CORRECTED}))
            known = {c.id for c in await self._cases.list(tenant)}
        newest: dict[tuple[str, str], str] = {}
        for entry in entries:
            refs = entry.refs
            if refs.run_id and refs.step_id and entry.content_digest is not None:
                newest[(refs.run_id, refs.step_id)] = entry.content_digest
        made: list[CorrectedCase] = []
        for (run_id, step_id), digest in newest.items():
            case_id = _derived("cor-", run_id, step_id)
            if case_id in known:
                continue
            proposed = await self._propose_case(tenant, case_id, run_id, step_id, digest)
            if proposed is not None:
                made.append(proposed)
        return made

    async def _propose_case(
        self, tenant: Tenant, case_id: str, run_id: str, step_id: str, digest: str
    ) -> CorrectedCase | None:
        async with self._work.transaction(tenant):
            run = await self._runs.get(tenant, run_id)
            process_id = None if run is None else run.process_version.split("@", 1)[0]
            process = None if process_id is None else await self._processes.get(tenant, process_id)
            version = (
                None
                if process is None or process.active_version is None
                else await self._versions.get(tenant, f"{process.id}@{process.active_version}")
            )
        if run is None or run.rehearsal or version is None or version.evaluation is None:
            return None
        if step_id not in version.evaluation.scored_steps:
            return None
        content = await self._objects.get(digest)
        if content is None:
            return None
        inputs, left_out = scoring.reduced(run.inputs, version)
        held = sorted(scoring.personal_inputs(version) & set(inputs))
        allowed = (await self._drifts.configuration(tenant)).evaluation_subjects
        now = self._clock.now()
        refs = LedgerRefs(
            tenant=tenant, process_version=version.ref, run_id=run_id, step_id=step_id
        )
        if held and not allowed:
            why = (
                f"it would keep the input(s) {', '.join(held)}, which a step's scope names as its "
                "subject, and the tenant does not allow personal data in cases"
            )
            withheld = CorrectedCase(
                id=case_id,
                tenant=tenant,
                process_id=version.process_id,
                state=CaseState.WITHHELD,
                withheld=why,
                source_run=run_id,
                source_step=step_id,
                proposed_at=now,
            )
            await self._keep(tenant, withheld, CASE_WITHHELD, refs, outcome="personal")
            return withheld
        case = CorrectedCase(
            id=case_id,
            tenant=tenant,
            process_id=version.process_id,
            case=EvaluationCase(id=case_id, inputs=inputs, targets={step_id: json.loads(content)}),
            source_run=run_id,
            source_step=step_id,
            left_out=left_out,
            proposed_at=now,
        )
        await self._keep(tenant, case, CASE_PROPOSED, refs, outcome="proposed")
        return case

    async def _keep(
        self,
        tenant: Tenant,
        case: CorrectedCase,
        kind: str,
        refs: LedgerRefs,
        *,
        outcome: str,
        actor: str | None = None,
    ) -> None:
        async with self._work.transaction(tenant):
            await self._cases.put(tenant, case)
            await self._ledger.record(
                tenant,
                Fact(
                    kind=kind,
                    refs=refs if actor is None else refs.model_copy(update={"actor": actor}),
                    outcome=outcome,
                ),
            )

    async def confirm(
        self,
        tenant: Tenant,
        process_id: str,
        case_id: str,
        by: str,
        target: Any = None,
    ) -> CorrectedCase:
        """A proposed case confirmed by a person, with its target or the one they give; only
        now does it enter the evaluation set."""
        found = await self._open_case(tenant, process_id, case_id)
        case = found.case
        if case is None:
            raise ProposalError("closed", f"the case {case_id} keeps nothing to confirm")
        if target is not None:
            case = case.model_copy(update={"targets": {found.source_step: target}})
        confirmed = found.model_copy(
            update={"state": CaseState.CONFIRMED, "case": case, "decided_at": self._clock.now()}
        )
        await self._keep(
            tenant,
            confirmed,
            CASE_CONFIRMED,
            self._refs(tenant, found),
            outcome="confirmed",
            actor=by,
        )
        return confirmed

    async def reject(self, tenant: Tenant, process_id: str, case_id: str, by: str) -> CorrectedCase:
        """A proposed case a person rejected; it never enters the set."""
        found = await self._open_case(tenant, process_id, case_id)
        rejected = found.model_copy(
            update={"state": CaseState.REJECTED, "decided_at": self._clock.now()}
        )
        await self._keep(
            tenant, rejected, CASE_REJECTED, self._refs(tenant, found), outcome="rejected", actor=by
        )
        return rejected

    async def _open_case(self, tenant: Tenant, process_id: str, case_id: str) -> CorrectedCase:
        async with self._work.transaction(tenant):
            found = await self._cases.get(tenant, case_id)
        if found is None or found.process_id != process_id:
            raise ProposalError("unknown", f"no proposed case {case_id!r} of {process_id!r}")
        if found.state is not CaseState.PROPOSED:
            raise ProposalError("closed", f"the case {case_id} is {found.state.value}")
        return found

    @staticmethod
    def _refs(tenant: Tenant, case: CorrectedCase) -> LedgerRefs:
        return LedgerRefs(tenant=tenant, run_id=case.source_run, step_id=case.source_step)

    # --- the scheduler's look --------------------------------------------------------------

    async def look(self, tenant: Tenant) -> list[Evaluation]:
        """One look (ADR-0134 §5, §7): cases proposed from new corrections, a drift evaluation
        started for every process whose schedule has a slot not yet evaluated, and every
        evaluation that is not scored moved on. The evaluations started or scored are returned."""
        await self.propose_cases(tenant)
        moved: list[Evaluation] = []
        now = self._clock.now()
        async with self._work.transaction(tenant):
            processes = list(await self._processes.list(tenant))
            evaluations = list(await self._evaluations.list(tenant))
        for process in processes:
            if process.active_version is None:
                continue
            async with self._work.transaction(tenant):
                version = await self._versions.get(tenant, f"{process.id}@{process.active_version}")
            if version is None or version.evaluation is None or not version.evaluation.schedule:
                continue
            slot = schedule.parse(version.evaluation.schedule).latest(now)
            if slot is None:
                continue
            drifts = [
                e for e in evaluations if e.process_id == process.id and e.purpose is Purpose.DRIFT
            ]
            last = max((e.slot or e.started_at for e in drifts), default=None)
            if last is not None and last >= slot:
                continue
            started = await self.start_drift(tenant, process.id, slot=slot)
            if started is not None:
                moved.append(started)
        for evaluation in evaluations:
            if evaluation.state is EvaluationState.SCORED:
                continue
            advanced = await self.advance(tenant, evaluation.id)
            if advanced.state is EvaluationState.SCORED:
                moved.append(advanced)
        return moved


def _score_of(evaluation: Evaluation) -> float | None:
    side = evaluation.side(Side.ACTIVE)
    return None if side is None else side.score


def _refusal(evaluation: Evaluation) -> str:
    active = evaluation.side(Side.ACTIVE)
    proposed = evaluation.side(Side.PROPOSED)
    scores = (
        f"the proposal scored {_shown(proposed.score if proposed else None)} on the process's "
        f"evaluation cases, the active version {_shown(active.score if active else None)}, "
        f"within a tolerance of {evaluation.tolerance or 0:.2f}"
    )
    if evaluation.verdict is Verdict.INCOMPLETE:
        return (
            f"the evaluation {evaluation.id} is incomplete: a case has no score, because a judge "
            f"fell back to a person ({scores}); a person may commission it against the verdict, "
            "with a reason"
        )
    return (
        f"the evaluation {evaluation.id} found a regression: {scores}; a person may commission "
        "it against the verdict, with a reason"
    )


def _shown(value: float | None) -> str:
    return "nothing" if value is None else f"{value:.2f}"


def evaluations_tick(
    evaluations: Evaluations,
    tenants: ServedTenants,
    clock: Clock,
    *,
    interval_seconds: int = INTERVAL_SECONDS,
) -> Callable[[], Awaitable[None]]:
    """What the scheduler calls on every tick: every tenant is looked at once the interval has
    passed since the last look. A look that fails is logged and made again at the next
    interval: evaluating never stops the scheduler."""
    last: list[datetime] = []

    async def tick() -> None:
        now = clock.now()
        if last and now - last[0] < timedelta(seconds=interval_seconds):
            return
        last[:] = [now]
        for tenant in await this_round(tenants, "scheduler"):
            try:
                moved = await evaluations.look(tenant)
            except Exception as error:  # a look never takes the scheduler down
                log.error(
                    "evaluations not advanced; the next look tries again",
                    tenant=tenant,
                    error=f"{type(error).__name__}: {error}",
                )
                continue
            for evaluation in moved:
                if evaluation.verdict in (Verdict.DRIFT, Verdict.REGRESSED):
                    log.warning(
                        "an evaluation found its process worse on its cases",
                        tenant=tenant,
                        evaluation=evaluation.id,
                        verdict=evaluation.verdict.value,
                    )

    return tick
