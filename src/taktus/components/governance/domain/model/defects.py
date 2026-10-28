"""A result defect, bounded and planned for (ADR-0021, ADR-0022, ADR-0023, ADR-0153).

A **result defect** is a result that counted and is wrong. It is found by a person who records
what the result should have been (`step.corrected`), or by a sample a person judged wrong
(`check.sampled`). Four objects follow from it, each a value, each changing nothing:

- the **impact analysis** (UC-4.11): since when the step produced such results, which results
  are affected, what was built on them, and what has left the system;
- the **decision** of the rule (ADR-0023): `continue`, `escalate` or `stop`, with the facts and
  the thresholds it read;
- the **remediation plan** (UC-4.12): the steps that produce the affected results again, in
  order, and for every result that left the system an outward correction that waits for a
  person, written so that a person can carry it out without Taktus;
- the **rules** a tenant holds, which are never empty: some rule always leads to `escalate`.

Nothing here names a person (principle 14): what a correction was is the ledger's, who made it
is the actor of its entry.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from taktus.components.governance.domain.model.egress import Egress, ResultRef
from taktus.shared.v1 import ExactnessClass, Value

STRICTNESS: dict[ExactnessClass, int] = {
    ExactnessClass.EXACT: 4,
    ExactnessClass.SOURCED: 3,
    ExactnessClass.TOLERANT: 2,
    ExactnessClass.FREE: 1,
}
"""How strict a class is, for "the strictest class affected" (ADR-0023 §2)."""


class Found(StrEnum):
    CORRECTED = "corrected"
    """A person recorded what the result should have been (`step.corrected`)."""
    SAMPLED = "sampled"
    """A person judged a sampled result wrong (`check.sampled`, ADR-0152)."""


class Position(StrEnum):
    FIRST = "first"
    INSIDE = "inside"
    LAST = "last"
    DERIVED = "derived"
    """Not a result of the step itself, but one derived from a result in the window."""


class Change(Value):
    """What changed in how the step produced its results, between two results of the step."""

    field: Literal["process_version", "method", "model", "prompt", "adapter", "adapter_version"]
    before: str | None
    after: str | None
    at_run: str = Field(min_length=1)
    """The run whose result is the first after the change."""


class Affected(Value):
    """One result in the impact analysis."""

    result: ResultRef
    process_version: str = Field(min_length=1)
    exactness: ExactnessClass | None
    position: Position
    produced_at: datetime
    readers: tuple[str, ...] = ()
    """The steps that read it, as `<process_version>/<step>`: what was built on it."""
    left: Egress | None = None
    """The egress entry through which it, or something derived from it, left the system."""


class Analysis(Value):
    """The impact analysis of one result defect (UC-4.11). Changes nothing."""

    defect: ResultRef
    found: Found
    process_version: str = Field(min_length=1)
    cause: Change | None = None
    """The change the window starts after; None where none was found, which is said, never
    guessed."""
    unbounded: bool = False
    """The window may reach before the first result the provenance chain recorded: since when
    cannot be said, which is itself a finding."""
    window_start: datetime
    window_end: datetime
    window_runs: int = Field(ge=1)
    affected: tuple[Affected, ...] = Field(min_length=1)

    @property
    def strictest(self) -> ExactnessClass | None:
        classes = [a.exactness for a in self.affected if a.exactness is not None]
        return max(classes, key=STRICTNESS.__getitem__) if classes else None

    @property
    def left(self) -> tuple[Affected, ...]:
        return tuple(a for a in self.affected if a.left is not None)


class Verdict(StrEnum):
    CONTINUE = "continue"
    ESCALATE = "escalate"
    STOP = "stop"


SEVERITY: dict[Verdict, int] = {Verdict.CONTINUE: 0, Verdict.ESCALATE: 1, Verdict.STOP: 2}


class When(Value):
    """What a rule reads; every condition given must hold (ADR-0023 §2). Each is a number or a
    yes/no the system already holds."""

    classes: tuple[ExactnessClass, ...] = ()
    """The strictest class affected is one of these."""
    left: bool | None = None
    """Whether anything affected has left the system."""
    legal_downstream: bool | None = None
    """Whether a step that reads an affected result sits under a legal anchor."""
    window_runs_over: int | None = Field(default=None, ge=0)
    window_over: timedelta | None = None
    relevance_at_least: int | None = Field(default=None, ge=1, le=5)
    """The business relevance the tenant assigned to the process, 1 to 5."""

    @model_validator(mode="after")
    def _says_something(self) -> When:
        if not self.model_dump(exclude_defaults=True):
            raise ValueError("a rule reads at least one criterion")
        return self


class Rule(Value):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    when: When
    then: Verdict


class Facts(Value):
    """The facts a rule reads, as the analysis and the tenant's records give them."""

    strictest: ExactnessClass | None
    left: bool
    legal_downstream: bool
    window_runs: int
    window: timedelta
    relevance: int | None = None


