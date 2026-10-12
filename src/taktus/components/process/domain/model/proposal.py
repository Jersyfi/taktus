"""A proposal: a changed process version a person asked for, not yet registered (UC-4.15,
ADR-0091 §1).

A proposal is a record of its own and never a process version. No trigger, schedule, overview
or level reads it as one, and the active version does not change while it exists. It carries
the bundle it proposes, the version it was made against, the words of the request where there
were any, who asked, and its difference against that version: every step added, removed or
changed, each with what it was and what it would be.

Its state moves `proposed` → `rehearsed` → `commissioned`, or to `discarded` from either of the
first two. Only commissioning registers it, through registration (ADR-0091 §4).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from taktus.shared.v1 import Autonomy, Step, Value


class ProposalState(StrEnum):
    PROPOSED = "proposed"
    REHEARSED = "rehearsed"
    COMMISSIONED = "commissioned"
    DISCARDED = "discarded"


OPEN = frozenset({ProposalState.PROPOSED, ProposalState.REHEARSED})
"""The states in which a proposal can still be rehearsed, commissioned or discarded."""


class StepChange(Value):
    """One step the proposal adds, removes or changes, with what it was and what it would be."""

    id: str = Field(min_length=1)
    change: Literal["added", "removed", "changed"]
    before: Step | None = None
    after: Step | None = None
    fields: tuple[str, ...] = ()
    """For a changed step, the fields that differ: `method`, `reason`, `rejected`,
    `exactness`, `checks`, `fallback`, `depends_on`, `work`, and the like."""


class Difference(Value):
    """What the proposal changes against the version it was made against."""

    steps: tuple[StepChange, ...] = ()
    autonomy_before: Autonomy
    autonomy_after: Autonomy
    triggers_changed: bool = False
    inputs_changed: bool = False

    @property
    def empty(self) -> bool:
        return (
            not self.steps
            and self.autonomy_before == self.autonomy_after
            and not self.triggers_changed
            and not self.inputs_changed
        )


class Proposal(Value):
    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    process_id: str = Field(min_length=1)
    base_version: str = Field(min_length=1)
    """The version the proposal was made against: the active one when it was made."""
    version: str = Field(min_length=1)
    """The version the proposal would register as, if commissioned."""
    bundle: dict[str, Any]
    request: str | None = None
    """The person's words, where the proposal was asked for in words."""
    requested_by: str = Field(min_length=1)
    state: ProposalState = ProposalState.PROPOSED
    difference: Difference
    created_at: datetime
    rehearsal_run: str | None = None
    """The rehearsal run, once the proposal is rehearsed (ADR-0091 §3)."""

    @property
    def base_ref(self) -> str:
        return f"{self.process_id}@{self.base_version}"
