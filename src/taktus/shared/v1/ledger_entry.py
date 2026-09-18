"""LedgerEntry.json: one link of the content-free hash chain (ADR-0006)."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from taktus.shared.v1.artifact import Digest
from taktus.shared.v1.consumption import Consumption
from taktus.shared.v1.method import Method
from taktus.shared.v1.step import MODEL_PATTERN
from taktus.shared.v1.value import Value

KIND_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"
OUTCOME_PATTERN = r"^[a-z][a-z0-9_]*$"
TRACE_ID_PATTERN = r"^[0-9a-f]{32}$"

EGRESS_KINDS: frozenset[str] = frozenset({"egress.write", "egress.delivery", "egress.read"})
"""The entries that record that a result left the system (ADR-0022 §4): a connector wrote
outward, a channel delivered, an external system read through Taktus."""


class LedgerRefs(Value):
    """What an entry is about: identifiers only, at least one."""

    tenant: str | None = Field(default=None, min_length=1)
    command_id: str | None = Field(default=None, min_length=1)
    plan_id: str | None = Field(default=None, min_length=1)
    process_version: str | None = Field(default=None, min_length=1)
    run_id: str | None = Field(default=None, min_length=1)
    step_id: str | None = Field(default=None, min_length=1)
    assignment_id: str | None = Field(default=None, min_length=1)
    decision_request_id: str | None = Field(default=None, min_length=1)
    artifact_ids: tuple[str, ...] | None = None
    actor: str | None = Field(default=None, min_length=1)
    trace_id: str | None = Field(default=None, pattern=TRACE_ID_PATTERN)
    """The trace the entry was recorded in, so that an entry and a trace can be joined."""

    @model_validator(mode="after")
    def _at_least_one(self) -> LedgerRefs:
        if not self.document():
            raise ValueError("an entry references at least one identifier")
        if self.artifact_ids is not None:
            if any(not a for a in self.artifact_ids):
                raise ValueError("an artifact id is never empty")
            if len(set(self.artifact_ids)) != len(self.artifact_ids):
                raise ValueError("artifact_ids lists an artifact twice")
        return self


class LedgerEntry(Value):
    seq: int = Field(ge=1)
    ts: datetime
    kind: str = Field(pattern=KIND_PATTERN)
    prev_hash: Digest | None
    hash: Digest
    refs: LedgerRefs
    method: Method | None = None
    model: str | None = Field(default=None, pattern=MODEL_PATTERN)
    adapter: str | None = Field(default=None, min_length=1)
    consumption: Consumption | None = None
    outcome: str | None = Field(default=None, pattern=OUTCOME_PATTERN)
    content_digest: Digest | None = None

    def document(self) -> dict[str, object]:
        # prev_hash is required by the schema and null for the first entry: keep it when None.
        document = super().document()
        document["prev_hash"] = self.prev_hash
        return document
