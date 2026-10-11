"""Use case: Taktus proposes moving a step from a language model to a trained model, on
evidence (ADR-0084, issue #217, DEC-0164 provisionally Option A).

For every step on a language model whose cases reach the floor (`domain.service.maturation`),
Taktus makes the evidence before it proposes anything:

1. **A training run.** The ML bench trains a classifier twice on the same cases, with a fifth of
   every class held out and never given to it. Both trainings are steps of one run, executed by
   the run engine like any other: estimated, admitted, held to a budget, in the ledger. The
   model file is that run's artifact (UC-8.6's hub does not exist yet).
2. **A trial run.** The model, pinned by its digest, predicts the held-out cases as a step of
   method `ml` would (ADR-0076): once all of them, which gives the agreement, and once a single
   case, which gives the cost of one case as the moved step would pay it.
3. **The verdict, by a rule.** Agreement, cost and reproducibility are held to the floor. Below
   it, nothing is proposed, and the outcome says why.
4. **The proposal, a decision request.** It goes to whoever owns the process — the role `owner`,
   until a process names its owner (UC-15.5) — and states the step, the cases and classes, the
   agreement, the cost per case of both methods, the exactness class the move would allow, the
   confidence threshold, and the model by version and digest.

A change of a step's method is never made by Taktus (UC-4.3 §2, ADR-0004): asked to make it as a
change within the frame, it raises the proposal all the same and registers nothing. This handler
has no way to register a process version: it cannot apply what it proposes. Applying an
accepted proposal is #218.
"""

from __future__ import annotations

import hashlib
import json
from base64 import b64encode
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal

from pydantic import Field

from taktus.components.run.application.query.measures import StepCases, StepMeasures
from taktus.components.run.application.service.execute_run import RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState
from taktus.components.run.domain.service import maturation, prediction
from taktus.components.run.domain.service.maturation import Case, Evidence, Proposal
from taktus.components.run.ports import Decisions, Draft, DraftOption, NotRaised
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.model import PriceTable, price_compute
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Tenant, UnitOfWork
from taktus.ports.worker import Limits
from taktus.shared.v1 import (
    Commissioned,
    DecisionClass,
    ExactnessClass,
    Fallback,
    LedgerRefs,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    Rejected,
    Step,
    Value,
)

PROPOSED = "method.proposed"
"""The ledger kind of a maturation's verdict on a step it trained a candidate for."""
TRAINING = "method-maturation@1"
"""The process version the training and the trial runs are recorded under: Taktus's own, not
the step's process."""
DECIDER = "owner"
"""Whoever owns the process, until a process names its owner (UC-15.5)."""
TRAIN = ("data.read", "ml.train", "ml.evaluate")
PREDICT = ("data.read", "ml.predict")
NEVER_UNSURE = "confidence < 0"
"""The trial's fallback: a trial measures, so every prediction it makes is read, sure or not."""
BENCH_HOLDOUT = 0.05
"""What the bench holds out of the training cases for its own metrics: the least it allows. The
evidence is measured on the cases Taktus held out, which the bench never sees."""
WITHIN_FRAME = (
    "a change of a step's method kind is always outside the frame: it is proposed, never made "
    "(UC-4.3 §2, ADR-0004)"
)


@dataclass(frozen=True)
class ProposeMoves:
    tenant: Tenant
    actor: str
    """On whose behalf the training and the trial run."""
    budget: Limits
    """What each of the two runs may use."""
    process_version: str | None = None
    """Only this process version's steps; None for every one."""
    step_id: str | None = None
    as_change: bool = False
    """Asked to make the move as a change within the frame. It is proposed all the same."""
    seed: int = 0
    epochs: int = 5


class MoveOutcome(Value):
    """What maturation found for one step on a language model."""

    process_version: str
    step_id: str
    proposed: bool
    findings: tuple[str, ...] = ()
    """Why nothing was proposed; empty when it was."""
    request_id: str | None = None
    proposal: Proposal | None = None
    training_run: str | None = None
    trial_run: str | None = None
    applied: Literal[False] = False
    """Never: a person decides the move, and #218 applies it."""
    note: str | None = Field(default=None, min_length=1)
    """Why a request to make the move as a change was answered with a proposal."""


