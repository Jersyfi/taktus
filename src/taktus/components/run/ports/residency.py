"""Where a tenant's data may be processed, seen from the run (ADR-0116 §3, UC-11.1)."""

from __future__ import annotations

from typing import Protocol

from taktus.ports.model import Permitted
from taktus.ports.persistence import Tenant


class Residency(Protocol):
    async def permitted(self, tenant: Tenant, data_class: str | None) -> Permitted:
        """The location the tenant's rule permits for data of the class — the rule for the
        class, or the tenant's own where the class has none or none is named. `anywhere` for
        a tenant that set no rule."""
        ...
