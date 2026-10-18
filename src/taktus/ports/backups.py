"""What the instance knows of its backups: the outcome every run of the backup program recorded
(ADR-0106, amending ADR-0087).

The backup is a program of its own that imports nothing of Taktus (ADR-0013 C). At the end of
every run it records one outcome per tenant in the database it backs up. This port reads a
tenant's outcomes, inside the tenant's unit of work. Every field is a time, a name of the
program's form, `ok` or `failed`, or the token of the step that failed: nothing the program
printed reaches it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol

from pydantic import Field

from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Value

NAME_PATTERN = r"^taktus-\d{8}T\d{6}Z$"
REASONS: frozenset[str] = frozenset(
    {"configuration", "database", "encryption", "objects", "store", "retention"}
)
"""The steps a run can fail at, as the program names them (`deploy/backup/backup.py`)."""

FAILURES_READ = 30
"""How many failed runs after the last success are read at most: a month of a daily schedule."""


class BackupOutcome(Value):
    """One run of the backup, as it recorded itself."""

    name: str = Field(pattern=NAME_PATTERN)
    at: datetime
    outcome: Literal["ok", "failed"]
    reason: str | None = Field(default=None, pattern=r"^[a-z]+$")
    """The step that failed; None for `ok`."""


class BackupHistory(Value):
    """A tenant's backups as far as they say what to do: the last success, and the failures
    since, newest first."""

    last_ok: BackupOutcome | None = None
    failed: tuple[BackupOutcome, ...] = ()
    """At most `FAILURES_READ` of them; `failed_count` counts all."""
    failed_count: int = Field(default=0, ge=0)


class BackupLog(Protocol):
    async def history(self, tenant: Tenant) -> BackupHistory:
        """The tenant's last successful backup and every failed one since, inside the open unit
        of work."""
        ...
