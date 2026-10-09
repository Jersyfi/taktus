"""How mature an adapter is: the catalog's record, seen from the run.

From autonomy level 3 a step runs only on an adapter whose maturity is *verified* or above: the
conformance suite and the removal test both passed (`docs/architecture/contracts.md` §3,
NTC-0051). The run asks before the step starts; the catalog component keeps the record, and the
composition root answers from it.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import Field

from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Value


class Standing(Value):
    """One adapter's standing, as far as a step at level 3 needs it."""

    adapter: str = Field(min_length=1)
    integration: bool = True
    """False for an adapter that is no integration of the instance: Taktus reached by Taktus
    through the loopback connector, which acts on nothing outside and which the removal test
    never lists (`docs/architecture/contracts.md` §4, NTC-0079)."""
    maturity: str | None = Field(default=None, min_length=1)
    """`experimental`, `verified` or `reference`, as the record derives it; None for an adapter
    that is no integration."""
    missing: tuple[str, ...] = ()
    """What keeps the adapter from *verified*, in words."""

    @property
    def serves_from_level_three(self) -> bool:
        return not self.integration or self.maturity in ("verified", "reference")


class Maturities(Protocol):
    async def standing(self, tenant: Tenant, adapter: str) -> Standing:
        """The adapter's standing. An adapter nothing has recorded is *experimental*, and says
        that both halves are missing."""
        ...
