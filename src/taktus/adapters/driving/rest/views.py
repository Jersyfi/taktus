"""How a record is shown to a reader where more than one surface shows it: the HTTP surface and
the MCP surface (ADR-0131)."""

from __future__ import annotations

from typing import Any

from taktus.components.decision.application.query import Addressed


def decision_view(addressed: Addressed, reader: str) -> dict[str, Any]:
    """A request as a decider sees it. Who answered and when is shown to that person alone:
    the time it took is theirs (ADR-0015)."""
    request = addressed.request
    yours = request.answered_by == reader
    view: dict[str, Any] = {
        "id": request.id,
        "decider": request.decider,
        "anchor": request.anchor,
        "raised_at": request.raised_at.isoformat(),
        "overdue": addressed.overdue,
        "answered_by_you": yours,
        "request": request.request.document(),
    }
    if yours and request.reflection is not None:
        view["reflection"] = request.reflection
    return view
