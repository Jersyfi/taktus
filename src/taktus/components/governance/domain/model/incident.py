"""An incident, and the tenant's configuration of the watch that raises one (ADR-0107, ADR-0021).

An **incident** is the tracked object above a failure (ADR-0021 §1). The first source of one is
the watcher of expected runs: a run that was expected and did not happen, or a run that did not
end within its bound. It names the process and its version, the expected time, the last run that
did happen, the rule that fired and the facts the rule read (ADR-0023 §1). Its timeline is what
happened to it since: further misses, a run that happened late, its closure. It never names a
person (principle 14): who closed it is the actor of its ledger entry, not a field of it.

A **watch configuration** is one tenant's grace period and its threshold for a watcher that never
finds anything. A tenant that configured nothing holds the shipped default (NTC-0212).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from taktus.shared.v1 import Value


class IncidentKind(StrEnum):
    MISSING = "run.missing"
    """A run that was expected did not happen."""
    OVERDUE = "run.overdue"
    """A run that started did not end within its bound."""


class IncidentState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class RunSeen(Value):
    """A run the ledger says happened: a run that started, or a firing that found nothing."""

    at: datetime
    run_id: str | None = Field(default=None, min_length=1)
    """None for a firing whose list named nothing (`trigger.empty`): no run was created."""
    kind: str = Field(min_length=1)
    """The ledger kind it was read from: `run.started` or `trigger.empty`."""


class Happening(Value):
    """One event of an incident's timeline."""

    at: datetime
    what: Literal["missed", "happened", "closed"]
    expected_at: datetime | None = None
    """For `missed`: when the run was expected."""
    deadline: datetime | None = None
    """For `missed`: the expected time plus the grace period, after which it counted as missed."""
    run: RunSeen | None = None
    """For `happened`: the run that happened after the miss."""


class Incident(Value):
    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    kind: IncidentKind
    process_id: str = Field(min_length=1)
    process_version: str = Field(min_length=1)
    expected_at: datetime
    """When the run was expected to start (missing), or to have ended (overdue)."""
    last_run: RunSeen | None = None
    """The last run of the process that did happen before the miss; None when none did."""
    run_id: str | None = Field(default=None, min_length=1)
    """For an overdue run: the run that has not ended."""
    rule: str = Field(min_length=1)
    """The rule that fired: `expected.slot`, `expected.gap` or `expected.bound`."""
    facts: Mapping[str, str | float | None] = Field(default_factory=dict)
    """What the rule read, and the thresholds it compared with (ADR-0023 §1)."""
    raised_at: datetime
    state: IncidentState = IncidentState.OPEN
    timeline: tuple[Happening, ...] = ()
    closed_at: datetime | None = None

    @property
    def missed(self) -> tuple[datetime, ...]:
        """Every expected time this incident records as missed."""
        return tuple(h.expected_at for h in self.timeline if h.what == "missed" and h.expected_at)

    def missed_again(self, expected_at: datetime, deadline: datetime, at: datetime) -> Incident:
        return self._with(
            Happening(at=at, what="missed", expected_at=expected_at, deadline=deadline)
        )

    def happened(self, run: RunSeen, at: datetime) -> Incident:
        return self._with(Happening(at=at, what="happened", run=run))

    def closed(self, at: datetime) -> Incident:
        closing = self._with(Happening(at=at, what="closed"))
        return closing.model_copy(update={"state": IncidentState.CLOSED, "closed_at": at})

    @property
    def waits_for_a_run(self) -> datetime | None:
        """The deadline of the newest miss, while no run has been recorded after it; None once
        one has, and for an overdue run."""
        for happening in reversed(self.timeline):
            if happening.what == "happened":
                return None
            if happening.what == "missed":
                return happening.deadline
        return None

    def _with(self, happening: Happening) -> Incident:
        return self.model_copy(update={"timeline": (*self.timeline, happening)})


def incident_id(tenant: str, kind: IncidentKind, process_id: str, key: str) -> str:
    """Derived from what the incident is about, so that a second look at the same miss names the
    same incident and raises nothing (ADR-0107 §4)."""
    canonical = "\n".join((tenant, kind.value, process_id, key))
    return "inc_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


GRACE = timedelta(minutes=15)
EMPTY_SHARE = 0.9
EMPTY_WINDOW = timedelta(days=30)
EMPTY_MINIMUM = 10


class WatchConfiguration(Value):
    """One tenant's watch, stored under the tenant's own identifier (ADR-0107 §6)."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    grace: timedelta = GRACE
    """How long after its expected time a run may still start, or after its bound end."""
    empty_share: float = Field(default=EMPTY_SHARE, gt=0, le=1)
    """The share of `empty` ends above which a process is reported as possibly blind."""
    empty_window: timedelta = EMPTY_WINDOW
    """The window the share is counted over."""
    empty_minimum: int = Field(default=EMPTY_MINIMUM, ge=1)
    """The fewest ends within the window for the share to count."""
    configured_at: datetime | None = None
    """When it was configured; None for the shipped default, which nobody configured."""

    @model_validator(mode="after")
    def _sound(self) -> WatchConfiguration:
        if self.id != self.tenant:
            raise ValueError(f"a watch configuration is stored under its tenant {self.tenant!r}")
        if self.grace < timedelta(0):
            raise ValueError("the grace period is no shorter than nothing")
        if self.empty_window <= timedelta(0):
            raise ValueError("the window of the empty share is longer than nothing")
        return self


def shipped_watch(tenant: str) -> WatchConfiguration:
    """What a tenant that configured nothing holds (NTC-0212)."""
    return WatchConfiguration(id=tenant, tenant=tenant)
