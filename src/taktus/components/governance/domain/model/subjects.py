"""A data-protection request and what Taktus holds of its subject (ADR-0176, UC-11.2).

A **subject** is the person or organisation a case is about, named by the identifier the
organisation's own systems use (ADR-0130). A **request** asks, for one subject, for one of the
data-protection tools: `access`, `rectification`, `erasure` or `portability`. A **holding** is
one run that served a case of the subject, with everything of it that holds content: its
inputs, its stored results, artifacts and messages, its traces.

A request is *prepared* — its holdings found and shown — and then *carried out* by a person who
checked the requester's identity, or *withdrawn*. A carried-out or withdrawn request does not
move again.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from taktus.shared.v1 import Digest, Value

ERASED = "[erased]"
"""What an erased run's every input reads from then on (ADR-0176 §3)."""

KEPT_SHARED = "referenced by another run"
"""Why an erasure keeps an object: another run, not of the subject, still references it."""


class RequestKind(StrEnum):
    ACCESS = "access"
    RECTIFICATION = "rectification"
    ERASURE = "erasure"
    PORTABILITY = "portability"


class RequestState(StrEnum):
    PREPARED = "prepared"
    CARRIED_OUT = "carried_out"
    WITHDRAWN = "withdrawn"


type ObjectKind = Literal["result", "artifact", "message", "record"]
"""What an object of a run is: a step's stored result, an artifact a step produced, a message
a step received, or the content a ledger entry of the run points at."""


class HeldObject(Value):
    """One object of the object store a run references, by digest."""

    digest: Digest
    kind: ObjectKind
    step_id: str | None = Field(default=None, min_length=1)
    """The step that references it; None for content of a run's own ledger entry."""
    artifact_id: str | None = Field(default=None, min_length=1)
    kept: str | None = None
    """Why an erasure keeps it; None where an erasure removes it."""


class HeldStep(Value):
    """One step of a run that holds content, and what of it does."""

    step_id: str = Field(min_length=1)
    method: str = Field(min_length=1)
    adapter: str | None = None
    state: str = Field(min_length=1)
    recorded: bool
    """Whether the step has a provenance record."""
    scoped: bool
    """Whether the step's case scope names the subject."""
    trace_lines: int = Field(default=0, ge=0)


class Holding(Value):
    """One run that served a case of the subject."""

    run_id: str = Field(min_length=1)
    process_version: str = Field(min_length=1)
    state: str = Field(min_length=1)
    ended: bool
    """Whether the run ended: only an ended run is erased (ADR-0176 §3)."""
    created_at: datetime
    found_through: tuple[Literal["provenance", "intake"], ...] = Field(min_length=1)
    """Where it was found: a provenance record that names the subject, the run's intake, or
    both (ADR-0176 §2)."""
    inputs: tuple[str, ...] = ()
    """The names of the run's inputs that still hold a value."""
    steps: tuple[HeldStep, ...] = ()
    objects: tuple[HeldObject, ...] = ()
    left_the_system: int = Field(default=0, ge=0)
    """How many of the run's entries record something that left the system (ADR-0022)."""
    built_on: tuple[str, ...] = ()
    """The steps of other runs built on this run's results, as `<run>/<step>`."""
    other_subjects: int = Field(default=0, ge=0)
    """How many other subjects the run's scoped steps serve: a number, never who."""
    erased_for: str | None = Field(default=None, min_length=1)
    """The request whose erasure already erased the run's content, where one did."""

    def signature(self) -> tuple[Any, ...]:
        """What a person confirms of the holding: a confirmation is refused when it changed."""
        return (
            self.run_id,
            self.ended,
            self.inputs,
            tuple(sorted((o.digest, o.kind, o.step_id or "", o.kept or "") for o in self.objects)),
            tuple((s.step_id, s.trace_lines) for s in self.steps),
            self.erased_for,
        )


class Erased(Value):
    """What an erasure did."""

    runs: tuple[str, ...] = ()
    pending: tuple[str, ...] = ()
    """Runs in flight, not erased: a later request erases them once they ended."""
    objects_removed: int = Field(default=0, ge=0)
    objects_kept: int = Field(default=0, ge=0)
    inputs_erased: int = Field(default=0, ge=0)
    trace_lines_erased: int = Field(default=0, ge=0)
    ledger_intact: bool
    provenance_intact: bool
    findings: tuple[str, ...] = ()


class Exported(Value):
    """An export generated: its digest, never its content (ADR-0176 §5)."""

    digest: Digest
    size_bytes: int = Field(ge=0)


class Outcome(Value):
    """What carrying a request out did; exactly one part for its kind, none for a
    rectification, which a person carries out elsewhere."""

    erased: Erased | None = None
    exported: Exported | None = None


class SubjectRequest(Value):
    """One data-protection request of a tenant."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    kind: RequestKind
    subject: str = Field(min_length=1)
    state: RequestState = RequestState.PREPARED
    holdings: tuple[Holding, ...] = ()
    created_at: datetime
    prepared_by: str = Field(min_length=1)
    carried_out_at: datetime | None = None
    carried_out_by: str | None = Field(default=None, min_length=1)
    identity_checked: bool = False
    """The confirming person's statement that they checked who asked."""
    withdrawn_at: datetime | None = None
    withdrawn_by: str | None = Field(default=None, min_length=1)
    outcome: Outcome | None = None

    @model_validator(mode="after")
    def _sound(self) -> SubjectRequest:
        if self.state is RequestState.CARRIED_OUT and (
            self.carried_out_by is None or not self.identity_checked
        ):
            raise ValueError("a request is carried out by a person who checked the identity")
        if self.state is RequestState.WITHDRAWN and self.withdrawn_by is None:
            raise ValueError("a request is withdrawn by someone")
        return self


class RequestRefused(ValueError):
    """A request that cannot be prepared, confirmed or withdrawn as asked; nothing changed."""


def signature(holdings: tuple[Holding, ...]) -> tuple[Any, ...]:
    return tuple(sorted(h.signature() for h in holdings))


def confirmable(request: SubjectRequest, *, identity_checked: bool) -> None:
    """Raises RequestRefused where the request cannot be carried out now."""
    if request.state is not RequestState.PREPARED:
        raise RequestRefused(f"request {request.id} is {request.state}, not prepared")
    if not identity_checked:
        raise RequestRefused(
            "a request is carried out only by a person who checked the requester's identity"
        )


def carried_out(
    request: SubjectRequest, *, by: str, at: datetime, outcome: Outcome
) -> SubjectRequest:
    return request.model_copy(
        update={
            "state": RequestState.CARRIED_OUT,
            "carried_out_by": by,
            "carried_out_at": at,
            "identity_checked": True,
            "outcome": outcome,
        }
    )


def withdrawn(request: SubjectRequest, *, by: str, at: datetime) -> SubjectRequest:
    if request.state is not RequestState.PREPARED:
        raise RequestRefused(f"request {request.id} is {request.state}, not prepared")
    return request.model_copy(
        update={"state": RequestState.WITHDRAWN, "withdrawn_by": by, "withdrawn_at": at}
    )
