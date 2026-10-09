"""The ledger entries of the owner-facing channel: content-free, each pointing at the report it
is about (ADR-0006). The renderings are composed from that record, never from the entry."""

from __future__ import annotations

import hashlib
import re

from taktus.components.reporting.domain.model import Report, ReportKind
from taktus.ports.ledger import Fact, Ledger
from taktus.shared.v1 import LedgerRefs

CONFIGURED = "owner_channel.configured"
RAISED = "report.raised"
DELIVERED = "report.delivered"
ANSWERED = "report.answered"
FILED = "report.filed"
TASK_CLOSED = "report.task_closed"


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def key(report_id: str, *parts: str) -> str:
    """An idempotency key for one delivery of one report: a delivery repeated after a restart
    is said once."""
    raw = ":".join(("taktus", "report", report_id, *parts))
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]", "-", raw)
    if len(cleaned) <= 128:
        return cleaned
    return "taktus:report:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


async def record(
    ledger: Ledger,
    report: Report,
    kind: str,
    outcome: str,
    *,
    actor: str | None = None,
    text: str | None = None,
) -> None:
    await ledger.record(
        report.tenant,
        Fact(
            kind=kind,
            refs=LedgerRefs(
                tenant=report.tenant,
                report_id=report.id,
                decision_request_id=report.id if report.kind is ReportKind.DECISION else None,
                actor=actor,
            ),
            outcome=outcome,
            content_digest=None if text is None else digest(text),
        ),
    )
