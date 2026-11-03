"""The exactness statement of the version a run executes, seen from the run (UC-6.9).

A step that delivers a report carries the statement of the checks behind its numbers by the
reference `{"$run": "exactness"}`: the statement as the process component renders it, unchanged.
The process component generates it from the version; the composition root answers this port
from it, because components never import each other.
"""

from __future__ import annotations

from typing import Protocol

from taktus.ports.persistence import Tenant


class Statements(Protocol):
    async def rendered(self, tenant: Tenant, process_version: str) -> str | None:
        """The statement of the version as a person reads it; None where the version is not
        registered, as for a plan run without one."""
        ...
