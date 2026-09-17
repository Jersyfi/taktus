"""What the egress predicate speaks about (ADR-0022 §4)."""

from __future__ import annotations

from pydantic import Field

from taktus.shared.v1 import Digest, Value


class ResultRef(Value):
    """One result inside the system: an artifact of a step run, or the value the step run
    produced (named by its digest)."""

    run_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    artifact_id: str | None = Field(default=None, min_length=1)
    digest: Digest | None = None


class Egress(Value):
    """Where a result, or something derived from it, left the system: the ledger entry and
    the member of the closure it names."""

    seq: int
    kind: str
    through: ResultRef
