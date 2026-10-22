"""What keeps the operation running, read for the HTTP surface (ADR-0121, DEC-0218).

The incidents are the governance component's (ADR-0107). The alerts and the backup's state are
the reporting component's, made by the rules the scheduler reports them by (ADR-0106). The
signals are judged against their corridors by the reporting component's rule (ADR-0109). The
components never import each other; this is where the surface reads all of them. Nothing here
decides anything: each read asks the component that owns the record, as `taktusctl` does.
"""

from __future__ import annotations

from collections.abc import Sequence

from taktus.components.governance.application.service import ExpectedRuns
from taktus.components.governance.domain.model import Incident
from taktus.components.reporting.application.service import (
    Alerted,
    Alerts,
    BackupWatched,
    SignalWatch,
)
from taktus.components.reporting.domain.model import Corridor, Judged
from taktus.ports.persistence import Tenant


class OperationRecords:
    def __init__(self, incidents: ExpectedRuns, alerts: Alerts, signals: SignalWatch) -> None:
        self._incidents = incidents
        self._alerts = alerts
        self._signals = signals

    async def incidents(self, tenant: Tenant) -> Sequence[Incident]:
        """Every incident, open and closed, newest first."""
        return await self._incidents.incidents(tenant, every=True)

    async def alerts(self, tenant: Tenant) -> Sequence[Alerted]:
        """Every alert, in effect, cleared and closed, each with what became of its report."""
        return await self._alerts.noticed(tenant)

    async def backup(self, tenant: Tenant) -> BackupWatched:
        return await self._alerts.backup(tenant)

    async def signals(self, tenant: Tenant) -> Sequence[tuple[Corridor, Judged]]:
        """Every signal in force, judged now against its corridor."""
        return await self._signals.judged(tenant)
