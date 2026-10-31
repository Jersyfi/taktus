"""LedgerEntry.json: one link of the content-free hash chain (ADR-0006)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from taktus.shared.v1.artifact import Digest
from taktus.shared.v1.autonomy import ACTION_PATTERN
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
    incident_id: str | None = Field(default=None, min_length=1)
    """The incident the entry is about (ADR-0107)."""
    action: str | None = Field(default=None, pattern=ACTION_PATTERN)
    """The tool action whose level held the step the entry is about; None where the process's
    own level held it (ADR-0110)."""
    report_id: str | None = Field(default=None, min_length=1)
    """The report to the owner the entry is about (ADR-0045)."""
    deadline_id: str | None = Field(default=None, min_length=1)
    """The deadline the entry is about (ADR-0133)."""
    stage_id: str | None = Field(default=None, min_length=1)
    """The stage of a tenant's introduction the entry is about (ADR-0137)."""
    skill_id: str | None = Field(default=None, min_length=1)
    """The skill version the entry is about, `<name>@<version>` (ADR-0162)."""
    agent_id: str | None = Field(default=None, min_length=1)
    """The shared agent the entry is about: a core, `<agent>@<version>`, or a role profile,
    `<agent>:<role>@<version>` (ADR-0163). It names a role, never a person."""
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
    duration_seconds: float | None = Field(default=None, ge=0)
    """How long what the entry records took: a run, from its creation to its end, on
    `run.ended`; the read of an `each` list on `trigger.empty` (ADR-0107)."""
    content_digest: Digest | None = None
    rehearsal: Literal[True] | None = None
    """True on every entry of a rehearsal run, absent otherwise (ADR-0030): nothing outside
    was acted on, and no such entry is evidence that anything was."""
    chain_seq: int | None = Field(default=None, ge=1)
    """The entry's place in its chain: its run's chain when it references a run, the tenant's
    otherwise (ADR-0164). Absent on an entry written before: the tenant's chain was the only
    one, and the entry's place in it is its seq."""
    chain: Literal["tenant"] | None = None
    """`tenant` on an entry that references a run and is on the tenant's chain all the same,
    because what it records must be ordered with the tenant's other such entries (ADR-0164)."""
    through: int | None = Field(default=None, ge=0)
    """On `ledger.anchored` only: the seq up to which the anchor covers the run chains' heads
    (ADR-0164)."""

    def chain_name(self) -> str:
        """The chain the entry is on: its run's identifier, or "" for the tenant's chain — an
        entry that references no run, one marked `tenant`, and every entry written before
        ADR-0164, when the tenant's chain was the only one."""
        if self.chain_seq is None or self.chain == "tenant" or self.refs.run_id is None:
            return ""
        return self.refs.run_id

    def document(self) -> dict[str, object]:
        # prev_hash is required by the schema and null for the first entry: keep it when None.
        document = super().document()
        document["prev_hash"] = self.prev_hash
        return document