class Decision(Value):
    """What the rule decided, with the rules that fired, the facts and the thresholds it read
    (ADR-0023 §1)."""

    verdict: Verdict
    fired: tuple[str, ...] = ()
    facts: Facts
    thresholds: dict[str, str] = Field(default_factory=dict)


SHIPPED: tuple[Rule, ...] = (
    Rule(
        id="exact-left-under-a-legal-anchor",
        when=When(classes=(ExactnessClass.EXACT,), left=True, legal_downstream=True),
        then=Verdict.STOP,
    ),
    Rule(
        id="exact-or-sourced",
        when=When(classes=(ExactnessClass.EXACT, ExactnessClass.SOURCED)),
        then=Verdict.ESCALATE,
    ),
    Rule(id="window-over-a-week", when=When(window_over=timedelta(days=7)), then=Verdict.ESCALATE),
    Rule(id="anything-left", when=When(left=True), then=Verdict.ESCALATE),
)
"""The rules a tenant that configured nothing holds: ADR-0023's two examples, the second split
into its two halves, and an escalation for anything that left the system (NTC-0242)."""


class EmptiedRules(Exception):
    """A rule set under which no criterion leads to `escalate` (ADR-0023 §3)."""


def never_empty(rules: tuple[Rule, ...]) -> tuple[Rule, ...]:
    """The rules, once at least one of them leads to `escalate` or `stop` and each has an
    identifier of its own; `EmptiedRules` otherwise (ADR-0023 §3: reducible, never empty)."""
    if not any(r.then is not Verdict.CONTINUE for r in rules):
        raise EmptiedRules(
            "no rule leads to escalate: an unattended process with no condition that brings a "
            "person in has no owner in practice (ADR-0023 §3)"
        )
    if len({r.id for r in rules}) != len(rules):
        raise EmptiedRules("every rule has an identifier of its own")
    return rules


class Kind(StrEnum):
    INSIDE = "inside"
    """Produced again inside the system: runs at the process's level (ADR-0022 §2)."""
    OUTWARD = "outward"
    """Corrected where it went: waits for a person at every level (ADR-0022 §3)."""


class PlanStep(Value):
    """One step of a remediation plan, written so that a person can carry it out without Taktus:
    the system to act in, the record to change, the value before and after, the order, and how
    to tell that it is done (UC-4.12, ADR-0013 B)."""

    order: int = Field(ge=1)
    kind: Kind
    system: str = Field(min_length=1)
    record: str = Field(min_length=1)
    before: str = Field(min_length=1)
    after: str = Field(min_length=1)
    done_when: str = Field(min_length=1)
    after_steps: tuple[int, ...] = ()
    """The steps of the plan it waits for."""
    atomic: bool = True
    """False where the correction cannot be made at once: the receiver holds the old value while
    the new one is prepared, and the plan says so."""
    note: str | None = None


class Plan(Value):
    """The remediation plan of one result defect (UC-4.12): a process in order, produced by
    Taktus at any level. Its outward steps are under the correction anchor."""

    defect: ResultRef
    process_version: str = Field(min_length=1)
    steps: tuple[PlanStep, ...] = Field(min_length=1)

    @property
    def outward(self) -> tuple[PlanStep, ...]:
        return tuple(s for s in self.steps if s.kind is Kind.OUTWARD)

    @property
    def runs_unattended(self) -> bool:
        """Whether the plan runs at the process's level without a halt: nothing has left."""
        return not self.outward
