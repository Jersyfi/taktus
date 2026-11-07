"""What holds an incident open: a decision request of class `correction` its remediation raised
and nobody decided yet (UC-6.8 §2, ADR-0227 §3).

The requests are the decision component's and the remediation runs the run component's; the
composition answers this port from both."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from taktus.ports.persistence import Tenant


class OpenCorrections(Protocol):
    async def waiting(self, tenant: Tenant, incident_id: str) -> Sequence[str]:
        """The open requests of class `correction` raised by the incident's remediation runs,
        by identifier; empty where none waits."""
        ...
