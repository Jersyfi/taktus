"""Method maturation: a step measured, the evidence floor, and what a proposal must show
(ADR-0084, issue #217).

A **case** is one run of a step that succeeded: what it read and what it produced. A **label**
is the result taken as correct: the language model's answer, or a person's correction of it
where a person corrected it.

Three questions are answered here, each by a rule:

1. **What a step costs and how it behaves**, from what was recorded of its cases: the money per
   case at the price table, the duration, how often a person corrected the result, and how far
   the results spread. The measures belong to the step. None names a person (principle 14).
2. **Whether a step on a language model is a candidate** for a trained classifier: its labels
   fall into at most 50 classes, there are at least 500 labelled cases and at least 20 in every
   class, and every case gives the same numbers to learn from.
3. **Whether a trained candidate is evidence enough for a proposal**: it agrees with the labels
   on at least 95 % of the cases held out from its training, its measured cost per case is lower
   than the language model's, and two trainings on the same cases gave the same model.

The numbers are DEC-0164's provisional answer, Option A. They change with the owner's answer.

Pure: cases in, measures and findings out.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import Field

from taktus.shared.v1 import ExactnessClass, Method, Value

MAX_CLASSES = 50
MIN_CASES = 500
MIN_PER_CLASS = 20
HOLDOUT = 0.2
"""The share of every class held out from the training and used only to measure it."""
MIN_AGREEMENT = 0.95
FALLBACK_AT = 0.9
"""The confidence below which the moved step would hand a case back to the language model it
runs on now: the threshold `docs/architecture/methods.md` §2 shows. The person who accepts the
proposal accepts it with this number or changes it."""
LABEL = "label"
"""The label column of the cases a training reads. A feature of that name is renamed."""
CORRECTED = "step.corrected"
"""The ledger kind of a person's correction of a step's result."""
ALLOWED = ExactnessClass.SOURCED
"""The strictest class a step on a trained model may carry: `exact` admits rule and statistics
only (ADR-0014). `sourced` asks for a check against the source besides (UC-4.13)."""


class Case(Value):
    """One run of a step that succeeded, as maturation reads it."""

    run_id: str = Field(min_length=1)
    features: Mapping[str, float] = Field(default_factory=dict)
    """The numbers the step read, by the dotted path of the value that held them."""
    left_out: tuple[str, ...] = ()
    """The values the step read that are not numbers: a classifier on them needs embeddings
    (#210), so they are named and not learned from."""
    result: str
    """What the step produced: the answer's text for a language model, the result's digest for
    every other method."""
    label: str
    """The result taken as correct: the person's correction where there is one."""
    corrected: bool = False
    cost: float | None = None
    """The money the case cost at the price table; None when it cannot be priced."""
    unpriced: tuple[str, ...] = ()
    """What could not be priced, and why."""
    seconds: float | None = Field(default=None, ge=0)
    """How long the step ran."""


class Measures(Value):
    """A step's measures, from its own records. Nothing here names a person."""

    process_version: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    method: Method
    cases: int = Field(ge=0)
    cost_per_case: float | None = None
    """Money per case at the price table; None when any case could not be priced."""
    currency: str | None = None
    unpriced: tuple[str, ...] = ()
    seconds_per_case: float | None = None
    corrected: int = Field(default=0, ge=0)
    """How many cases a person corrected: a count, never who."""
    correction_rate: float | None = None
    distinct_results: int = Field(default=0, ge=0)
    """How many different results the cases produced."""
    commonest_share: float | None = None
    """The share of cases that produced the commonest result. With `distinct_results` it is the
    spread: 1.0 is a step that always answers the same."""


def numbers(value: Any, path: str = "") -> tuple[dict[str, float], tuple[str, ...]]:
    """The numbers a step read, by the dotted path of each, and the paths of what it read that
    is not a number. A truth value is not a number here, nor is one that is not finite."""
    found: dict[str, float] = {}
    left_out: list[str] = []
    if isinstance(value, Mapping):
        for key in sorted(value):
            inner, rest = numbers(value[key], f"{path}.{key}" if path else str(key))
            found.update(inner)
            left_out.extend(rest)
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            inner, rest = numbers(item, f"{path}.{index}" if path else str(index))
            found.update(inner)
            left_out.extend(rest)
    elif isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value):
        found[path or "value"] = float(value)
    elif value is not None:
        left_out.append(path or "value")
    return found, tuple(left_out)


def measure(
    process_version: str,
    step_id: str,
    method: Method,
    cases: Sequence[Case],
    currency: str | None,
) -> Measures:
    """The measures of one step over its cases."""
    count = len(cases)
    unpriced = sorted({reason for case in cases for reason in case.unpriced})
    priced = [case.cost for case in cases if case.cost is not None]
    cost = None if not count or unpriced or len(priced) != count else math.fsum(priced) / count
    durations = [case.seconds for case in cases if case.seconds is not None]
    corrected = sum(1 for case in cases if case.corrected)
    results = Counter(case.result for case in cases)
    return Measures(
        process_version=process_version,
        step_id=step_id,
        method=method,
        cases=count,
        cost_per_case=None if cost is None else round(cost, 9),
        currency=currency if cost is not None else None,
        unpriced=tuple(unpriced),
        seconds_per_case=round(math.fsum(durations) / len(durations), 6) if durations else None,
        corrected=corrected,
        correction_rate=round(corrected / count, 6) if count else None,
        distinct_results=len(results),
        commonest_share=round(results.most_common(1)[0][1] / count, 6) if count else None,
    )


