"""Provenance.json: what a step result is made of (ADR-0021)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from taktus.shared.v1.artifact import Digest
from taktus.shared.v1.capability import Capability
from taktus.shared.v1.exactness_class import ExactnessClass
from taktus.shared.v1.method import NON_PRODUCING, PRODUCING, Method
from taktus.shared.v1.step import MODEL_PATTERN, StepId
from taktus.shared.v1.value import Value


class InputKind(StrEnum):
    ARTIFACT = "artifact"
    RESULT = "result"
    SOURCE = "source"


class ProvenanceInput(Value):
    """One thing a step read, and when: an artifact or a result of an earlier step run, or an
    external source read through a capability."""

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
        else:
            needed, forbidden = {"capability", "ref"}, {"run_id", "step_id", "artifact_id"}
        if missing := needed - present:
            raise ValueError(f"a {self.kind} input names {', '.join(sorted(missing))}")
        if extra := forbidden & present:
            raise ValueError(f"a {self.kind} input does not name {', '.join(sorted(extra))}")
        return self


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
