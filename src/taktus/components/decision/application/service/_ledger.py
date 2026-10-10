"""The ledger entries of a decision request: content-free, linked to the run, the step and the
request (ADR-0006)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from taktus.components.decision.domain.model import Request
from taktus.components.decision.domain.model.recorded import (
    ANSWERED,
    APPLIED,
    CONFIRMED,
    INTERPRETED,
    RAISED,
    REREAD,
)
from taktus.ports.ledger import Fact, Ledger
from taktus.shared.v1 import LedgerRefs

__all__ = ["ANSWERED", "APPLIED", "CONFIRMED", "INTERPRETED", "RAISED", "REREAD", "record"]


def digest(document: dict[str, Any]) -> str:
    canonical = json.dumps(document, ensure_ascii=False, sort_keys=True)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def record(
    ledger: Ledger,
    request: Request,
    kind: str,
    outcome: str,
    *,
    actor: str | None = None,
    document: dict[str, Any] | None = None,
) -> None:
    await ledger.record(
        request.tenant,
        Fact(
            kind=kind,
            refs=LedgerRefs(
                tenant=request.tenant,
                run_id=request.request.raised_by.run,
                step_id=request.request.raised_by.step,
                decision_request_id=request.id,
                actor=actor,
            ),
            outcome=outcome,
            content_digest=None if document is None else digest(document),
        ),
    )