class Candidacy(Value):
    """Whether a step's cases reach the floor a training needs, and what was found below it."""

    candidate: bool
    findings: tuple[str, ...] = ()
    """Why the step is not a candidate; empty when it is."""
    classes: Mapping[str, int] = Field(default_factory=dict)
    """Cases per label."""
    features: tuple[str, ...] = ()
    """The numbers every case gives, which a training learns from."""
    left_out: tuple[str, ...] = ()


def candidacy(method: Method, cases: Sequence[Case]) -> Candidacy:
    """Whether a step on a language model has the cases a trained classifier needs: at most
    `MAX_CLASSES` classes, at least `MIN_CASES` labelled cases, `MIN_PER_CLASS` in every class,
    and the same numbers in every case. Every shortfall is named."""
    findings: list[str] = []
    if method is not Method.LLM:
        findings.append(f"the step runs on {method}; only a step on llm is proposed a move")
    classes = dict(sorted(Counter(case.label for case in cases).items()))
    if len(cases) < MIN_CASES:
        findings.append(f"{len(cases)} labelled case(s), fewer than {MIN_CASES}")
    if len(classes) > MAX_CLASSES:
        findings.append(f"{len(classes)} classes, more than {MAX_CLASSES}")
    if len(classes) < 2:
        findings.append("fewer than two classes: there is nothing to tell apart")
    small = [f"{label!r} ({n})" for label, n in classes.items() if n < MIN_PER_CLASS]
    if small and len(classes) <= MAX_CLASSES:
        findings.append(f"fewer than {MIN_PER_CLASS} cases in class(es) {', '.join(small)}")
    shapes = {tuple(sorted(case.features)) for case in cases}
    features = next(iter(shapes)) if len(shapes) == 1 else ()
    if len(shapes) > 1:
        findings.append("the cases do not all give the same numbers to learn from")
    elif cases and not features:
        findings.append(
            "the step reads no number to learn from: a classifier on text needs embeddings (#210)"
        )
    left_out = tuple(sorted({name for case in cases for name in case.left_out}))
    return Candidacy(
        candidate=not findings,
        findings=tuple(findings),
        classes=classes,
        features=features,
        left_out=left_out,
    )


def split(cases: Sequence[Case], seed: int = 0) -> tuple[tuple[Case, ...], tuple[Case, ...]]:
    """The cases to train on and the cases held out, `HOLDOUT` of every class. The order is
    drawn from the seed and each case's run, never from the order the cases were read in, so
    the same cases give the same split."""
    by_class: dict[str, list[Case]] = {}
    for case in cases:
        by_class.setdefault(case.label, []).append(case)
    train: list[Case] = []
    held: list[Case] = []
    for label in sorted(by_class):
        ordered = sorted(
            by_class[label],
            key=lambda c: hashlib.sha256(f"{seed}:{c.run_id}".encode()).hexdigest(),
        )
        cut = max(1, round(len(ordered) * HOLDOUT))
        held.extend(ordered[:cut])
        train.extend(ordered[cut:])
    key = lambda c: c.run_id  # noqa: E731 — the order a dataset is written in
    return tuple(sorted(train, key=key)), tuple(sorted(held, key=key))


def column(name: str) -> str:
    """A feature's column name: never the label's."""
    return f"{name}_" if name == LABEL else name


def dataset(cases: Sequence[Case], features: Sequence[str], *, labelled: bool) -> bytes:
    """The cases as the ML bench reads them: a CSV with a header row, a number in every feature
    column and, where `labelled`, the label last."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow([column(f) for f in features] + ([LABEL] if labelled else []))
    for case in cases:
        writer.writerow(
            [repr(float(case.features[f])) for f in features] + ([case.label] if labelled else [])
        )
    return out.getvalue().encode("utf-8")


def agreement(held: Sequence[Case], predicted: Sequence[str]) -> float:
    """The share of held-out cases on which the model gives the label."""
    if not held or len(held) != len(predicted):
        return 0.0
    agreed = sum(1 for case, label in zip(held, predicted, strict=True) if case.label == label)
    return agreed / len(held)


class Evidence(Value):
    """What a trained candidate showed on cases it was not trained on."""

    held_out: int = Field(ge=0)
    agreement: float = Field(ge=0, le=1)
    below_threshold: float = Field(ge=0, le=1)
    """The share of held-out cases whose confidence is below `FALLBACK_AT`: what the moved step
    would hand back to the language model."""
    llm_cost_per_case: float | None
    ml_cost_per_case: float | None
    currency: str | None
    digests: tuple[str, ...] = Field(min_length=1)
    """The model's digest from each training on the same cases."""

    @property
    def digest(self) -> str:
        return self.digests[0]


