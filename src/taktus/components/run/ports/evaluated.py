"""Which models of a step's purpose have passed a trial on the cases of the step's process, seen
from the run (ADR-0249).

The trials, the evaluation cases and their scores live in the composition root, which answers
this port; components never import each other. A step its process does not evaluate has nothing
to pass, and every answer for it leaves the route as it was.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Protocol

from taktus.ports.persistence import Tenant


class Evaluated(Protocol):
    async def unevaluated(
        self,
        tenant: Tenant,
        process_version: str,
        step_id: str,
        purpose: str,
        adapters: Collection[str],
    ) -> frozenset[str]:
        """Of these model adapters, those that may not serve the step in a real run: its
        process evaluates the step on cases, and no settled trial of the purpose found the
        quality held with that model. Opens its own unit of work."""
        ...
