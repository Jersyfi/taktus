"""Where a tenant's data may be processed, seen from the run (ADR-0116 §3, UC-11.1)."""

from __future__ import annotations

from typing import Protocol

from taktus.ports.model import Permitted
from taktus.ports.persistence import Tenant


class Residency(Protocol):
    async def permitted(
        self, tenant: Tenant, data_class: str | None, process: str | None = None
    ) -> Permitted:
        """The location the tenant's rule permits for data of the class in a run of the
        process — the narrowest of the class's rule, the process's and the tenant's own.
        `anywhere` for a tenant that set no rule (ADR-0258)."""
        ...
