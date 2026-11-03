"""What a run hands its steps as know-how: the skills they name and the role profile of the
shared agent it serves (ADR-0162 §5, ADR-0163 §5). The catalogue keeps both; the composition
root answers this port from it."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Protocol

from taktus.ports.persistence import Tenant


class Guidance(Protocol):
    async def production(self, tenant: Tenant, names: Collection[str]) -> Mapping[str, str]:
        """The version in production of each named skill that has one, `{name: version}`."""
        ...

    async def skill(self, tenant: Tenant, name: str, version: str) -> str | None:
        """The instructions of one skill version; None where the catalogue holds none."""
        ...

    async def profile(self, tenant: Tenant, profile: str) -> str | None:
        """The brief of a shared agent's role profile, its core's instructions first; None
        where the catalogue holds no such profile."""
        ...
