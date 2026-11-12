"""The citation of an answer drawn from knowledge, seen from the run (UC-5.5, ADR-0265 §3).

A step of the rule `citation` hands over the answer, the documents a search read and the
versions a later reading found. The knowledge component cites the answer and records what was
read into its index; the composition root answers this port from it, because components never
import each other.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from taktus.ports.persistence import Tenant


class Citations(Protocol):
    async def cite(
        self,
        tenant: Tenant,
        *,
        capability: str,
        answer: Any,
        documents: Any,
        confirmed: Any,
        read_at: datetime,
        confirmed_at: datetime | None,
    ) -> dict[str, Any]:
        """The answer with its sources. A ValueError, with the reason, where the answer cannot
        leave its step: no statement, a statement without a source, a source not read."""
        ...
