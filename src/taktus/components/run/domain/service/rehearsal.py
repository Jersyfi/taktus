"""Rehearsal (ADR-0030): which earlier call answers an outward connector operation in a
rehearsal run. Pure functions, no I/O.

A rehearsal run sends no outward call. Where a real run would call an operation whose effect
leaves Taktus, a rehearsal takes the result of the most recent *real* call of the same
operation through the same adapter in the same tenant — the stored result of that step run —
and continues with it. The rule below chooses that step run. It never chooses one of a
rehearsal run: a recording is always evidence of a real answer, never of another replay.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from pydantic import Field

from taktus.components.run.domain.model.run import Run
from taktus.shared.v1 import Digest, StepId, Value

REHEARSED = "rehearsed"
"""The outcome of `step.finished` for an outward step a rehearsal answered from a recording."""


class Recording(Value):
    """Where a recorded response is kept: the real step run that received it, and the digest
    of its stored result (`{output, effect, consumption}`)."""

    run_id: str = Field(min_length=1)
    step_id: StepId
    digest: Digest
    finished_at: datetime


def recording(runs: Iterable[Run], adapter: str, operation: str) -> Recording | None:
    """The most recent successful step run of a real run whose work called `operation` through
    `adapter` and kept its result; None when the operation was never called for real through
    that adapter."""
    found: Recording | None = None
    for run in runs:
        if run.rehearsal:
            continue
        for step_run in run.step_runs:
            if not step_run.done or step_run.adapter != adapter:
                continue
            checkpoint = step_run.checkpoint
            if checkpoint is None or checkpoint.result_digest is None:
                continue
            work = run.work.get(step_run.step_id) or {}
            if work.get("rule") != "connector" or work.get("operation") != operation:
                continue
            at = step_run.finished_at or checkpoint.taken_at
            if found is None or at > found.finished_at:
                found = Recording(
                    run_id=run.id,
                    step_id=step_run.step_id,
                    digest=checkpoint.result_digest,
                    finished_at=at,
                )
    return found
