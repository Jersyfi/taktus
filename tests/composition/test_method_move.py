"""An accepted proposal moves the step to the trained model, and the move is measured (issue
#218, ADR-0114, DEC-0164 provisionally Option A), over the memory stores.

The run history, the scripted language model and the scripted bench are
`tests/components/run/test_maturation.py`'s. Here the process is registered, the proposal is
answered and confirmed through the decision component, the move is applied by
`composition/moves.py`, and the new version runs: a case at or above the threshold is answered by
the trained model, a case below it by the language model. The move is measured over its first 100
cases, beside the version it replaced, and rolled back in one act.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import pytest
from components.run.test_maturation import (
    BUDGET,
    CLASSIFY,
    PRICES,
    STARTER,
    TENANT,
    WORK,
    World,
    bench,
    predictions,
    separable,
)
from fakes import FakeWorker, InnerStep

from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.decision.application.service import AnswerRequest, ConfirmRequest
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import InvalidProcess, Process, ProcessVersion
from taktus.components.process.domain.service.bundle import bundle_of
from taktus.components.process.domain.service.evaluation import MIN_AGREEMENT
from taktus.components.run.application.service import (
    MoveError,
    ProposeMoves,
    ReviewMovesHandler,
    StartRun,
)
from taktus.components.run.domain.model import Run, RunState
from taktus.components.run.domain.service import maturation
from taktus.composition.moves import MethodMoves
from taktus.ports.worker import Worker
from taktus.shared.v1 import Commissioned, LedgerEntry, Method, Plan, PlanResult, PlanStatus

OWNER = "idn_owner"


def bundle() -> dict[str, Any]:
    """The process the step belongs to: one step on a language model, as the cases ran it."""
    step = CLASSIFY.document()
    step["work"] = WORK
    return {
        "id": "triage",
        "version": "1",
        "name": "Triage",
        "autonomy": {"level": 3, "reason": "a test", "toward_next": "nothing"},
        "inputs": {
            "a": {"description": "a number", "example": 1.0},
            "b": {"description": "a number", "example": 0.1},
            "note": {"description": "a text", "example": "n"},
        },
        "steps": [step],
    }


class Moving(World):
    """The world of `test_maturation`, with the process registered, an owner who decides, the
    moves and their review, and a predictor whose answer each test sets per case. Given
    `workers` — the ML bench itself — the bench answers instead."""

    def __init__(
        self,
        predicted: list[str],
        *,
        predict_seconds: float = 0.5,
        workers: Sequence[Worker] | None = None,
    ) -> None:
        trainer, trial = bench(predicted, predict_seconds=predict_seconds)
        self.trial: FakeWorker | None = None if workers is not None else trial
        super().__init__(
            workers=[trainer, trial] if workers is None else workers,
            uncalibrated_margin=0.0 if workers is None else 1.0,
        )
        self.predict_seconds = predict_seconds
        self.processes = MemoryRepository(self.persistence, Process)
        self.versions = MemoryRepository(self.persistence, ProcessVersion)
        self.register = RegisterProcessVersionHandler(
            self.versions, self.persistence, self.processes, ledger=self.ledger
        )
        self.moves = MethodMoves(
            versions=self.versions,
            processes=self.processes,
            register=self.register,
            decisions=self.decisions.requests,
            ledger=self.ledger,
            objects=self.objects,
            work=self.persistence,
        )
        self.review = ReviewMovesHandler(
            self.measures,
            self.objects,
            self.ledger,
            self.persistence,
            self.clock,
            self.decisions.requests,
            PRICES,
        )

    async def setup(self) -> Moving:
        await self.people.directory.add(TENANT, STARTER, (TENANT,))
        await self.people.directory.add(TENANT, OWNER, (TENANT,), roles=("owner",))
        await self.register.execute(RegisterProcessVersion(bundle(), tenant=TENANT, by=STARTER))
        return self

    async def decide(self, request_id: str, option: str) -> ProcessVersion | None:
        await self.decisions.answer.execute(
            AnswerRequest(tenant=TENANT, request_id=request_id, identity=OWNER, option=option)
        )
        await self.decisions.confirm.execute(
            ConfirmRequest(tenant=TENANT, request_id=request_id, identity=OWNER)
        )
        return await self.moves.decided(TENANT, request_id)

    async def entries(self) -> list[LedgerEntry]:
        async with self.persistence.transaction(TENANT):
            return list(await self.ledger.entries(TENANT))

    async def version(self, ref: str) -> ProcessVersion:
        async with self.persistence.transaction(TENANT):
            found = await self.versions.get(TENANT, ref)
        assert found is not None, ref
        return found

    async def active(self) -> str:
        async with self.persistence.transaction(TENANT):
            found = await self.processes.get(TENANT, "triage")
        assert found is not None and found.active_version is not None
        return f"triage@{found.active_version}"

    async def run_of(
        self, version: ProcessVersion, a: float, b: float, *, confidence: float, kind: str
    ) -> Run:
        """One case on a version: the predictor answers `kind` at `confidence`, the language
        model answers `kind` too, should the case reach it. The bench answers as it predicts."""
        if self.trial is not None:
            self.trial.script = (
                InnerStep(
                    "predict",
                    compute_seconds=self.predict_seconds,
                    artifacts=(("predictions", predictions([kind], confidence)),),
                ),
            )
        self.model.answers[f"a={a} b={b} note=n"] = kind
        plan = Plan(
            id="pln_moved",
            command_id="cmd_moved",
            goal="sort a request",
            autonomy_level=version.autonomy_level,
            steps=version.ordered(),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=STARTER, at=self.clock.now()),
        )
        run = await self.engine.start(
            StartRun(
                plan=plan,
                work=version.work,
                budget=BUDGET,
                process_version=version.ref,
                actor=STARTER,
                tenant=TENANT,
                inputs={"a": a, "b": b, "note": "n"},
            )
        )
        assert run.state is RunState.FINISHED, run.reason
        return run

    async def result(self, run: Run) -> dict[str, Any]:
        checkpoint = run.step_run("classify").checkpoint
        assert checkpoint is not None and checkpoint.result_digest is not None
        content = await self.objects.get(checkpoint.result_digest)
        assert content is not None
        document: dict[str, Any] = json.loads(content)
        return document


async def proposed(
    predict_seconds: float = 0.5, workers: Sequence[Worker] | None = None
) -> tuple[Moving, str]:
    """A world whose step was proposed a move, and the request that proposes it."""
    history = separable(540)
    labels = [
        maturation.Case(run_id=f"run_{n + 1:04d}", result=kind, label=kind, features=features)
        for n, (features, kind) in enumerate(history)
    ]
    _, held = maturation.split(labels)
    w = await Moving(
        [c.label for c in held], predict_seconds=predict_seconds, workers=workers
    ).setup()
    await w.history(history)
    (outcome,) = await w.propose.execute(ProposeMoves(TENANT, actor=STARTER, budget=BUDGET))
    assert outcome.proposed and outcome.request_id is not None, outcome.findings
    return w, outcome.request_id


async def moved(
    predict_seconds: float = 0.5, workers: Sequence[Worker] | None = None
) -> tuple[Moving, str, ProcessVersion]:
    w, request = await proposed(predict_seconds, workers)
    version = await w.decide(request, "A")
    assert version is not None
    return w, request, version


# --- accepting registers a new version, and the replaced one stays ------------------------------


async def test_accepting_the_proposal_registers_a_version_with_the_step_on_the_trained_model() -> (
    None
):
    w, request = await proposed()
    before = await w.version("triage@1")
    version = await w.decide(request, "A")
    assert version is not None and version.ref == "triage@2"
    assert await w.active() == "triage@2"
    (step,) = version.steps
    assert step.method is Method.ML
    work = version.work["classify"]
    digest = work["model"]["digest"]
    assert step.model == maturation.model_ref("classify", digest)
    assert step.fallback is not None and step.fallback.to is Method.LLM
    assert step.fallback.when == f"confidence < {maturation.FALLBACK_AT:g}"
    assert work["fallback"]["prompt"] == WORK["prompt"], "the language model it ran on"
    assert work["dataset"] == {"values": WORK["values"], "features": ["a", "b"]}
    assert [r.method for r in step.rejected][-1] is Method.LLM
    evaluation = work["evaluation"]
    assert evaluation["model_digest"] == digest and evaluation["held_out"] == 108
    assert evaluation["agreement"] == 1.0 and evaluation["proposal"] == request
    # The replaced version stays registered and unchanged.
    assert await w.version("triage@1") == before
    moved_entry = _entry(await w.entries(), maturation.MOVED)
    assert moved_entry.refs.actor == OWNER and moved_entry.refs.decision_request_id == request
    assert moved_entry.refs.process_version == "triage@2"
    # Applied twice, the same proposal gives the same version.
    assert (await w.moves.apply(TENANT, request)).ref == "triage@2"
    assert len([e for e in await w.entries() if e.kind == maturation.MOVED]) == 1


async def test_nothing_is_moved_before_a_person_accepts_or_when_the_answer_keeps_the_step() -> None:
    w, request = await proposed()
    with pytest.raises(MoveError, match="a person decides the move") as undecided:
        await w.moves.apply(TENANT, request)
    assert undecided.value.kind == "undecided"
    assert await w.decide(request, "B") is None
    with pytest.raises(MoveError) as declined:
        await w.moves.apply(TENANT, request)
    assert declined.value.kind == "declined"
    assert await w.active() == "triage@1"
    assert maturation.MOVED not in [e.kind for e in await w.entries()]


async def test_a_decision_that_is_no_proposal_to_move_changes_nothing() -> None:
    w, _ = await proposed()
    assert await w.moves.decided(TENANT, "dr_something_else") is None
    assert await w.active() == "triage@1"


# --- the version registers only with the model's evaluation -------------------------------------


async def test_a_version_without_the_models_evaluation_is_refused() -> None:
    w, _, version = await moved()
    document = bundle_of(version, as_version="9", author=None, reason="a test")
    (step,) = document["steps"]
    del step["work"]["evaluation"]
    with pytest.raises(InvalidProcess, match="registers only with the model's evaluation"):
        await w.register.execute(RegisterProcessVersion(document, tenant=TENANT))
    step["work"]["evaluation"] = {
        **version.work["classify"]["evaluation"],
        "model_digest": "sha256:" + "b" * 64,
    }
    with pytest.raises(InvalidProcess, match="registers only with its own evaluation"):
        await w.register.execute(RegisterProcessVersion(document, tenant=TENANT))
    step["work"]["evaluation"] = {**version.work["classify"]["evaluation"], "agreement": 0.94}
    with pytest.raises(InvalidProcess, match="below 95%"):
        await w.register.execute(RegisterProcessVersion(document, tenant=TENANT))
    assert MIN_AGREEMENT == maturation.MIN_AGREEMENT, "registration holds the proposal's floor"
    assert await w.active() == "triage@2"


# --- a run of the new version: the trained model, or the language model below the threshold ----


async def test_a_sure_case_is_answered_by_the_model_and_an_unsure_one_by_the_llm() -> None:
    w, _, version = await moved()
    calls = len(w.model.prompts)
    sure = await w.run_of(version, 10.2, 0.3, confidence=maturation.FALLBACK_AT, kind="k1")
    result = await w.result(sure)
    assert result["text"] == "k1" and result["answered_by"] == "ml"
    assert result["fell_back"] is False and result["model_digest"].startswith("sha256:")
    assert len(w.model.prompts) == calls, "the language model was not asked"
    used = sure.step_run("classify").consumption
    assert used is not None and used.compute_seconds and not used.tokens_in

    unsure = await w.run_of(version, 0.1, 10.4, confidence=0.6, kind="k2")
    result = await w.result(unsure)
    assert result["text"] == "k2" and result["answered_by"] == "llm"
    assert result["fell_back"] is True and result["fallback_model"] == "fake-model@1"
    assert result["confidence"] == 0.6 and result["threshold"] == "confidence < 0.9"
    assert w.model.prompts[-1].user == "a=0.1 b=10.4 note=n", "the same prompt as before"
    used = unsure.step_run("classify").consumption
    assert used is not None and used.compute_seconds and used.tokens_in, "both were used"


async def test_the_same_case_on_the_moved_step_gives_the_same_result() -> None:
    w, _, version = await moved()
    one = await w.run_of(version, 10.2, 0.3, confidence=0.97, kind="k1")
    two = await w.run_of(version, 10.2, 0.3, confidence=0.97, kind="k1")
    first, second = one.step_run("classify").checkpoint, two.step_run("classify").checkpoint
    assert first is not None and second is not None
    assert first.result_digest == second.result_digest, "reproducible at the pinned model"


# --- the move is measured ------------------------------------------------------------------------


async def cases_on(w: Moving, version: ProcessVersion, count: int, unsure_every: int) -> None:
    for n in range(count):
        kind = f"k{n % 3}"
        corner = ((0.0, 0.0), (10.0, 0.0), (0.0, 10.0))[n % 3]
        a, b = corner[0] + (n % 7) / 10, corner[1] + (n % 5) / 10
        confidence = 0.5 if n % unsure_every == 0 else 0.97
        await w.run_of(version, a, b, confidence=confidence, kind=kind)


async def test_over_its_first_100_cases_a_move_is_measured_beside_the_version_it_replaced() -> None:
    w, request, version = await moved()
    await cases_on(w, version, 40, unsure_every=10)
    (measuring,) = await w.review.execute(TENANT)
    assert measuring.verdict == "measuring" and measuring.cases == 40
    assert maturation.MEASURED not in [e.kind for e in await w.entries()]

    await cases_on(w, version, 70, unsure_every=10)
    (review,) = await w.review.execute(TENANT)
    assert review.verdict == "cheaper" and review.cases == maturation.MOVE_CASES
    assert review.fell_back == 10 and review.fallback_share == pytest.approx(0.1)
    assert review.replaced_cases == 540
    assert review.cost_per_case is not None and review.replaced_cost_per_case is not None
    # The numbers of the roadmap's criterion: measurably cheaper per case.
    llm = review.replaced_cost_per_case
    trained = 0.5 * 0.00002
    assert review.cost_per_case == pytest.approx(trained + 0.1 * llm, rel=1e-6)
    assert review.cost_per_case < llm / 2
    assert review.move.request_id == request and review.rollback_request is None
    entry = _entry(await w.entries(), maturation.MEASURED)
    assert entry.outcome == "cheaper" and entry.refs.process_version == version.ref
    assert entry.refs.actor is None, "Taktus measured on its own"
    # Measured once: the verdict is read back, not recomputed.
    await cases_on(w, version, 3, unsure_every=1)
    (again,) = await w.review.execute(TENANT)
    assert again == review
    assert len([e for e in await w.entries() if e.kind == maturation.MEASURED]) == 1
    text = json.dumps(review.document())
    assert OWNER not in text and STARTER not in text, "no measure names a person"


async def test_a_move_that_is_not_cheaper_is_reported_with_a_proposal_to_roll_back() -> None:
    w, _, version = await moved()
    # Every case falls back: it pays the trained model and the language model.
    await cases_on(w, version, maturation.MOVE_CASES, unsure_every=1)
    (review,) = await w.review.execute(TENANT)
    assert review.verdict == "not_cheaper" and review.fallback_share == 1.0
    assert review.cost_per_case is not None and review.replaced_cost_per_case is not None
    assert review.cost_per_case >= review.replaced_cost_per_case
    assert review.rollback_request is not None
    async with w.persistence.transaction(TENANT):
        request = await w.requests.get(TENANT, review.rollback_request)
    assert request is not None and request.decider == "owner"
    assert "did not make the step cheaper" in request.request.situation
    # Accepted, the proposal rolls the move back.
    restored = await w.decide(review.rollback_request, "A")
    assert restored is not None and restored.ref == "triage@3"
    assert await w.active() == "triage@3"
    assert restored.steps[0].method is Method.LLM


# --- rolling back is one act ---------------------------------------------------------------------


async def test_rolling_back_makes_the_predecessor_current_again_as_a_new_version() -> None:
    w, request, version = await moved()
    restored = await w.moves.rollback(TENANT, "triage", by=OWNER)
    assert restored.ref == "triage@3" and await w.active() == "triage@3"
    original = await w.version("triage@1")
    assert restored.steps == original.steps and restored.work == original.work
    assert await w.version("triage@2") == version, "the moved version stays registered"
    kinds = [e.kind for e in await w.entries()]
    assert "process.rolled_back" in kinds and maturation.ROLLED_BACK in kinds
    rolled = _entry(await w.entries(), maturation.ROLLED_BACK)
    assert rolled.refs.actor == OWNER and rolled.refs.decision_request_id == request
    # Only a move whose version is current is rolled back.
    with pytest.raises(MoveError, match="not a version a step was moved"):
        await w.moves.rollback(TENANT, "triage", by=OWNER)
    run = await w.run_of(restored, 10.2, 0.3, confidence=0.97, kind="k1")
    assert run.step("classify").method is Method.LLM


def _entry(entries: list[LedgerEntry], kind: str) -> LedgerEntry:
    return next(e for e in reversed(entries) if e.kind == kind)
