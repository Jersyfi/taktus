"""A process's evaluation cases and scorers, and an evaluation of a version on them (UC-4.18,
ADR-0134).

A bundle declares `evaluation`: its **cases** — a run's inputs, with a **target** per step, the
result the step should produce — its **scorers**, which hold a step's result to its target and
give a score from 0 to 1, and the **schedule** the cases run on without a change (§1).

A scorer carries a method, its reason, the methods it rejected, an exactness class and a
fallback, as every step does, and is held to the same rules. Its method is `rule` or, where no
rule can score, `llm`: a judge, which rejects `rule` with why and falls back to a rule or a
person (§2).

An **evaluation** runs a version on every case of the process's set and scores what it
produced: the active version beside a proposal (`change`), or the active version alone
(`drift`). It is a record of its own, never a run and never a version (§3, §4).

A **corrected case** is a case proposed from a person's correction of a step's result. It
enters the process's set only once a person confirmed its target (§7).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, ValidationError, model_validator

from taktus.components.process.domain.service import schedule
from taktus.shared.v1 import ExactnessClass, Method, Step, StepId, Value
from taktus.shared.v1.step import Fallback, Rejected

CASE_ID = r"^[a-z0-9][a-z0-9._-]*$"
SCORING_METHODS = frozenset({Method.RULE, Method.LLM})
"""A scorer is a rule, or a language model as judge where no rule can score (ADR-0134 §2)."""
JUDGE_FALLBACKS = frozenset({Method.RULE, Method.HUMAN})


class ScoringRule(Value):
    """One of the four rules a scorer scores by (ADR-0134 §2)."""

    kind: Literal["equals", "contains", "pattern", "overlap"]
    pattern: str | None = Field(default=None, min_length=1)
    """For `pattern`: the regular expression the result's text must match."""

    @model_validator(mode="after")
    def _pattern_where_needed(self) -> ScoringRule:
        if self.kind == "pattern":
            if self.pattern is None:
                raise ValueError("the rule `pattern` names the `pattern` the result must match")
            try:
                re.compile(self.pattern)
            except re.error as error:
                raise ValueError(f"`pattern` is no regular expression: {error}") from error
        elif self.pattern is not None:
            raise ValueError(f"the rule `{self.kind}` takes no `pattern`")
        return self


class Scorer(Value):
    """How a step's result is held to its target, with the method that does it."""

    step: StepId
    method: Method
    reason: str = Field(min_length=1)
    rejected: tuple[Rejected, ...] = ()
    exactness: ExactnessClass
    fallback: Fallback | None = None
    rule: ScoringRule | None = None
    """The rule a `rule` scorer scores by; for a judge, the rule it falls back to."""
    purpose: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]*$")
    """For a judge: the purpose of the model it asks."""
    criterion: str | None = Field(default=None, min_length=1)
    """For a judge: what it asks the model to judge the result by."""

    @model_validator(mode="after")
    def _a_method_of_its_own(self) -> Scorer:
        findings: list[str] = []
        if self.method not in SCORING_METHODS:
            findings.append(
                f"a scorer is a rule, or a language model as judge where no rule can score, "
                f"never {self.method}"
            )
        try:
            Step(
                id=self.step,
                method=self.method,
                reason=self.reason,
                rejected=self.rejected,
                exactness=self.exactness,
                fallback=self.fallback,
            )
        except ValidationError as error:
            findings.extend(item["msg"].removeprefix("Value error, ") for item in error.errors())
        if self.method is Method.RULE:
            if self.rule is None:
                findings.append("a rule scorer names its `rule`")
            if self.purpose is not None or self.criterion is not None:
                findings.append("a rule scorer asks no model: no `purpose`, no `criterion`")
        if self.method is Method.LLM:
            if not any(r.method is Method.RULE for r in self.rejected):
                findings.append(
                    "a judge scores only where no rule can: it rejects `rule` and says why"
                )
            if self.purpose is None or self.criterion is None:
                findings.append("a judge names the `purpose` of its model and its `criterion`")
            if self.fallback is not None:
                if self.fallback.to not in JUDGE_FALLBACKS:
                    findings.append("a judge falls back to a rule or to a person")
                elif self.fallback.to is Method.RULE and self.rule is None:
                    findings.append("a judge that falls back to a rule names that `rule`")
                elif self.fallback.to is Method.HUMAN and self.rule is not None:
                    findings.append("a judge that falls back to a person names no `rule`")
        if findings:
            raise ValueError("; ".join(findings))
        return self

    @property
    def judge(self) -> bool:
        return self.method is Method.LLM


class EvaluationCase(Value):
    """A run's inputs, and the result each named step should produce."""

    id: str = Field(pattern=CASE_ID)
    inputs: Mapping[str, Any] = Field(default_factory=dict)
    targets: Mapping[StepId, Any] = Field(min_length=1)


class EvaluationSpec(Value):
    """What a bundle declares under `evaluation` (ADR-0134 §1)."""

    cases: tuple[EvaluationCase, ...] = ()
    scorers: tuple[Scorer, ...] = Field(min_length=1)
    schedule: str | None = Field(default=None, min_length=1)
    """When the cases run without a change; a schedule as a trigger names one (ADR-0035)."""

    @model_validator(mode="after")
    def _sound(self) -> EvaluationSpec:
        ids = [case.id for case in self.cases]
        if len(set(ids)) != len(ids):
            raise ValueError("an evaluation names every case once")
        if self.schedule is not None:
            schedule.parse(self.schedule)  # an InvalidSchedule is a ValueError and says why
        return self

    def scorers_of(self, step_id: str) -> tuple[Scorer, ...]:
        return tuple(scorer for scorer in self.scorers if scorer.step == step_id)

    @property
    def scored_steps(self) -> frozenset[str]:
        return frozenset(scorer.step for scorer in self.scorers)


