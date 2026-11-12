"""Where a rule's decision to stop a process goes (ADR-0023, ADR-0256 §3, UC-7.2).

The stops are the run component's; the composition answers this port from them. The rule
decides; this port only carries the decision out and names the stop it made.
"""

from __future__ import annotations

from typing import Protocol

from taktus.ports.persistence import Tenant


class ProcessStops(Protocol):
    async def stop_process(self, tenant: Tenant, process: str, *, rule: str, incident: str) -> str:
        """Stop every run of the process at its next boundary, as the rule that fired decided;
        the stop's identifier. A stop of the process already held is the one returned."""
        ...