def findings(evidence: Evidence) -> tuple[str, ...]:
    """Why the candidate is not evidence enough for a proposal; empty when it is."""
    found: list[str] = []
    if len(set(evidence.digests)) != 1:
        found.append("two trainings on the same cases gave different models: not reproducible")
    if evidence.agreement < MIN_AGREEMENT:
        found.append(
            f"the model agrees with the labels on {percent(evidence.agreement)} of the "
            f"held-out cases, below {percent(MIN_AGREEMENT)}"
        )
    if evidence.llm_cost_per_case is None:
        found.append("the language model's cost per case cannot be priced")
    if evidence.ml_cost_per_case is None:
        found.append("the trained model's cost per case cannot be priced")
    if (
        evidence.llm_cost_per_case is not None
        and evidence.ml_cost_per_case is not None
        and not evidence.ml_cost_per_case < evidence.llm_cost_per_case
    ):
        found.append(
            f"the trained model costs {money(evidence.ml_cost_per_case, evidence.currency)} "
            f"per case, not less than the language model's "
            f"{money(evidence.llm_cost_per_case, evidence.currency)}"
        )
    return tuple(found)


def percent(share: float) -> str:
    return f"{share * 100:.1f} %"


def money(amount: float | None, currency: str | None) -> str:
    if amount is None:
        return "unpriced"
    return f"{amount:.9f}".rstrip("0").rstrip(".") + f" {(currency or '').upper()}".rstrip()


def model_ref(step_id: str, digest: str) -> str:
    """The candidate pinned as `name@version`: named after the step, versioned by the first
    twelve digits of its digest, so the version names the file (until UC-8.6's hub)."""
    return f"{step_id}-clf@{digest.removeprefix('sha256:')[:12]}"


class Proposal(Value):
    """Everything a person reads before deciding the move (DEC-0164, Option A, item 3)."""

    process_version: str
    step_id: str
    exactness: ExactnessClass | None
    """The class the step carries now."""
    cases: int
    classes: Mapping[str, int]
    features: tuple[str, ...]
    left_out: tuple[str, ...]
    evidence: Evidence
    model: str
    """The candidate as `name@version`."""
    threshold: float = FALLBACK_AT
    allowed: ExactnessClass = ALLOWED
    training_run: str
    trial_run: str

    def situation(self) -> str:
        classes = ", ".join(f"{label} ({n})" for label, n in self.classes.items())
        left_out = (
            f" It does not read {', '.join(self.left_out)}, which are not numbers."
            if self.left_out
            else ""
        )
        e = self.evidence
        return (
            f"Step {self.step_id} of {self.process_version} runs on a language model. Across "
            f"{self.cases} labelled cases it gave {len(self.classes)} classes: {classes}. A "
            f"classifier trained on the ML bench on {self.cases - e.held_out} of them agrees "
            f"with the labels on {percent(e.agreement)} of the {e.held_out} cases held out "
            f"from its training. Measured per case, the language model costs "
            f"{money(e.llm_cost_per_case, e.currency)} and the trained model "
            f"{money(e.ml_cost_per_case, e.currency)}. Trained twice on the same cases, the "
            f"model has the same digest. It reads {', '.join(self.features)}.{left_out} The "
            f"model is {self.model}, digest {e.digest}, kept by run {self.training_run}; the "
            f"trial is run {self.trial_run}."
        )

    def question(self) -> str:
        return (
            f"Shall step {self.step_id} of {self.process_version} move from the language model "
            f"to the trained model {self.model}?"
        )

    def options(self) -> tuple[dict[str, Any], dict[str, Any]]:
        e = self.evidence
        return (
            {
                "id": "A",
                "proposal": (
                    f"Move step {self.step_id} to {self.model}, pinned by digest {e.digest}. "
                    f"Below confidence {self.threshold:g} it hands the case back to the "
                    f"language model it runs on now; on the held-out cases that was "
                    f"{percent(e.below_threshold)}."
                ),
                "consequence": (
                    f"A new version of the process. The step is reproducible at the pinned "
                    f"model and may carry an exactness class up to {self.allowed} "
                    f"(now {self.exactness or 'none'}); {self.allowed} asks for a check "
                    f"against the source besides. It can be rolled back in one act."
                ),
                "recommended": True,
                "reason": (
                    f"The evidence meets the floor: at least {MIN_CASES} cases and "
                    f"{MIN_PER_CLASS} per class, {percent(MIN_AGREEMENT)} agreement on held-out "
                    f"cases, a lower measured cost per case, the same model twice."
                ),
            },
            {
                "id": "B",
                "proposal": f"Keep step {self.step_id} on the language model.",
                "consequence": (
                    "The step keeps costing what it costs, and its answers keep varying. "
                    "Taktus proposes again when the evidence changes."
                ),
                "recommended": False,
            },
        )

    def request_id(self, tenant: str) -> str:
        """The same step and the same model give the same request: a proposal raised twice is
        met, not repeated."""
        key = f"{tenant}|{self.process_version}|{self.step_id}|{self.evidence.digest}"
        return "dr_move_" + hashlib.sha256(key.encode()).hexdigest()[:24]
