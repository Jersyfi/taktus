"""What the capacity report speaks about (docs/architecture/platform.md, *Observe*): the places
the state grows in, how fast it grows, the thresholds a person has agreed to be told at, and
the findings — a figure and a date, never a warning light."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from taktus.ports.platform import Headroom, Unobserved
from taktus.shared.v1 import Value
from taktus.shared.v1.ledger_entry import KIND_PATTERN


class Status(StrEnum):
    OK = "ok"
    """Nothing to do before the next report."""
    ACT = "act"
    """A person must act: the threshold is crossed, or will be within the agreed horizon."""
    UNKNOWN = "unknown"
    """The platform did not say; the finding says why."""


class CapacityThresholds(Value):
    """Named, configured, with defaults — never a constant hidden in a function. The daemon
    and `taktusctl` read them from `TAKTUS_CAPACITY_*` (`.env.example`)."""

    storage_warn_free_percent: float = Field(default=10.0, gt=0, lt=100)
    """Below this share of a volume free, a person must act."""
    act_within_days: int = Field(default=30, ge=1)
    """A person is told this many days before the storage threshold is crossed at the observed
    growth — the time a migration to a larger volume needs, not the time a disk takes to
    fill."""
    memory_warn_free_percent: float = Field(default=10.0, gt=0, lt=100)
    cpu_warn_free_percent: float = Field(default=10.0, gt=0, lt=100)
    window_days: int = Field(default=14, ge=1)
    """Runs per day are counted over this many days, or over the instance's life if shorter."""


class StorageStore(Value):
    """One place the state grows in: the state directory's filesystem, the database's
    volume."""

    name: str = Field(min_length=1)
    """For a person: `state directory`, `database`."""
    label: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    """For the ledger: `state_directory`, `database`."""
    adapter: str = Field(min_length=1)
    """Who observed it: the adapter identifier the ledger entry names."""
    reading: Headroom | Unobserved
    used_bytes: int | None = Field(default=None, ge=0)
    """What the state occupies there now; None when it could not be measured."""
    expandable: bool | None = None
    """Whether the volume can be grown in place; None when nobody has said."""


class RunActivity(Value):
    """How much work the state holds and how fast it arrives, from the ledger."""

    runs: int = Field(ge=0)
    """Runs the state holds: every `run.created` of the tenants this instance serves."""
    recent: int = Field(ge=0)
    """Of them, created within the window."""
    window_days: float = Field(gt=0)
    """The window the recent runs were counted over."""

    @property
    def runs_per_day(self) -> float:
        return self.recent / self.window_days


type Resource = Literal["storage", "memory", "cpu"]


class Finding(Value):
    """One resource, one sentence with figures and dates, and the figures on their own for a
    reader that computes."""

    resource: Resource
    subject: str = Field(min_length=1)
    kind: str = Field(pattern=KIND_PATTERN)
    """The ledger kind a crossing of this finding is recorded under: `capacity.memory`,
    `capacity.storage.database`."""
    adapter: str = Field(min_length=1)
    status: Status
    text: str = Field(min_length=1)
    free: float | None = None
    total: float | None = None
    used_bytes: int | None = None
    bytes_per_run: float | None = None
    runs_per_day: float | None = None
    threshold_on: date | None = None
    """The day the warning threshold is crossed at the observed growth; today when it is."""
    full_on: date | None = None
    """The day the volume is full at the observed growth."""

    @property
    def recorded(self) -> bool:
        """Whether a crossing of this finding is written to the ledger: storage and memory,
        whose exhaustion stops work. A busy CPU slows work down and is reported only."""
        return self.resource in ("storage", "memory")


class CapacityReport(Value):
    at: datetime
    findings: tuple[Finding, ...]
    recorded: tuple[str, ...] = ()
    """The ledger kinds written by this report, with their new status: `capacity.memory=act`."""

    @property
    def act(self) -> bool:
        return any(f.status is Status.ACT for f in self.findings)
