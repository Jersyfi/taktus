"""What a broken interface is noticed from (ADR-0047).

**`Failures`** is the run's record of failed calls that speak about their interface: every
`interface.failed` entry of the tenant's ledger, a rehearsal's left out. The composition root
binds it to the run's query; this component never imports the run.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from taktus.components.reporting.domain.model import FailedCall
from taktus.ports.persistence import Tenant


class Failures(Protocol):
    async def failures(self, tenant: Tenant) -> Sequence[FailedCall]:
        """Every failed call the run recorded for the tenant, oldest first."""
        ...
