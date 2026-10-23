"""A worker's event as a line of its step's trace (ADR-0135 §1, UC-6.14).

The line keeps what the worker contract carries for the event beyond its envelope — the
assignment, the `seq`, the time and the type are fields of their own. Every text in it is
masked before it is kept: a secret value the instance holds never reaches the trace, whatever
a worker reported. A tool's arguments are a digest already (W-09) and stay one.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from taktus.ports.traces import TraceLine
from taktus.ports.worker import Event

ENVELOPE = frozenset({"assignment_id", "seq", "ts", "type"})


def line_of(
    event: Event,
    *,
    run_id: str,
    step_id: str,
    recorded_at: datetime,
    mask: Callable[[str], str],
) -> TraceLine:
    document = event.model_dump(mode="json", by_alias=True, exclude_none=True)
    detail = {key: _masked(value, mask) for key, value in document.items() if key not in ENVELOPE}
    return TraceLine(
        run_id=run_id,
        step_id=step_id,
        assignment_id=event.assignment_id,
        seq=event.seq,
        ts=event.ts,
        type=event.type,
        detail=detail,
        recorded_at=recorded_at,
    )


def _masked(value: Any, mask: Callable[[str], str]) -> Any:
    if isinstance(value, str):
        return mask(value)
    if isinstance(value, list):
        return [_masked(v, mask) for v in value]
    if isinstance(value, dict):
        return {k: _masked(v, mask) for k, v in value.items()}
    return value
