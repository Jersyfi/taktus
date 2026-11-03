"""A result a person corrected is assessed by itself, and raised as a result defect (#92,
ADR-0184, UC-4.11, UC-4.12).

A correction is the ledger entry `step.corrected` (`run/application/service/correct_result.py`).
Until now its assessment waited for a person to run `taktusctl defect assess` and `raise`. The
scheduler now looks once an interval at every correction of the tenant that no result-defect
incident answers yet, and raises one through the governance component's `ResultDefects`: the
window, the impact over the provenance chain, the tenant's rule and the remediation plan, the
same as by hand. A result without a provenance record cannot be assessed; it is logged and
looked at again at the next interval, never raised blind.

The incident is the tenant's; nothing here corrects anything. A correction of a result that left
the system stays with a person (ADR-0022), and the plan says what to do. This is wiring, because
the correction is the run component's record and the incident the governance component's.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

import structlog

from taktus.components.governance.application.service import ResultDefects
from taktus.components.governance.application.service.result_defects import ReportDefect
from taktus.components.governance.domain.model.defects import Found
from taktus.components.governance.domain.service.defects import NotRecorded
from taktus.components.process.domain.service.autonomy import is_result_defect
from taktus.composition.tenancy import this_round
from taktus.ports.clock import Clock
from taktus.ports.identity import ServedTenants
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Tenant, UnitOfWork

log = structlog.get_logger("taktusd")

CORRECTED = "step.corrected"
RAISED = "incident.raised"
INTERVAL_SECONDS = 300
"""How often the scheduler looks for corrections nobody assessed: five minutes."""


class DefectWatch:
    def __init__(self, ledger: Ledger, defects: ResultDefects, work: UnitOfWork) -> None:
        self._ledger = ledger
        self._defects = defects
        self._work = work

    async def sweep(self, tenant: Tenant) -> list[str]:
        """Every correction no result-defect incident answers yet, assessed and raised: the
        incidents raised now. A rehearsal's correction is none: a rehearsal's result never
        counted."""
        async with self._work.transaction(tenant):
            entries = await self._ledger.of_kinds(tenant, (CORRECTED, RAISED))
        answered = {(e.refs.run_id, e.refs.step_id) for e in entries if is_result_defect(e)}
        pending: list[tuple[str, str]] = []
        for entry in entries:
            if entry.kind != CORRECTED or entry.rehearsal:
                continue
            run_id, step_id = entry.refs.run_id, entry.refs.step_id
            if run_id is None or step_id is None or (run_id, step_id) in answered:
                continue
            if (run_id, step_id) not in pending:
                pending.append((run_id, step_id))
        raised: list[str] = []
        for run_id, step_id in pending:
            command = ReportDefect(
                tenant=tenant, run_id=run_id, step_id=step_id, found=Found.CORRECTED
            )
            try:
                incident, _ = await self._defects.raise_incident(command)
            except NotRecorded as missing:
                log.warning(
                    "a corrected result has no provenance record; it is not assessed",
                    tenant=tenant,
                    run=run_id,
                    step=step_id,
                    reason=str(missing),
                )
                continue
            raised.append(incident.id)
        return raised


def defects_tick(
    watch: DefectWatch,
    tenants: ServedTenants,
    clock: Clock,
    *,
    interval_seconds: int = INTERVAL_SECONDS,
) -> Callable[[], Awaitable[None]]:
    """What the scheduler calls on every tick: every tenant's corrections are looked at once the
    interval has passed. A sweep that fails is logged and made again at the next interval: it
    never stops the scheduler."""
    last: list[datetime] = []

    async def tick() -> None:
        now = clock.now()
        if last and now - last[0] < timedelta(seconds=interval_seconds):
            return
        last[:] = [now]
        for tenant in await this_round(tenants, "scheduler"):
            try:
                raised = await watch.sweep(tenant)
            except Exception as error:  # a sweep must never take the scheduler down
                log.error(
                    "corrections not assessed; the next sweep tries again",
                    tenant=tenant,
                    error=f"{type(error).__name__}: {error}",
                )
                continue
            for incident in raised:
                log.info("a corrected result was raised as a result defect", incident=incident)

    return tick


__all__ = ["DefectWatch", "defects_tick"]
