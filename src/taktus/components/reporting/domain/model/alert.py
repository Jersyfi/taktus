"""What needs a person's action, noticed from recorded facts (ADR-0106, issue #323).

Five signals, each read from what another part of the instance recorded:

- a **capacity crossing**: a `capacity.<resource>` entry of the ledger, outcome `act` when a
  storage or memory finding turned to *act*, `ok` when it cleared (platform.md §3);
- a **lost claim**: a `run.claim_lost` entry, written when a runner learned that another runner
  had taken its run over;
- the **backup's state**: the last successful backup and the failed ones since, as the backup
  program recorded them, and when the tenant began to be watched;
- a **level lowered** by rule: an incident the governance component raised when a process
  breached an anchor or a correction rate rose above the tenant's limit (ADR-0110);
- a **raise proposed** on the corrections: Taktus proposes it, and only a person applies it.

An **alert** is one condition made from them, with the words its report is said in. It goes to
the owner of the tenant through the owner-facing channel, as a report of kind `failure`
(ADR-0045). Every field is an identifier, a time, a count or a token, each held to a pattern, so
that no content and no person can pass into it (ADR-0006, principle 14).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from taktus.components.reporting.domain.model.finding import RUN_PATTERN
from taktus.shared.v1 import Value

CAPACITY_KIND_PATTERN = r"^capacity\.[a-z_]+(\.[a-z_]+)*$"
BACKUP_NAME_PATTERN = r"^taktus-\d{8}T\d{6}Z$"

ACTION_PATTERN = r"^[a-z][a-z0-9_-]*(\.[a-z][a-z0-9_-]*)+$"
VERSION_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*@[A-Za-z0-9][A-Za-z0-9.+_-]*$"
STEP_PATTERN = r"^[a-z][a-z0-9_.-]*$"
type Identifier = Annotated[
    str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$", max_length=128)
]

type AlertKind = Literal["capacity", "claim_lost", "backup", "lowered", "raise"]

ID_PREFIXES: dict[str, str] = {
    "capacity": "capacity-",
    "claim_lost": "claim-lost-",
    "backup": "backup-",
    "lowered": "level-lowered-",
    "raise": "raise-proposed-",
}
"""Every report of an alert has an identifier that starts with its kind's prefix."""


class CapacityCrossing(Value):
    """One `capacity.<resource>` entry: where in the chain, when, which kind, which status."""

    seq: int = Field(ge=1)
    at: datetime
    kind: str = Field(pattern=CAPACITY_KIND_PATTERN, max_length=128)
    outcome: Literal["act", "ok"]


class ClaimLost(Value):
    """One `run.claim_lost` entry: a runner learned that it no longer held the run's claim."""

    seq: int = Field(ge=1)
    at: datetime
    run_id: str = Field(pattern=RUN_PATTERN, max_length=128)


class BackupRun(Value):
    """One run of the backup as it recorded itself."""

    name: str = Field(pattern=BACKUP_NAME_PATTERN)
    at: datetime
    reason: str | None = Field(default=None, pattern=r"^[a-z]+$")
    """The step a failed run failed at; None for a run that succeeded."""


class BackupState(Value):
    """The tenant's backups as far as they say what to do."""

    watched_since: datetime | None
    """When the tenant began to be watched: its creation. None when it is not known, and then a
    tenant without any successful backup is not reported as missing one."""
    expected_hours: int | None = Field(default=None, ge=1)
    """How old the last success may be; None: a missing backup is not watched."""
    last_ok: BackupRun | None = None
    failed: tuple[BackupRun, ...] = ()
    """The failed runs after the last success, newest first, as far as they were read."""
    failed_count: int = Field(default=0, ge=0)


class LevelLowered(Value):
    """One incident about a level that fell by rule, as far as its report needs it."""

    incident: str = Field(pattern=r"^inc_[0-9a-f]+$")
    at: datetime
    process_version: str = Field(pattern=VERSION_PATTERN, max_length=256)
    action: str | None = Field(default=None, pattern=ACTION_PATTERN, max_length=256)
    rule: Literal["anchor.breach", "corrections.rate"]
    before: int = Field(ge=1, le=4)
    after: int = Field(ge=1, le=4)
    anchors: tuple[Identifier, ...] = ()
    """For a breach: the anchors that name the act, by identifier."""
    run_id: str | None = Field(default=None, pattern=RUN_PATTERN, max_length=128)
    step_id: str | None = Field(default=None, pattern=STEP_PATTERN, max_length=128)
    decided: int | None = Field(default=None, ge=0)
    """For a rate: how many decisions the window counted."""
    rate: float | None = Field(default=None, ge=0, le=1)
    limit: float | None = Field(default=None, ge=0, le=1)
    window_days: float | None = Field(default=None, gt=0)


class RaiseProposed(Value):
    """One raise Taktus proposed on the corrections, with its figures."""

    seq: int = Field(ge=1)
    at: datetime
    process_version: str = Field(pattern=VERSION_PATTERN, max_length=256)
    action: str | None = Field(default=None, pattern=ACTION_PATTERN, max_length=256)
    week_decided: int = Field(ge=0)
    week_rate: float = Field(ge=0, le=1)
    month_decided: int = Field(ge=0)
    month_rate: float = Field(ge=0, le=1)
    counted_since: datetime


class Signalled(Value):
    """Everything recorded for one tenant that an alert is made from."""

    capacity: tuple[CapacityCrossing, ...] = ()
    """Oldest first."""
    claims_lost: tuple[ClaimLost, ...] = ()
    """Oldest first."""
    backup: BackupState
    lowered: tuple[LevelLowered, ...] = ()
    """Oldest first."""
    raises: tuple[RaiseProposed, ...] = ()
    """Oldest first."""


class Alert(Value):
    """One condition that needs a person's action, with its report's words."""

    id: str = Field(pattern=r"^[a-z][a-z-]*-[0-9a-f]{16}$")
    """Derived from the facts and never stored: the identifier of its report."""
    kind: AlertKind
    since: datetime
    """When the condition was first recorded."""
    in_effect: bool
    """False once the facts say it is over: it cleared."""
    title: str = Field(min_length=1)
    needed: tuple[str, ...] = Field(min_length=1)
    steps: tuple[str, ...] = Field(min_length=1)
    standing_still: tuple[str, ...] = Field(min_length=1)
    summary: str = Field(min_length=1)
    """One line for the operator's view."""
