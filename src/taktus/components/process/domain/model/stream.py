"""A value stream: the processes that carry a customer's need to the customer's outcome
(UC-15.6, ADR-0159 §4).

A value stream is a definition, like a process. It names its kind — a core stream from the
customer's need to their outcome, or a management or support stream beside it — the trigger it
starts from, the outcome it ends in, the one role responsible for it, and its processes in the
order they hand over to each other. That ordered list is the chain of UC-15.4: when the chain's
handover clauses are built, they extend this object, and no second object is made.

Each declaration is a revision of its own and is kept: the stream's history is never deleted.
The figures of a stream are no part of it. They are read from the records of its processes
whenever the stream is shown, and stored nowhere (ADR-0029).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from taktus.components.process.domain.model.process import ROLE
from taktus.shared.v1 import Value

STREAM = r"^[a-z][a-z0-9-]*$"


class StreamKind(StrEnum):
    CORE = "core"
    """From the customer's need to the customer's outcome."""
    MANAGEMENT = "management"
    """Steers the core streams: planning, budgets, direction."""
    SUPPORT = "support"
    """Keeps the core streams able to run: staff, systems, purchasing."""


class ValueStream(Value):
    id: str = Field(min_length=1)
    """`<stream>@<revision>`: one row per revision, never overwritten."""
    tenant: str = Field(min_length=1)
    stream: str = Field(pattern=STREAM)
    revision: int = Field(ge=1)
    name: str = Field(min_length=1)
    kind: StreamKind
    trigger: str = Field(min_length=1)
    """The need it starts from, in the words of the person it serves."""
    outcome: str = Field(min_length=1)
    """The outcome it ends in, in the same words."""
    role: str = Field(pattern=ROLE)
    """The one role responsible for the stream as a whole. A role, never a person."""
    processes: tuple[str, ...] = Field(min_length=1)
    """Its processes, in the order they hand over to each other."""
    declared_at: datetime
    """Who declared it is the ledger entry's actor, never a field beside the revision."""

    @model_validator(mode="after")
    def _named(self) -> ValueStream:
        if self.id != f"{self.stream}@{self.revision}":
            raise ValueError(f"a value stream's revision is kept as {self.stream}@{self.revision}")
        if len(set(self.processes)) != len(self.processes):
            raise ValueError("a value stream lists each of its processes once")
        return self

    def same_as(self, other: ValueStream) -> bool:
        """Whether two revisions declare the same: then no new revision is kept."""
        keep = {"name", "kind", "trigger", "outcome", "role", "processes"}
        return self.model_dump(include=keep) == other.model_dump(include=keep)
