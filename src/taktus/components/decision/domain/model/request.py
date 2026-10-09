"""A decision request as the decision component keeps it, and the entry it leaves in the
decision register (ADR-0008, ADR-0042).

The request itself has the one shape of `contracts/shared/v1/DecisionRequest.json` in every
process and every channel. Around it the component keeps what the shape does not carry: the
tenant, the role that decides, the anchor that raised it, and when it was raised, answered and
decided — what the decider's list, the due date and the response times are read from.

A **register entry** is what an applied request leaves behind: the decision, linked to the run,
the step and the request, and the precedent later cases are judged by. It is written once.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from taktus.shared.v1 import DecisionClass, DecisionRequest, DecisionStatus, Value


class Request(Value):
    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    decider: str = Field(min_length=1)
    """The role that decides. The identities holding it are the deciders it is addressed to."""
    anchor: str | None = Field(default=None, min_length=1)
    """The anchor that raised it; None for a request no anchor raised."""
    raised_at: datetime
    request: DecisionRequest
    answered_by: str | None = Field(default=None, min_length=1)
    """The identity whose answer the request carries now."""
    answered_at: datetime | None = None
    reflection: str | None = Field(default=None, min_length=1)
    """The one message sent back for the answer: the interpretation to confirm, or why no
    option could be read from it."""
    decided_by: str | None = Field(default=None, min_length=1)
    decided_at: datetime | None = None

    @property
    def status(self) -> DecisionStatus:
        return self.request.status

    @property
    def open(self) -> bool:
        """Not yet applied: work waits on it."""
        return self.status is not DecisionStatus.APPLIED

    def overdue(self, today: date) -> bool:
        """Past its due date and not applied."""
        return self.open and self.request.due < today


class RegisterEntry(Value):
    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    class_: DecisionClass = Field(alias="class")
    anchor: str | None = Field(default=None, min_length=1)
    decider: str = Field(min_length=1)
    """The role that decided."""
    option: str = Field(pattern=r"^[A-Z]$")
    proposal: str = Field(min_length=1)
    modifications: str | None = None
    answer_raw: str = Field(min_length=1)
    decided_by: str = Field(min_length=1)
    raised_at: datetime
    answered_at: datetime
    decided_at: datetime


def entry_id(request_id: str) -> str:
    """The one register entry a request can have."""
    return "dce_" + request_id.removeprefix("dr_")
