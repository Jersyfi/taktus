"""A process version's deadlines, seen from the run (ADR-0133, UC-4.17).

The process component owns what a version declares. The run asks for its deadlines once, when
it creates a run, and the run carries the copy from then on. The composition root answers from
the process component, because components never import each other.
"""

from __future__ import annotations

from typing import Protocol

from taktus.components.run.domain.model.deadline import DeadlineRule
from taktus.ports.persistence import Tenant


class DeclaredDeadlines(Protocol):
    async def deadlines(self, tenant: Tenant, process_version: str) -> tuple[DeadlineRule, ...]:
        """The deadlines the version declares, in the order it declares them; none when it
        declares none or is not known."""
        ...
