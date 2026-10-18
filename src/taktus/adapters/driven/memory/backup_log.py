"""The backup outcomes in memory, for development and tests (ADR-0106).

Nothing writes here in development: the backup program writes to the database it backs up. A
test records outcomes with `record`, as that program would. Read inside a unit of work of the
tenant, as the database adapter is.
"""

from __future__ import annotations

from collections import defaultdict

from taktus.adapters.driven.memory.persistence import MemoryPersistence
from taktus.ports.backups import FAILURES_READ, BackupHistory, BackupOutcome
from taktus.ports.persistence import Tenant


class MemoryBackupLog:
    def __init__(self, persistence: MemoryPersistence) -> None:
        self._persistence = persistence
        self._outcomes: dict[Tenant, list[BackupOutcome]] = defaultdict(list)

    def record(self, tenant: Tenant, outcome: BackupOutcome) -> None:
        """What the backup program does at the end of a run, for one tenant."""
        self._outcomes[tenant].append(outcome)

    async def history(self, tenant: Tenant) -> BackupHistory:
        self._persistence.current(tenant)
        newest_first = sorted(self._outcomes[tenant], key=lambda o: o.at, reverse=True)
        last_ok = next((o for o in newest_first if o.outcome == "ok"), None)
        failed = [
            o
            for o in newest_first
            if o.outcome == "failed" and (last_ok is None or o.at > last_ok.at)
        ]
        return BackupHistory(
            last_ok=last_ok, failed=tuple(failed[:FAILURES_READ]), failed_count=len(failed)
        )
