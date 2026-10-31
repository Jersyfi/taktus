"""The evidence of an installation's processing, drawn from facts (ADR-0176 §8, UC-11.2).

What is processed, by which adapter, where, and kept how long. Every part comes from the
register of what acts for the tenant (ADR-0147), the tenant's declarations and the ledger; the
composition gathers them, and nothing here reads or stores anything. The document is marked as
not legally reviewed, as the register's inventory is.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from datetime import datetime
from typing import Any

from taktus.components.reporting.domain.model.acting import Register
from taktus.components.reporting.domain.service.acting import NOT_LEGALLY_REVIEWED

FOR_GOOD = "for good; written once, never changed"


def keeping(trace_days: int | None) -> list[dict[str, Any]]:
    """How long each kind of record is kept, and what it holds."""
    return [
        {
            "record": "ledger",
            "holds": "identifiers, tokens and digests of what happened; no content (ADR-0006)",
            "kept": FOR_GOOD,
        },
        {
            "record": "provenance",
            "holds": "what produced each result, from which inputs, by identifier and digest; "
            "the subject's identifier where a step served a case (ADR-0021, ADR-0130)",
            "kept": FOR_GOOD,
        },
        {
            "record": "run content",
            "holds": "a run's inputs, its steps' stored results, artifacts and messages",
            "kept": "until a person erases it on a data-protection request (ADR-0176)",
        },
        {
            "record": "trace",
            "holds": "what a worker reported while it worked a step, every secret masked",
            "kept": "not kept: no trace store is configured"
            if trace_days is None
            else f"{trace_days} days from when it was read, then erased (ADR-0135)",
        },
        {
            "record": "backup",
            "holds": "a copy of the database and the artifacts",
            "kept": "as the operator configured the backups, outside Taktus (ADR-0087)",
        },
    ]


def processing(
    register: Register,
    *,
    personal: Collection[str],
    scoped: Collection[tuple[str, str]],
    permitted: str,
    retention_days: int | None,
    requests: Mapping[str, int],
    generated_at: datetime,
) -> dict[str, Any]:
    """The evidence as one JSON document. `personal`: the capabilities the tenant declares
    personal; `scoped`: the steps of active versions, as (process, step), that declare a case
    scope; `requests`: the tenant's `subject.*` entries, counted by kind."""
    declared = frozenset(personal)
    cases = frozenset(scoped)
    steps: list[dict[str, Any]] = []
    adapters: list[dict[str, Any]] = []
    for row in register.rows:
        adapters.append(
            {
                "adapter": row.adapter,
                "kind": row.family,
                "serves": list(row.serves),
                "location": row.location or "undeclared",
                "within_residency_rule": row.residency,
                "used": {
                    "days": row.used.days,
                    "runs": row.used.runs,
                    "steps": row.used.steps,
                },
            }
        )
        for use in row.uses:
            case = (use.process_id, use.step_id) in cases
            if not case and use.served not in declared:
                continue
            steps.append(
                {
                    "process": use.process_id,
                    "version": use.version,
                    "step": use.step_id,
                    "serves": use.served,
                    "personal_data": "a case of one subject" if case else "declared personal",
                    "adapter": row.adapter,
                    "location": row.location or "undeclared",
                    "within_residency_rule": row.residency,
                }
            )
    steps.sort(key=lambda s: (s["process"], s["step"], s["adapter"]))
    return {
        "tenant": register.tenant,
        "generated_at": generated_at.isoformat(),
        "legally_reviewed": False,
        "notice": NOT_LEGALLY_REVIEWED,
        "residency_rule": permitted,
        "personal_capabilities": sorted(declared),
        "personal_data_steps": steps,
        "adapters": adapters,
        "keeping": keeping(retention_days),
        "requests": {
            "prepared": requests.get("subject.request_prepared", 0),
            "erased": requests.get("subject.erased", 0),
            "exported": requests.get("subject.exported", 0),
            "rectified": requests.get("subject.rectified", 0),
            "withdrawn": requests.get("subject.request_withdrawn", 0),
        },
    }
