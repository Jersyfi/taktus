"""What an alert is noticed from (ADR-0106).

**`Signals`** reads what other parts of the instance recorded for a tenant: the capacity
crossings and the lost claims of its ledger, a rehearsal's left out, and the state of its
backups. The composition root binds it to the ledger and to the backup log; this component
imports neither the run nor the governance component.
"""

from __future__ import annotations

from typing import Protocol

from taktus.components.reporting.domain.model.alert import Signalled
from taktus.ports.persistence import Tenant


class Signals(Protocol):
    async def signalled(self, tenant: Tenant) -> Signalled:
        """Everything recorded for the tenant that an alert is made from, read once."""
        ...