class CaseState(StrEnum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    WITHHELD = "withheld"
    """Not proposed: it would keep personal data the tenant does not allow in a case. Nothing of
    the run is kept, only why."""


class CorrectedCase(Value):
    """A case proposed from a person's correction of a step's result (ADR-0134 §7). It names
    the run and the step it was taken from, never the person who corrected."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    process_id: str = Field(min_length=1)
    case: EvaluationCase | None = None
    """None for a withheld one."""
    state: CaseState = CaseState.PROPOSED
    withheld: str | None = Field(default=None, min_length=1)
    """Why it was withheld."""
    source_run: str = Field(min_length=1)
    source_step: StepId
    left_out: tuple[str, ...] = ()
    """The inputs of the run no step reads, left out of the case."""
    proposed_at: datetime
    decided_at: datetime | None = None


class Purpose(StrEnum):
    CHANGE = "change"
    """A proposal held to the active version."""
    DRIFT = "drift"
    """The active version alone, with no change."""


class Side(StrEnum):
    ACTIVE = "active"
    PROPOSED = "proposed"


class Verdict(StrEnum):
    PASSED = "passed"
    REGRESSED = "regressed"
    INCOMPLETE = "incomplete"
    FIRST = "first"
    STEADY = "steady"
    DRIFT = "drift"


OVERRIDABLE = frozenset({Verdict.REGRESSED, Verdict.INCOMPLETE})
"""The verdicts of a change a person may commission against, with a reason."""


class EvaluationState(StrEnum):
    RUNNING = "running"
    """The case runs have not all settled."""
    JUDGING = "judging"
    """The judges' runs have not all settled."""
    SCORED = "scored"


class CaseRun(Value):
    """One case on one side: the run that rehearsed it, or why it was not run, and the runs of
    the judges that scored it, by scorer."""

    case: str = Field(min_length=1)
    side: Side
    run_id: str | None = Field(default=None, min_length=1)
    left_out: str | None = Field(default=None, min_length=1)
    """Why the case was not run; None when it was."""
    judges: Mapping[str, str] = Field(default_factory=dict)
    """The judge's run by scorer key (`<step>#<index>`)."""


class Score(Value):
    """One scorer's score of one case on one side, and how it was reached."""

    scorer: str = Field(min_length=1)
    """`<step>#<index of the scorer in the declaration>`."""
    step: StepId
    method: Method
    exactness: ExactnessClass
    score: float | None = Field(default=None, ge=0, le=1)
    """None where a judge fell back to a person."""
    how: Literal["rule", "judge", "fallback", "person", "no result"]


class CaseResult(Value):
    case: str = Field(min_length=1)
    side: Side
    run_id: str | None = None
    run_state: str | None = None
    score: float | None = Field(default=None, ge=0, le=1)
    """The mean of its scores; None when one of them is None or the case was not run."""
    scores: tuple[Score, ...] = ()
    models: Mapping[str, str] = Field(default_factory=dict)
    """The model that answered each step on a language model, as the provider named it."""
    seconds: float | None = Field(default=None, ge=0)
    tokens_in: int = Field(default=0, ge=0)
    tokens_out: int = Field(default=0, ge=0)
    left_out: str | None = None


class SideResult(Value):
    side: Side
    version: str = Field(min_length=1)
    """The reference the side's runs ran under."""
    score: float | None = Field(default=None, ge=0, le=1)
    """The mean of its cases' scores; None while one has none."""
    cases: int = Field(ge=0)
    unscored: int = Field(ge=0)


class Override(Value):
    """A person's reason for commissioning against a verdict (ADR-0134 §4). Who gave it is the
    actor of `evaluation.overridden`, never a field of it (principle 14)."""

    reason: str = Field(min_length=1)
    at: datetime


class Evaluation(Value):
    """One evaluation of a version on the process's cases (ADR-0134 §3)."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    process_id: str = Field(min_length=1)
    purpose: Purpose
    version: str = Field(min_length=1)
    """The active version's reference."""
    proposal: str | None = Field(default=None, min_length=1)
    candidate: str | None = Field(default=None, min_length=1)
    """The reference the proposal's runs ran under; None for drift."""
    slot: datetime | None = None
    """The schedule's slot a drift evaluation was started for; None when started by an act."""
    acting_for: str = Field(min_length=1)
    cases: tuple[EvaluationCase, ...] = ()
    """The cases as they were when it started: the set may change while it runs."""
    scorers: tuple[Scorer, ...] = ()
    """The active version's scorers when it started; their position is the scorer's key."""
    runs: tuple[CaseRun, ...] = ()
    state: EvaluationState = EvaluationState.RUNNING
    results: tuple[CaseResult, ...] = ()
    sides: tuple[SideResult, ...] = ()
    verdict: Verdict | None = None
    tolerance: float | None = Field(default=None, ge=0, le=1)
    compared_with: str | None = None
    """For drift: the earlier evaluation the score was compared with."""
    previous_score: float | None = Field(default=None, ge=0, le=1)
    started_at: datetime
    scored_at: datetime | None = None
    override: Override | None = None

    def side(self, side: Side) -> SideResult | None:
        for found in self.sides:
            if found.side is side:
                return found
        return None
