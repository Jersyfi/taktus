"""A deadline as the run keeps it, and the tenant's working time it may count in (ADR-0133,
UC-4.17).

A **deadline rule** is the run's copy of what its process version declares: the moment it starts
from, its limit, an optional lead time, whether it counts in calendar or in working time, the
step whose finish meets it, and the action at the lead time and at the limit. A run takes the
copy when it is created, as it takes its steps and their work.

A **deadline** is the record of one rule started for one run, the case. It holds when it falls
due and when its lead time begins, which actions were taken and when, and whether it was met.
It never names a person (principle 14): an action names a role or a process.

A tenant's **working time** is a zone, the working days, the hours of a working day and the
dates that are no working days. A tenant that configured none holds the shipped default
(NTC-0227).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, model_validator

from taktus.shared.v1 import StepId, Value

NAME = r"^[a-z][a-z0-9_]*$"
"""A deadline's name is a token: `first_answer`, `renewal`."""
ROLE = r"^[a-z][a-z0-9_.-]*$"
"""A role is named as the organisation's structure names it: a token."""
PROCESS = r"^[a-z][a-z0-9-]*$"


class ActionKind(StrEnum):
    REMIND = "remind"
    """A reminder to the holders of a role."""
    ESCALATE = "escalate"
    """An escalation to the holders of a role."""
    START = "start"
    """A run of a process started."""


class DeadlineAction(Value):
    """What happens at a deadline's lead time or limit: exactly one of a reminder to a role, an
    escalation to a role, or the start of a process."""

    kind: ActionKind
    role: str | None = Field(default=None, pattern=ROLE)
    process: str | None = Field(default=None, pattern=PROCESS)
    inputs: Mapping[str, Any] = Field(default_factory=dict)
    """The literal inputs a started run is given."""

    @model_validator(mode="after")
    def _one_target(self) -> DeadlineAction:
        if self.kind is ActionKind.START:
            if self.process is None or self.role is not None:
                raise ValueError("a start names a process and no role")
        elif self.role is None or self.process is not None or self.inputs:
            raise ValueError(f"a {self.kind} names a role, and nothing else")
        return self


class Start(StrEnum):
    RUN = "run"
    """When the run is created."""
    AFTER = "after"
    """When a step of the run finished."""
    DATE = "date"
    """At the date or moment an input of the run names."""


class DeadlineRule(Value):
    """One deadline a process version declares, as its runs carry it."""

    name: str = Field(pattern=NAME)
    start: Start
    after: StepId | None = None
    """The step whose finish starts it, for `after`."""
    date_input: str | None = Field(default=None, min_length=1)
    """The input that names its moment, for `date`."""
    limit: timedelta
    lead: timedelta | None = None
    working: bool = False
    """True: the limit and the lead count in the tenant's working time."""
    until: StepId
    """The step whose finish meets it."""
    at_lead: DeadlineAction | None = None
    at_limit: DeadlineAction

    @model_validator(mode="after")
    def _sound(self) -> DeadlineRule:
        if (self.start is Start.AFTER) != (self.after is not None):
            raise ValueError("a deadline starts after a step exactly when it names one")
        if (self.start is Start.DATE) != (self.date_input is not None):
            raise ValueError("a deadline starts at a date exactly when it names its input")
        if self.limit < timedelta(0):
            raise ValueError("a limit is no shorter than nothing")
        if self.lead is not None and self.lead <= timedelta(0):
            raise ValueError("a lead time is longer than nothing")
        if (self.lead is None) != (self.at_lead is None):
            raise ValueError("a lead time and its action come together")
        return self


class DeadlineState(StrEnum):
    OPEN = "open"
    """Started and not met: it is listed, overdue once its limit passed."""
    MET = "met"
    """The step that meets it finished, or its run did."""


def deadline_id(run_id: str, name: str) -> str:
    """The one record a rule can have in one run: a run that records its starting moment again
    opens nothing new (ADR-0133 §2)."""
    digest = hashlib.sha256(f"{run_id}\x00{name}".encode()).hexdigest()[:24]
    return f"dl_{digest}"


class Deadline(Value):
    """One deadline started for one case."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    process_version: str = Field(min_length=1)
    rule: DeadlineRule
    started_at: datetime
    """The moment it counts from."""
    due_at: datetime
    """When it falls due: the limit, counted from `started_at` as the rule counts."""
    lead_at: datetime | None = None
    """When its lead time begins; None without one."""
    created_at: datetime
    """When the record was opened."""
    state: DeadlineState = DeadlineState.OPEN
    lead_taken_at: datetime | None = None
    reached_at: datetime | None = None
    """When the limit's action was taken."""
    refused: str | None = None
    """Why a start the action named was refused; None when nothing was refused."""
    started_run: str | None = None
    """The run an action of kind `start` started, at the lead time or the limit."""
    met_at: datetime | None = None
    met_through: str | None = None
    """What met it: `step` or `run_finished`."""

    @property
    def name(self) -> str:
        return self.rule.name

    def overdue(self, now: datetime) -> bool:
        return self.state is DeadlineState.OPEN and self.due_at <= now

    def link(self) -> str:
        """The case's page in the web app, relative to where the instance is served."""
        return f"app/#/runs/{self.run_id}"

    def roles(self) -> tuple[str, ...]:
        """The roles its actions taken so far went to."""
        taken: list[str] = []
        if self.lead_taken_at is not None and self.rule.at_lead is not None:
            taken.append(self.rule.at_lead.role or "")
        if self.reached_at is not None:
            taken.append(self.rule.at_limit.role or "")
        return tuple(r for r in taken if r)


DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class WorkingTime(Value):
    """One tenant's working time, stored under the tenant's own identifier (ADR-0133 §4)."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    zone: str = "UTC"
    days: tuple[int, ...] = (0, 1, 2, 3, 4)
    """The working days of the week: 0 is Monday, 6 is Sunday."""
    begins: time = time(9, 0)
    ends: time = time(17, 0)
    holidays: tuple[date, ...] = ()
    """Dates that are no working days, in the zone."""
    configured_at: datetime | None = None
    """When it was configured; None for the shipped default, which nobody configured."""

    @model_validator(mode="after")
    def _sound(self) -> WorkingTime:
        if self.id != self.tenant:
            raise ValueError(f"a working time is stored under its tenant {self.tenant!r}")
        if not self.days or any(d < 0 or d > 6 for d in self.days):
            raise ValueError("working days are at least one of 0 (Monday) to 6 (Sunday)")
        if len(set(self.days)) != len(self.days):
            raise ValueError("a working day is named once")
        if self.begins >= self.ends:
            raise ValueError("a working day begins before it ends")
        self.tz  # noqa: B018 — a zone that cannot be read is refused here, not when counted
        return self

    @property
    def tz(self) -> tzinfo:
        """The zone; UTC needs no time zone database."""
        if self.zone == "UTC":
            return UTC
        try:
            return ZoneInfo(self.zone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(f"{self.zone!r} is not a time zone") from error

    def describe(self) -> str:
        days = ",".join(DAYS[d] for d in sorted(self.days))
        return f"{days} {self.begins:%H:%M}-{self.ends:%H:%M} {self.zone}"


def shipped_working_time(tenant: str) -> WorkingTime:
    """Monday to Friday, 09:00 to 17:00 UTC, no holidays (NTC-0227)."""
    return WorkingTime(id=tenant, tenant=tenant)
