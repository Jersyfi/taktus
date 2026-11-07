"""What the bottleneck analysis reads from other components (ADR-0283, UC-9.5).

Three ports; the composition root answers each, because components never import each other.

**`BlockAccounts`** is the run's blocked-time accounts, read. `blocks` hands the ended blocks of
the four limit accounts and the steps held back (`wait.dependency`), never a wait on a person
one by one. `waits` hands the waits on a person only as the run groups them, by role or by
department, with a group that fewer than two persons answered withheld (ADR-0043, NTC-0168).

**`MethodCheck`** says, per step, whether a change of method may remove a bottleneck at no
extra cost: the run's step measures and the maturation candidacy (ADR-0004, ADR-0084).

**`RecurringDecisions`** is the decision component's rules from precedent: proposed, adopted,
declined or retired (ADR-0161). A rule names the role that decides it, never a person.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Literal, Protocol

from pydantic import Field

from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Value

type Grouping = Literal["role", "department"]
type Period = Literal["day", "week", "month"]


class Blocked(Value):
    """A block that ended, as the analysis reads it. No field can hold a person."""

    account: str = Field(min_length=1)
    cause: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    process_version: str = Field(min_length=1)
    since: datetime
    until: datetime
    seconds: float = Field(ge=0)
    on: str | None = None
    """For a step held back: the step it waited on."""
    short: dict[str, float] | None = None
    """For a refusal by admission: by how much the reservation exceeded what was left, per
    quantity, when the block began."""

    @property
    def process(self) -> str:
        return self.process_version.split("@", 1)[0]


class WaitGroup(Value):
    """The waits on a person of one role or department, in one period, as the run groups
    them. Withheld, with no figure, where fewer than two persons answered."""

    grouping: Grouping
    group: str = Field(min_length=1)
    period: str = Field(min_length=1)
    seconds: float | None = Field(default=None, ge=0)
    blocks: int | None = Field(default=None, ge=1)
    runs_held_up: int | None = Field(default=None, ge=1)
    withheld: str | None = Field(default=None, min_length=1)


class BlockAccounts(Protocol):
    async def blocks(self, tenant: Tenant) -> Sequence[Blocked]:
        """Every ended block of `limit.*` and `wait.dependency`, oldest first; a rehearsal's
        left out."""
        ...

    async def waits(
        self, tenant: Tenant, grouping: Grouping, period: Period
    ) -> Sequence[WaitGroup]:
        """The waits on a person by role or by department, per period."""
        ...


class MethodChecked(Value):
    """What a check for a change of method found for one step."""

    process_version: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    method: str | None = None
    """The step's method now; None where no case of the step is recorded."""
    alternative: str | None = None
    """The method that may remove the bottleneck at no extra cost, where one may."""
    check: str = Field(min_length=1)
    """What was checked and what it found, in one line."""

    @property
    def removes(self) -> bool:
        return self.alternative is not None


class MethodCheck(Protocol):
    async def check(
        self, tenant: Tenant, steps: Sequence[tuple[str, str]]
    ) -> Sequence[MethodChecked]:
        """The check of each step, named by its process version and identifier, in order."""
        ...


class RecurringRule(Value):
    """A rule from recurring decisions, as the analysis reads it: whose it is, never who."""

    rule_id: str = Field(min_length=1)
    process: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    anchor: str = Field(min_length=1)
    role: str = Field(min_length=1)
    """The role that decided the precedents, decides the proposal and retires the rule."""
    status: Literal["proposed", "adopted", "declined", "retired"]
    precedents: int = Field(ge=1)
    request_id: str = Field(min_length=1)
    """The decision request that proposes it."""


class RecurringDecisions(Protocol):
    async def rules(self, tenant: Tenant) -> Sequence[RecurringRule]:
        """Every rule from precedent of the tenant, in the order it was proposed."""
        ...