class ProposeMovesHandler:
    def __init__(
        self,
        engine: RunEngine,
        cases: StepMeasures,
        objects: ObjectStore,
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
        decisions: Decisions | None,
        prices: PriceTable | None,
        decision_days: int = 3,
    ) -> None:
        self._engine = engine
        self._cases = cases
        self._objects = objects
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._decisions = decisions
        self._prices = prices
        self._decision_days = decision_days

    async def execute(self, command: ProposeMoves) -> tuple[MoveOutcome, ...]:
        outcomes: list[MoveOutcome] = []
        for step in await self._cases.steps(command.tenant):
            if step.method is not Method.LLM:
                continue
            if command.process_version not in (None, step.process_version):
                continue
            if command.step_id not in (None, step.step_id):
                continue
            outcome = await self._one(command, step)
            if command.as_change:
                outcome = outcome.model_copy(update={"note": WITHIN_FRAME})
            outcomes.append(outcome)
        return tuple(outcomes)

    async def _one(self, command: ProposeMoves, step: StepCases) -> MoveOutcome:
        candidacy = maturation.candidacy(step.method, step.cases)
        outcome = MoveOutcome(
            process_version=step.process_version, step_id=step.step_id, proposed=False
        )
        if not candidacy.candidate:
            return outcome.model_copy(update={"findings": candidacy.findings})
        decisions = self._decisions
        if decisions is None:
            # Nobody could be asked, so nothing is trained to ask with.
            return outcome.model_copy(
                update={"findings": ("no decision port is wired: nobody can be asked",)}
            )
        train, held = maturation.split(step.cases, command.seed)
        features = candidacy.features
        training = await self._train(command, step, train, features)
        outcome = outcome.model_copy(update={"training_run": training.id})
        models = _models(training)
        if training.state is not RunState.FINISHED or len(models) != 2:
            return await self._refused(
                command,
                step,
                outcome,
                (f"the training run did not finish: {training.state}, {training.reason}",),
            )
        content = await self._objects.get(models[0])
        if content is None:  # unreachable: the engine stored what the worker produced
            return await self._refused(
                command, step, outcome, ("the trained model is not in the object store",)
            )
        digest = models[0]
        model_ref = maturation.model_ref(step.step_id, digest)
        trial = await self._trial(command, step, held, features, content, digest, model_ref)
        outcome = outcome.model_copy(update={"trial_run": trial.id})
        if trial.state is not RunState.FINISHED:
            return await self._refused(
                command,
                step,
                outcome,
                (f"the trial run did not finish: {trial.state}, {trial.reason}",),
            )
        rows = await self._predicted(trial, "held-out")
        one = trial.step_run("one-case").consumption
        ml_cost: float | None = None
        if self._prices is not None and one is not None and one.resource_class is not None:
            priced = price_compute({one.resource_class: one.compute_seconds or 0.0}, self._prices)
            ml_cost = None if priced.unpriced else priced.amount
        llm = maturation.measure(
            step.process_version,
            step.step_id,
            step.method,
            step.cases,
            None if self._prices is None else self._prices.currency,
        )
        evidence = Evidence(
            held_out=len(held),
            agreement=round(maturation.agreement(held, [r.label for r in rows]), 6),
            below_threshold=round(
                sum(1 for r in rows if r.confidence < maturation.FALLBACK_AT) / len(rows), 6
            )
            if rows
            else 1.0,
            llm_cost_per_case=llm.cost_per_case,
            ml_cost_per_case=None if ml_cost is None else round(ml_cost, 9),
            currency=None if self._prices is None else self._prices.currency,
            digests=tuple(models),
        )
        found = maturation.findings(evidence)
        if found:
            return await self._refused(command, step, outcome, found, evidence)
        proposal = Proposal(
            process_version=step.process_version,
            step_id=step.step_id,
            exactness=None if step.exactness is None else ExactnessClass(step.exactness),
            cases=len(step.cases),
            classes=candidacy.classes,
            features=features,
            left_out=candidacy.left_out,
            evidence=evidence,
            model=model_ref,
            training_run=training.id,
            trial_run=trial.id,
        )
        request_id = proposal.request_id(command.tenant)
        options = proposal.options()
        try:
            await decisions.raise_request(
                command.tenant,
                Draft(
                    id=request_id,
                    run=training.id,
                    step="train",
                    class_=str(DecisionClass.CONCEPTUAL),
                    situation=proposal.situation(),
                    question=proposal.question(),
                    options=tuple(
                        DraftOption(
                            id=o["id"],
                            proposal=o["proposal"],
                            consequence=o["consequence"],
                            recommended=o["recommended"],
                            reason=o.get("reason"),
                        )
                        for o in options
                    ),
                    blocking=(),
                    due=self._clock.now().date() + timedelta(days=self._decision_days),
                    decider=DECIDER,
                ),
            )
        except NotRaised as error:
            return await self._refused(command, step, outcome, (str(error),), evidence)
        await self._verdict(command, step, "proposed", proposal.document(), request_id)
        return outcome.model_copy(
            update={"proposed": True, "request_id": request_id, "proposal": proposal}
        )

    async def _train(
        self, command: ProposeMoves, step: StepCases, train: Sequence[Case], features: Any
    ) -> Run:
        data = maturation.dataset(train, features, labelled=True)
        inputs = {
            "operation": "train",
            "dataset": {
                "base64": b64encode(data).decode("ascii"),
                "digest": _digest(data),
                "rows": len(train),
                "features": len(features),
            },
            "label": maturation.LABEL,
            "seed": command.seed,
            "epochs": command.epochs,
            "holdout": BENCH_HOLDOUT,
        }
        task = {
            "goal": f"train a classifier for step {step.step_id} of {step.process_version}",
            "acceptance": ["a model file and its metrics"],
            "inputs": inputs,
        }
        steps = tuple(
            Step(
                id=step_id,
                method=Method.WORKER,
                reason=(
                    "training runs as a worker of its own (ADR-0004); twice on the same "
                    "cases, so that the model is shown to be reproducible"
                ),
                rejected=(
                    Rejected(
                        method=Method.RULE,
                        why="a rule cannot be learned from the cases; the bench learns it",
                    ),
                ),
                exactness=ExactnessClass.TOLERANT,
                # A training that fails proposes nothing; a person looks at the run.
                fallback=Fallback(when="the training fails", to=Method.HUMAN),
                requires=TRAIN,
            )
            for step_id in ("train", "train-again")
        )
        work = {s.id: {"task": task} for s in steps}
        return await self._run(command, step, "train", steps, work)

    async def _trial(
        self,
        command: ProposeMoves,
        step: StepCases,
        held: Sequence[Case],
        features: Any,
        model: bytes,
        digest: str,
        model_ref: str,
    ) -> Run:
        pinned = {"base64": b64encode(model).decode("ascii"), "digest": digest}
        sets = {"held-out": held, "one-case": held[:1]}
        steps: list[Step] = []
        work: dict[str, Mapping[str, Any]] = {}
        for step_id, rows in sets.items():
            data = maturation.dataset(rows, features, labelled=False)
            steps.append(
                Step(
                    id=step_id,
                    method=Method.ML,
                    reason=(
                        "the candidate predicts cases it was not trained on, as the moved step "
                        "would (ADR-0076)"
                    ),
                    rejected=(),
                    exactness=ExactnessClass.TOLERANT,
                    fallback=Fallback(when=NEVER_UNSURE, to=Method.HUMAN),
                    model=model_ref,
                    requires=PREDICT,
                )
            )
            work[step_id] = {
                "model": pinned,
                "dataset": {"base64": b64encode(data).decode("ascii"), "digest": _digest(data)},
            }
        return await self._run(command, step, "trial", tuple(steps), work)

    async def _run(
        self,
        command: ProposeMoves,
        step: StepCases,
        what: str,
        steps: tuple[Step, ...],
        work: Mapping[str, Mapping[str, Any]],
    ) -> Run:
        key = hashlib.sha256(
            f"{command.tenant}|{step.process_version}|{step.step_id}|{what}|"
            f"{self._clock.now().isoformat()}".encode()
        ).hexdigest()[:16]
        plan = Plan(
            id=f"pln_mat_{key}",
            command_id=f"cmd_mat_{key}",
            goal=f"{what} a candidate for step {step.step_id} of {step.process_version}",
            # The training and the trial act on nothing outside the bench: they run unattended,
            # as a step at level 3 does, on a worker that is at least verified (ADR-0039).
            autonomy_level=3,
            steps=steps,
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=command.actor, at=self._clock.now()),
        )
        return await self._engine.start(
            StartRun(
                plan=plan,
                work=work,
                budget=command.budget,
                process_version=TRAINING,
                actor=command.actor,
                tenant=command.tenant,
            )
        )

    async def _predicted(self, trial: Run, step_id: str) -> tuple[prediction.Row, ...]:
        checkpoint = trial.step_run(step_id).checkpoint
        if checkpoint is None or checkpoint.result_digest is None:
            return ()
        content = await self._objects.get(checkpoint.result_digest)
        if content is None:
            return ()
        document = json.loads(content)
        return tuple(
            prediction.Row(row=r["row"], label=r["class"], confidence=r["confidence"])
            for r in sorted(document.get("rows") or (), key=lambda r: r["row"])
        )

    async def _refused(
        self,
        command: ProposeMoves,
        step: StepCases,
        outcome: MoveOutcome,
        found: Sequence[str],
        evidence: Evidence | None = None,
    ) -> MoveOutcome:
        document = {
            "process_version": step.process_version,
            "step_id": step.step_id,
            "findings": list(found),
            "evidence": None if evidence is None else evidence.document(),
            "training_run": outcome.training_run,
            "trial_run": outcome.trial_run,
        }
        await self._verdict(command, step, "not_evidenced", document, None)
        return outcome.model_copy(update={"findings": tuple(found)})

    async def _verdict(
        self,
        command: ProposeMoves,
        step: StepCases,
        outcome: str,
        document: Mapping[str, Any],
        request_id: str | None,
    ) -> None:
        """The verdict on a step a candidate was trained for, in the ledger, with what it rests
        on by digest. No actor: Taktus acted on its own."""
        content = json.dumps(document, ensure_ascii=False, sort_keys=True, default=str)
        digest = await self._objects.put(content.encode("utf-8"))
        async with self._work.transaction(command.tenant):
            await self._ledger.record(
                command.tenant,
                Fact(
                    kind=PROPOSED,
                    refs=LedgerRefs(
                        tenant=command.tenant,
                        process_version=step.process_version,
                        step_id=step.step_id,
                        decision_request_id=request_id,
                    ),
                    method=Method.LLM,
                    outcome=outcome,
                    content_digest=digest,
                ),
            )


def _models(training: Run) -> list[str]:
    """The digest of the model each training produced."""
    found: list[str] = []
    for step_run in training.step_runs:
        artifact = step_run.artifact("model")
        if artifact is not None:
            found.append(artifact.digest)
    return found


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()
