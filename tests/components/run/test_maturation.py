"""Method maturation against fakes: a step measured from the run history it left, the evidence
floor, and a proposal raised to a person, never applied (ADR-0084, issue #217, DEC-0164
provisionally Option A).

The run history is written by the run engine itself: a step on a scripted language model, run
once per case. The trainings and the trials run on scripted workers; what the ML bench itself
trains and predicts is `tests/workers/test_maturation_on_the_bench.py`'s.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest
from fakes import FakeIdentifiers, FakeModel, FakeWorker, InnerStep
from fakes.clock import FakeClock
from fakes.identity import directory
from fakes.maturity import VERIFIED

from taktus.adapters.driven.memory import (
    MemoryObjectStore,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.decision.domain.model import Request
from taktus.components.run.application.query import StepMeasures
from taktus.components.run.application.service import (
    CorrectResult,
    CorrectResultHandler,
    EngineOptions,
    ProposeMoves,
    ProposeMovesHandler,
    RunEngine,
    StartRun,
)
from taktus.components.run.domain.model import Run, RunError, RunState
from taktus.components.run.domain.service import maturation
from taktus.components.run.domain.service.maturation import Case, Evidence
from taktus.composition.decisions import decision_wiring
from taktus.ports.model import Completion, PriceTable, Prompt
from taktus.ports.worker import ComputeLimit, Limits, Worker
from taktus.shared.v1 import (
    Commissioned,
    ExactnessClass,
    Fallback,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    PriceKinds,
    Step,
)

from .test_engine import AT, TENANT

STARTER = "idn_starter"
CORRECTOR = "idn_corrector"
PROCESS = "triage@1"
BUDGET = Limits(compute=ComputeLimit(seconds=600, resource_class="cpu.small"))
PRICES = PriceTable(
    version="test-1",
    valid_from=AT,
    currency="eur",
    unit_tokens=1_000_000,
    source="a test: no provider's prices",
    prices={"fake-model@1": {"input": 3.0, "output": 15.0}},
    compute={"cpu.small": 0.00002},
)
FEATURES = ("a", "b")
CLASSIFY = Step(
    id="classify",
    method=Method.LLM,
    reason="sorts each request into a kind; no rule was known for it",
    rejected=(),
    exactness=ExactnessClass.TOLERANT,
    fallback=Fallback(when="the answer is not one of the kinds", to=Method.HUMAN),
)
WORK = {
    "purpose": "triage",
    "system": "Answer with the kind only.",
    "prompt": "a=${a} b=${b} note=${note}",
    "values": {
        "a": {"$input": "a"},
        "b": {"$input": "b"},
        "note": {"$input": "note"},
    },
    "max_output_tokens": 8,
}


@dataclass
class Classifying(FakeModel):
    """A language model that answers each prompt with the kind the test assigned it."""

    answers: dict[str, str] = field(default_factory=dict)

    async def complete(self, prompt: Prompt) -> Completion:
        self.prompts.append(prompt)
        text = self.answers.get(prompt.user, "k0")
        tokens_in = len(prompt.user.split()) + len((prompt.system or "").split())
        return Completion(
            text=text,
            model=self.name,
            tokens_in=tokens_in,
            tokens_out=1,
            by_kind=PriceKinds(input=tokens_in, output=1),
            finish="stop",
        )


class World:
    """An instance in memory: the run engine with a language model and the workers given, the
    decision component, and maturation over both."""

    def __init__(
        self,
        workers: Sequence[Worker] = (),
        prices: PriceTable | None = PRICES,
        uncalibrated_margin: float = 0.0,
    ):
        self.clock = FakeClock(AT)
        self.people = directory((TENANT,), clock=self.clock)
        self.persistence = self.people.persistence
        self.ledger = self.people.ledger
        self.runs = MemoryRepository(self.persistence, Run)
        self.objects = MemoryObjectStore()
        self.model = Classifying()
        self.decisions = decision_wiring(
            lambda kind: MemoryRepository(self.persistence, kind),
            self.persistence,
            self.ledger,
            self.clock,
            self.people.directory,
        )
        self.requests = MemoryRepository(self.persistence, Request)
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.runs,
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=MemoryProvenanceStore(self.persistence),
            workers=StaticWorkerPool(
                [(f"worker.fake.{n}", w) for n, w in enumerate(workers or [FakeWorker()])]
            ),
            clock=self.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            # The mechanics are tested at the estimate a fake gives; a real worker is reserved
            # what an uncalibrated one is (DEC-0034).
            options=EngineOptions(uncalibrated_margin=uncalibrated_margin, prices=prices),
            models=StaticModelPool([("model.fake", ["triage"], self.model, "fake-model@1")]),
        )
        self.measures = StepMeasures(self.runs, self.ledger, self.objects, self.persistence, prices)
        self.propose = ProposeMovesHandler(
            self.engine,
            self.measures,
            self.objects,
            self.ledger,
            self.persistence,
            self.clock,
            self.decisions.requests,
            prices,
        )
        self.correct = CorrectResultHandler(self.runs, self.persistence, self.objects, self.ledger)

    async def case(self, features: dict[str, float], kind: str, note: str = "n") -> Run:
        """One run of the step on the language model, which answers `kind`."""
        prompt = f"a={features['a']} b={features['b']} note={note}"
        self.model.answers[prompt] = kind
        plan = Plan(
            id="pln_triage",
            command_id="cmd_triage",
            goal="sort a request",
            autonomy_level=3,
            steps=(CLASSIFY,),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=STARTER, at=AT),
        )
        run = await self.engine.start(
            StartRun(
                plan=plan,
                work={"classify": WORK},
                budget=BUDGET,
                process_version=PROCESS,
                actor=STARTER,
                tenant=TENANT,
                inputs={**features, "note": note},
            )
        )
        assert run.state is RunState.FINISHED, run.reason
        return run

    async def history(self, cases: Sequence[tuple[dict[str, float], str]]) -> list[Run]:
        return [await self.case(features, kind) for features, kind in cases]

    async def proposals(self) -> list[Request]:
        async with self.persistence.transaction(TENANT):
            return list(await self.requests.list(TENANT))

    async def kinds(self) -> list[str]:
        async with self.persistence.transaction(TENANT):
            return [e.kind for e in await self.ledger.entries(TENANT)]


def separable(count: int) -> list[tuple[dict[str, float], str]]:
    """`count` cases in three kinds, each around its own corner — k0 near (0, 0), k1 near
    (10, 0), k2 near (0, 10): a kind is told from its numbers by a straight line, as a linear
    classifier can learn."""
    corners = ((0.0, 0.0), (10.0, 0.0), (0.0, 10.0))
    found: list[tuple[dict[str, float], str]] = []
    for n in range(count):
        a, b = corners[n % 3]
        found.append(({"a": a + (n % 7) / 10, "b": b + (n % 5) / 10}, f"k{n % 3}"))
    return found


def cases(sizes: dict[str, int], features: Sequence[str] = FEATURES) -> list[Case]:
    found: list[Case] = []
    for label, size in sizes.items():
        for n in range(size):
            found.append(
                Case(
                    run_id=f"run_{label}_{n:04d}",
                    features={f: float(n) for f in features},
                    result=label,
                    label=label,
                )
            )
    return found


# --- measured per step, never per person --------------------------------------------------------


async def test_a_steps_measures_are_read_back_from_the_run_history_it_wrote() -> None:
    w = World()
    runs = await w.history(separable(6))
    corrected = await w.correct.execute(
        CorrectResult(TENANT, runs[0].id, "classify", "k2", actor=CORRECTOR)
    )
    measures = {m.step_id: m for m in await w.measures.measures(TENANT)}
    m = measures["classify"]
    assert m.process_version == PROCESS and m.method is Method.LLM
    assert m.cases == 6
    used = [r.step_run("classify").consumption for r in runs]
    expected = sum(
        (c.tokens_in * 3.0 + c.tokens_out * 15.0) / 1_000_000 for c in used if c is not None
    )
    assert m.cost_per_case == pytest.approx(expected / 6) and m.currency == "eur"
    assert m.seconds_per_case is not None and m.seconds_per_case > 0
    assert m.corrected == 1 and m.correction_rate == pytest.approx(1 / 6, abs=1e-6)
    assert m.distinct_results == 3 and m.commonest_share == pytest.approx(2 / 6, abs=1e-6)
    # The correction is the label of its case; the case's result stays the model's answer.
    step = next(s for s in await w.measures.steps(TENANT) if s.step_id == "classify")
    first = next(c for c in step.cases if c.run_id == runs[0].id)
    assert (first.result, first.label, first.corrected) == ("k0", "k2", True)
    assert dict(first.features) == {"a": 0.0, "b": 0.0} and first.left_out == ("note",)
    # No measure names a person: neither who started the runs nor who corrected one.
    text = json.dumps([x.document() for x in measures.values()], default=str)
    assert CORRECTOR not in text and STARTER not in text
    async with w.persistence.transaction(TENANT):
        entry = next(e for e in await w.ledger.entries(TENANT) if e.kind == "step.corrected")
    assert entry.refs.actor == CORRECTOR and entry.content_digest == corrected


async def test_a_step_without_a_price_is_measured_and_its_cost_is_unpriced() -> None:
    w = World(prices=None)
    await w.history(separable(2))
    (m,) = await w.measures.measures(TENANT)
    assert m.cases == 2 and m.cost_per_case is None
    assert m.unpriced == ("no price table is configured",)


async def test_only_a_result_can_be_corrected() -> None:
    w = World()
    (run,) = await w.history(separable(1))
    with pytest.raises(RunError, match="no step"):
        await w.correct.execute(CorrectResult(TENANT, run.id, "nope", "k1", actor=CORRECTOR))
    with pytest.raises(RunError, match="no run"):
        await w.correct.execute(CorrectResult(TENANT, "run_x", "classify", "k1", actor=CORRECTOR))
    with pytest.raises(RunError, match="names what"):
        await w.correct.execute(CorrectResult(TENANT, run.id, "classify", " ", actor=CORRECTOR))


# --- a candidate only on evidence -----------------------------------------------------------------


def test_a_step_with_500_cases_and_20_in_every_class_is_a_candidate() -> None:
    found = maturation.candidacy(Method.LLM, cases({"a": 460, "b": 20, "c": 20}))
    assert found.candidate and found.findings == ()
    assert found.classes == {"a": 460, "b": 20, "c": 20} and found.features == FEATURES


def test_499_cases_or_one_class_at_19_is_no_candidate() -> None:
    few = maturation.candidacy(Method.LLM, cases({"a": 459, "b": 20, "c": 20}))
    assert not few.candidate and few.findings == ("499 labelled case(s), fewer than 500",)
    small = maturation.candidacy(Method.LLM, cases({"a": 461, "b": 20, "c": 19}))
    assert not small.candidate
    assert small.findings == ("fewer than 20 cases in class(es) 'c' (19)",)


def test_more_than_50_classes_another_method_or_no_numbers_is_no_candidate() -> None:
    many = maturation.candidacy(Method.LLM, cases({f"k{n}": 20 for n in range(51)}))
    assert many.findings == ("51 classes, more than 50",)
    rule = maturation.candidacy(Method.RULE, cases({"a": 480, "b": 20}))
    assert rule.findings == ("the step runs on rule; only a step on llm is proposed a move",)
    text = maturation.candidacy(Method.LLM, cases({"a": 480, "b": 20}, features=()))
    assert not text.candidate and "embeddings (#210)" in text.findings[0]


def test_the_held_out_cases_are_a_fifth_of_every_class_drawn_the_same_every_time() -> None:
    given = cases({"a": 400, "b": 100})
    train, held = maturation.split(given)
    assert len(held) == 100 and len(train) == 400
    assert sum(1 for c in held if c.label == "b") == 20
    assert not {c.run_id for c in train} & {c.run_id for c in held}
    assert maturation.split(list(reversed(given))) == (train, held)
    assert maturation.split(given, seed=1) != (train, held)


def evidence(**changes: Any) -> Evidence:
    base: dict[str, Any] = {
        "held_out": 100,
        "agreement": 0.95,
        "below_threshold": 0.02,
        "llm_cost_per_case": 0.0004,
        "ml_cost_per_case": 0.00001,
        "currency": "eur",
        "digests": ("sha256:" + "a" * 64,) * 2,
    }
    return Evidence.model_validate({**base, **changes})


def test_a_proposal_needs_95_percent_a_lower_cost_and_the_same_model_twice() -> None:
    assert maturation.findings(evidence()) == ()
    assert maturation.findings(evidence(agreement=0.94)) == (
        "the model agrees with the labels on 94.0 % of the held-out cases, below 95.0 %",
    )
    (equal,) = maturation.findings(evidence(ml_cost_per_case=0.0004))
    assert "not less than the language model's" in equal
    (twice,) = maturation.findings(evidence(digests=("sha256:" + "a" * 64, "sha256:" + "b" * 64)))
    assert "not reproducible" in twice
    (unpriced,) = maturation.findings(evidence(ml_cost_per_case=None))
    assert "cannot be priced" in unpriced


# --- the proposal is a decision request, never a change -------------------------------------------


MODEL_FILE = b'{"classes": ["k0", "k1", "k2"], "weights": [[1, 0], [0, 1]]}'


def predictions(labels: Sequence[str], confidence: float = 0.97) -> bytes:
    lines = ["row,class,confidence"] + [
        f"{n},{label},{confidence:.6f}" for n, label in enumerate(labels, 1)
    ]
    return ("\n".join(lines) + "\n").encode()


def bench(predicted: Sequence[str], *, predict_seconds: float = 0.5) -> list[FakeWorker]:
    """A worker that trains — the same model file every time — and one that predicts."""
    return [
        FakeWorker(
            capabilities_offered=("data.read", "ml.train", "ml.evaluate"),
            script=(InnerStep("epoch-1", artifacts=(("model", MODEL_FILE),)),),
        ),
        FakeWorker(
            capabilities_offered=("data.read", "ml.predict"),
            script=(
                InnerStep(
                    "predict",
                    compute_seconds=predict_seconds,
                    artifacts=(("predictions", predictions(predicted)),),
                ),
            ),
        ),
    ]


async def candidate_world(agreeing: float = 1.0, predict_seconds: float = 0.5) -> World:
    """A world with 540 cases of the step, whose bench predicts the held-out cases' labels on
    the share `agreeing` of them."""
    history = separable(540)
    labels = [
        maturation.Case(run_id=f"run_{n + 1:04d}", result=kind, label=kind, features=features)
        for n, (features, kind) in enumerate(history)
    ]
    _, held = maturation.split(labels)
    wrong = len(held) - round(len(held) * agreeing)
    predicted = [c.label if n >= wrong else "k9" for n, c in enumerate(held)]
    w = World(workers=bench(predicted, predict_seconds=predict_seconds))
    await w.history(history)
    return w


async def test_a_candidate_is_trained_tried_and_proposed_to_a_person() -> None:
    w = await candidate_world()
    (outcome,) = await w.propose.execute(ProposeMoves(TENANT, actor=STARTER, budget=BUDGET))
    assert outcome.proposed, outcome.findings
    proposal = outcome.proposal
    assert proposal is not None and outcome.request_id is not None
    e = proposal.evidence
    assert proposal.cases == 540 and proposal.classes == {"k0": 180, "k1": 180, "k2": 180}
    assert e.held_out == 108 and e.agreement == 1.0
    assert e.digests[0] == e.digests[1], "trained twice, the same model"
    assert e.ml_cost_per_case == pytest.approx(0.5 * 0.00002)
    assert e.llm_cost_per_case is not None and e.ml_cost_per_case < e.llm_cost_per_case
    assert proposal.model == maturation.model_ref("classify", e.digest)
    assert proposal.features == FEATURES and proposal.left_out == ("note",)
    (request,) = await w.proposals()
    shaped = request.request
    assert request.id == outcome.request_id and request.decider == "owner"
    assert request.anchor is None and str(shaped.class_) == "conceptual"
    assert shaped.raised_by.run == outcome.training_run and shaped.raised_by.step == "train"
    text = shaped.situation + " ".join(o.proposal + (o.consequence or "") for o in shaped.options)
    for stated in (
        "classify",
        PROCESS,
        "540 labelled cases",
        "k0 (180)",
        "100.0 % of the 108 cases held out",
        "0.00001 EUR",
        f"confidence {maturation.FALLBACK_AT:g}",
        "up to sourced",
        proposal.model,
        e.digest,
    ):
        assert stated in text, stated
    recommended = [o for o in shaped.options if o.recommended]
    assert [o.id for o in recommended] == ["A"] and recommended[0].reason
    kinds = await w.kinds()
    assert "decision.raised" in kinds and kinds[-1] == "method.proposed"
    # Raised again, the same proposal is met, not repeated.
    await w.propose.execute(ProposeMoves(TENANT, actor=STARTER, budget=BUDGET))
    assert len(await w.proposals()) == 1


async def test_asked_as_a_change_within_the_frame_it_is_proposed_and_nothing_is_registered() -> (
    None
):
    w = await candidate_world()
    (outcome,) = await w.propose.execute(
        ProposeMoves(TENANT, actor=STARTER, budget=BUDGET, as_change=True)
    )
    assert outcome.proposed and outcome.applied is False
    assert outcome.note is not None and "outside the frame" in outcome.note
    assert len(await w.proposals()) == 1
    kinds = await w.kinds()
    assert not [k for k in kinds if k.startswith("process.")], "no version was registered"
    # Nothing of the proposal ran: the step's runs since are on the language model still.
    run = await w.case({"a": 1.0, "b": 0.1}, "k0")
    assert run.step("classify").method is Method.LLM


async def test_an_agreement_of_94_percent_or_an_equal_cost_proposes_nothing() -> None:
    w = await candidate_world(agreeing=0.94)
    (outcome,) = await w.propose.execute(ProposeMoves(TENANT, actor=STARTER, budget=BUDGET))
    assert not outcome.proposed and await w.proposals() == []
    assert outcome.findings == (
        "the model agrees with the labels on 94.4 % of the held-out cases, below 95.0 %",
    )
    assert (await w.kinds())[-1] == "method.proposed"
    # A trained model that costs as much per case as the language model is no move.
    (llm,) = [
        m.cost_per_case for m in await w.measures.measures(TENANT) if m.process_version == PROCESS
    ]
    assert llm is not None
    w = await candidate_world(predict_seconds=llm / 0.00002)
    (outcome,) = await w.propose.execute(ProposeMoves(TENANT, actor=STARTER, budget=BUDGET))
    assert not outcome.proposed and "not less than" in outcome.findings[0]


async def test_a_step_below_the_floor_is_not_trained() -> None:
    w = World(workers=bench(["k0"]))
    await w.history(separable(30))
    (outcome,) = await w.propose.execute(ProposeMoves(TENANT, actor=STARTER, budget=BUDGET))
    assert not outcome.proposed and outcome.training_run is None
    assert outcome.findings == (
        "30 labelled case(s), fewer than 500",
        "fewer than 20 cases in class(es) 'k0' (10), 'k1' (10), 'k2' (10)",
    )
    assert "method.proposed" not in await w.kinds()
