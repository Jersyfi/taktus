"""DecisionRequest.json: the planned question about direction (ADR-0008)."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import Field, model_validator

from taktus.shared.v1.capability import Capability
from taktus.shared.v1.value import Value


class DecisionClass(StrEnum):
    STRATEGIC = "strategic"
    CONCEPTUAL = "conceptual"
    DOMAIN = "domain"
    LEGAL = "legal"
    CORRECTION = "correction"
    """Raised by the correction anchor: correct a result that has left the system (ADR-0022)."""


class DecisionStatus(StrEnum):
    OPEN = "open"
    ANSWERED = "answered"
    INTERPRETED = "interpreted"
    CONFIRMED = "confirmed"
    APPLIED = "applied"


class RaisedBy(Value):
    run: str = Field(min_length=1)
    step: str = Field(min_length=1)


class DecisionOption(Value):
    id: str = Field(pattern=r"^[A-Z]$")
    proposal: str = Field(min_length=1)
    consequence: str | None = None
    effort: str | None = None
    recommended: bool


class DecisionChannel(Value):
    connector: Capability
    address: str = Field(min_length=1)
    thread: str | None = None


class AnswerInterpreted(Value):
    option: str = Field(pattern=r"^[A-Z]$")
    modifications: str | None = None


class DecisionRequest(Value):
    id: str = Field(min_length=1)
    raised_by: RaisedBy
    class_: DecisionClass = Field(alias="class")
    situation: str = Field(min_length=1)
    question: str = Field(min_length=1)
    options: tuple[DecisionOption, ...] = Field(min_length=2)
    blocking: tuple[str, ...]
    channel: DecisionChannel
    due: date
    status: DecisionStatus
    answer_raw: str | None = None
    answer_interpreted: AnswerInterpreted | None = None
    outcome: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _rules(self) -> DecisionRequest:
        if sum(1 for o in self.options if o.recommended) != 1:
            raise ValueError("exactly one option is recommended")
        if any(not b for b in self.blocking) or len(set(self.blocking)) != len(self.blocking):
            raise ValueError("blocking lists identifiers, each once")
        beyond_open = self.status is not DecisionStatus.OPEN
        beyond_answered = self.status in (
            DecisionStatus.INTERPRETED,
            DecisionStatus.CONFIRMED,
            DecisionStatus.APPLIED,
        )
        if beyond_open and self.answer_raw is None:
            raise ValueError(f"a {self.status} request carries the raw answer")
        if beyond_answered and self.answer_interpreted is None:
            raise ValueError(f"a {self.status} request carries the interpretation")
        if self.status is DecisionStatus.APPLIED and self.outcome is None:
            raise ValueError("an applied request names its register entry")
        return self
