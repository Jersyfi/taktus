"""Provenance.json: what a step result is made of (ADR-0021)."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from taktus.shared.v1.artifact import Digest
from taktus.shared.v1.capability import Capability
from taktus.shared.v1.exactness_class import ExactnessClass
from taktus.shared.v1.method import NON_PRODUCING, PRODUCING, Method
from taktus.shared.v1.step import MODEL_PATTERN, StepId
from taktus.shared.v1.value import Value

MESSAGE_REF = r"msg_[A-Za-z0-9_-]{4,}"


class InputKind(StrEnum):
    ARTIFACT = "artifact"
    RESULT = "result"
    SOURCE = "source"
    MESSAGE = "message"
    """A person's message the step's worker received at a boundary (ADR-0156 §9)."""


class ProvenanceInput(Value):
    """One thing a step read, and when: an artifact or a result of an earlier step run, an
    external source read through a capability, or a person's message its worker received."""

    kind: InputKind
    run_id: str | None = Field(default=None, min_length=1)
    step_id: StepId | None = None
    artifact_id: str | None = Field(default=None, min_length=1)
    capability: Capability | None = None
    ref: str | None = Field(default=None, min_length=1)
    digest: Digest | None = None
    observed_at: datetime

    @model_validator(mode="after")
    def _fields_of_its_kind(self) -> ProvenanceInput:
        # The three rules of the input's allOf: each kind requires its own fields and
        # forbids the other kinds'.
        present = {
            name
            for name in ("run_id", "step_id", "artifact_id", "capability", "ref")
            if getattr(self, name) is not None
        }
        if self.kind is InputKind.ARTIFACT:
            needed, forbidden = {"run_id", "step_id", "artifact_id"}, {"capability", "ref"}
            if self.digest is None:
                raise ValueError("an artifact input carries the artifact's digest")
        elif self.kind is InputKind.RESULT:
            needed, forbidden = {"run_id", "step_id"}, {"artifact_id", "capability", "ref"}
            if self.digest is None:
                raise ValueError("a result input carries the result's digest")
        elif self.kind is InputKind.MESSAGE:
            needed, forbidden = {"ref"}, {"run_id", "step_id", "artifact_id", "capability"}
            if self.digest is None:
                raise ValueError("a message input carries the digest of the message's text")
            if self.ref is not None and re.fullmatch(MESSAGE_REF, self.ref) is None:
                raise ValueError("a message input names the message's identifier, msg_…")
        else:
            needed, forbidden = {"capability", "ref"}, {"run_id", "step_id", "artifact_id"}
        if missing := needed - present:
            raise ValueError(f"a {self.kind} input names {', '.join(sorted(missing))}")
        if extra := forbidden & present:
            raise ValueError(f"a {self.kind} input does not name {', '.join(sorted(extra))}")
        return self


class RouteSkip(Value):
    """A member of the chain the route passed over, and why (ADR-0116 §4)."""

    adapter: str = Field(min_length=1)
    reason: Literal["residency", "exactness", "cooling_down"]


class ProvenanceRoute(Value):
    """The route a step on a model took through its purpose's chain (ADR-0116 §7)."""

    purpose: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    adapter: str = Field(min_length=1)
    permitted: Literal["own", "eu", "anywhere"]
    data_class: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]*$")
    skipped: tuple[RouteSkip, ...]


class ProvenanceScope(Value):
    """The case a step served: the subject whose data its result was built from (ADR-0130)."""

    subject: str = Field(min_length=1, max_length=256)


class Provenance(Value):
    id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    step_id: StepId
    process_version: str = Field(min_length=1)
    method: Method
    exactness: ExactnessClass | None = None
    model: str | None = Field(default=None, pattern=MODEL_PATTERN)
    prompt: str | None = Field(default=None, pattern=MODEL_PATTERN)
    adapter: str | None = Field(default=None, min_length=1)
    adapter_version: str | None = Field(default=None, min_length=1)
    route: ProvenanceRoute | None = None
    scope: ProvenanceScope | None = None
    inputs: tuple[ProvenanceInput, ...]
    outputs: tuple[str, ...]
    result_digest: Digest | None = None
    ledger_seq: int = Field(ge=1)
    recorded_at: datetime

    @model_validator(mode="after")
    def _rules(self) -> Provenance:
        findings: list[str] = []
        if self.method in PRODUCING and self.exactness is None:
            findings.append(f"a {self.method} step produces a result and carries its exactness")
        if self.method in NON_PRODUCING and self.exactness is not None:
            findings.append(f"a {self.method} step produces no result and carries no exactness")
        if self.adapter_version is not None and self.adapter is None:
            findings.append("an adapter version names its adapter")
        if self.route is not None and self.route.adapter != self.adapter:
            findings.append("a route names the adapter that produced the record's result")
        if any(not output for output in self.outputs):
            findings.append("an output identifier is never empty")
        if len(set(self.outputs)) != len(self.outputs):
            findings.append("outputs lists an artifact twice")
        if findings:
            raise ValueError("; ".join(findings))
        return self

    def produced(self, artifact_id: str) -> bool:
        return artifact_id in self.outputs

    def reads_from(self) -> frozenset[tuple[str, str]]:
        """The step runs this record's inputs come from, as (run, step)."""
        return frozenset(
            (input.run_id, input.step_id)
            for input in self.inputs
            if input.run_id is not None and input.step_id is not None
        )
