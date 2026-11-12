"""Where a run's control sits, seen from the run (UC-5.2, ADR-0272).

A process version declares whether Taktus controls it or an external tool does. In the decoupled
mode the external tool's state of the task is the authority: the run asks at every step boundary
whether the task was withdrawn there, and is not continued past it when it was. The version is
the process component's and the external tool is reached through a connector; the composition
root answers this port from both, because components never import each other.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from taktus.components.run.domain.model import Run


class ExternalControl(Protocol):
    async def withdrawn(self, run: Run) -> str | None:
        """Why the run is not continued past this boundary — the external tool withdrew its
        task — in words; None where the run is controlled by Taktus, or its task stands."""
        ...
