"""Use case: the task a report opened in the ticket system was closed (ADR-0045).

**Closing a task is not an answer.** Nothing is filed: the report stays open, its history says
the task was closed, and `report.task_closed` records it. An answer is given in the owner's
channel and confirmed there, or on the decision component's own surface.
"""

from __future__ import annotations

from dataclasses import dataclass

from taktus.components.reporting.application.service._ledger import TASK_CLOSED, record
from taktus.components.reporting.domain.model import Happened, Report, ReportState
from taktus.ports.clock import Clock
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork


@dataclass(frozen=True)
class CloseTask:
    tenant: Tenant
    task: str
    """The task as the ticket system names it: the record its delivery made."""


class CloseTaskHandler:
    def __init__(
        self, reports: Repository[Report], work: UnitOfWork, ledger: Ledger, clock: Clock
    ) -> None:
        self._reports = reports
        self._work = work
        self._ledger = ledger
        self._clock = clock

    async def execute(self, command: CloseTask) -> Report | None:
        """The report whose task it was, unchanged but for its history; None when the task
        belongs to no report."""
        async with self._work.transaction(command.tenant):
            reports = await self._reports.list(command.tenant)
            report = next(
                (
                    r
                    for r in reports
                    if (task := r.task()) is not None and command.task in (task.record, task.url)
                ),
                None,
            )
            if report is None:
                return None
            outcome = "after_filing" if report.state is ReportState.FILED else "nothing_filed"
            noted = report.model_copy(
                update={
                    "history": (
                        *report.history,
                        Happened(at=self._clock.now(), event="task_closed"),
                    )
                }
            )
            await self._reports.put(command.tenant, noted)
            await record(self._ledger, noted, TASK_CLOSED, outcome)
        return noted
