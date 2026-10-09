"""The read side: the third rendering of a report, the view with its history (ADR-0045).

The view is the report itself — the same identifier, the same items, the same date as the
repository text and the message — with every delivery and everything that happened since it was
raised. A delivery that failed is in it, with its reason.

**Who reads it.** The owner and the people the owner named: the same identities whose answers
are filed. **Whom it names.** Nobody: an entry of the history says whether the reader acted, not
who did. How long a person took to answer is theirs (ADR-0015), and a view that named the
answerer beside the times would show it to everyone who reads the view.
"""

from __future__ import annotations

from typing import Any

from taktus.components.reporting.domain.model import OwnerChannel, Report
from taktus.ports.persistence import Repository, Tenant, UnitOfWork


def view(report: Report, reader: str) -> dict[str, Any]:
    document = report.document()
    document["history"] = [
        {"at": h.at.isoformat(), "event": h.event, "by_you": h.by == reader} for h in report.history
    ]
    if report.reading is not None:
        document["reading"] = {
            "answer": report.reading.answer,
            "kept": report.reading.kept,
            "at": report.reading.at.isoformat(),
            "by_you": report.reading.by == reader,
        }
    if report.filed is not None:
        filed = report.filed.document()
        filed.pop("by")
        filed["by_you"] = report.filed.by == reader
        document["filed"] = filed
    return document


class ReportQueries:
    def __init__(
        self, reports: Repository[Report], channels: Repository[OwnerChannel], work: UnitOfWork
    ) -> None:
        self._reports = reports
        self._channels = channels
        self._work = work

    async def may_read(self, tenant: Tenant, reader: str) -> bool:
        """The owner and the people the owner named read the reports."""
        async with self._work.transaction(tenant):
            channel = await self._channels.get(tenant, tenant)
        return channel is not None and channel.may_answer(reader)

    async def reports(self, tenant: Tenant) -> list[Report]:
        """Every report of the tenant, the open ones first and the earliest due first."""
        async with self._work.transaction(tenant):
            reports = await self._reports.list(tenant)
        return sorted(reports, key=lambda r: (r.filed is not None, r.due, r.raised_at))

    async def one(self, tenant: Tenant, report_id: str) -> Report | None:
        async with self._work.transaction(tenant):
            return await self._reports.get(tenant, report_id)
