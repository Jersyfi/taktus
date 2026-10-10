"""What a reader of the live stream receives (ADR-0055, UC-6.10 §2 *Live*).

A reader opens one stream for a **scope** — the tenant as a whole, one process, or one run —
and receives first a **snapshot** of the scope, then a **change** for every ledger entry that
records a change of state of a run, a step or a decision request in it. Each carries a
**position**: the hash of a ledger entry. A reader that reconnects names the last position it
received and resumes from it.

Nothing here carries content, a figure or a person: no text, no consumption, no actor. A run's
consumption is read from the component that owns it; a result through the ordinary requests.
The shapes are the contract `contracts/changes/v1/Changes.json`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from taktus.shared.v1 import Digest, Method, Value


class ScopeKind(StrEnum):
    TENANT = "tenant"
    PROCESS = "process"
    RUN = "run"


class Scope(Value):
    """What a stream covers. A process is named by its identifier, a run by its own; the tenant
    is the reader's and is named by neither."""

    kind: ScopeKind
    id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _named_where_needed(self) -> Scope:
        if (self.kind is ScopeKind.TENANT) != (self.id is None):
            raise ValueError("a process or a run scope names its id; the tenant scope none")
        return self


class Reader(Value):
    """Who reads, as the account key proves it at the moment of the read: the tenant and the
    roles the identity holds then (ADR-0055 §5)."""

    tenant: str = Field(min_length=1)
    identity: str = Field(min_length=1)
    roles: tuple[str, ...] = ()


class RunRef(Value):
    """What the predicate and the scope need of a run: its identity and where it belongs."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    process_version: str = Field(min_length=1)
    """`process@version`."""

    @property
    def process(self) -> str:
        return self.process_version.rsplit("@", 1)[0]


class StateAfter(Value):
    """Which state the entry led to, as the component that owns the state machine publishes
    it: the run's, the step's, the decision request's. Each only where the entry changed it."""

    run: str | None = None
    step: str | None = None
    decision_request: str | None = None


class Change(Value):
    """One ledger entry that recorded a change of state, projected."""

    position: Digest
    run: str = Field(min_length=1)
    step: str | None = Field(default=None, min_length=1)
    decision_request: str | None = Field(default=None, min_length=1)
    kind: str = Field(min_length=1)
    outcome: str | None = None
    method: Method | None = None
    recorded_at: datetime
    rehearsal: bool = False
    state: StateAfter

    @model_validator(mode="after")
    def _changed_something(self) -> Change:
        if not self.state.document():
            raise ValueError("a change led to a state; an entry that changed none is no change")
        return self


class SnapshotStep(Value):
    id: str = Field(min_length=1)
    state: str = Field(min_length=1)
    method: Method


class SnapshotRun(Value):
    id: str = Field(min_length=1)
    process_version: str = Field(min_length=1)
    state: str = Field(min_length=1)
    rehearsal: bool = False
    steps: tuple[SnapshotStep, ...] = ()


class Snapshot(Value):
    """The state of a scope at one position: every run the reader may see in it. The position
    is None for a tenant whose ledger is still empty."""

    position: Digest | None
    scope: Scope
    runs: tuple[SnapshotRun, ...] = ()

    def document(self) -> dict[str, object]:
        document = super().document()
        document["position"] = self.position  # null, never absent: no position yet
        return document
