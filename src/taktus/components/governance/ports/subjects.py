"""What a data-protection request needs from outside this component (ADR-0176 §9).

The runs, their provenance, their traces and the object store belong to other components and
ports. The composition root answers each of these, because components never import each other.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from taktus.components.governance.domain.model.subjects import Erased, Holding
from taktus.ports.persistence import Tenant


class SubjectHoldings(Protocol):
    async def holdings(self, tenant: Tenant, subject: str) -> Sequence[Holding]:
        """Every run of the tenant that served a case of the subject, found through its
        provenance records and its intake, oldest first. Changes nothing."""
        ...

    async def erase(self, tenant: Tenant, request_id: str, holdings: Sequence[Holding]) -> Erased:
        """The content of every ended run among the holdings erased, and the record of what
        happened verified after it (ADR-0176 §3, §4)."""
        ...

    async def export(
        self, tenant: Tenant, holdings: Sequence[Holding], *, processing: bool
    ) -> Mapping[str, Any]:
        """The holdings with their content, as one JSON document; with `processing`, the
        adapter, its location and the keeping of every holding as well (ADR-0176 §5)."""
        ...
