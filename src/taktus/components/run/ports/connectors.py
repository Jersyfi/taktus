"""Which connector serves which capability: configuration, seen from the run."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from taktus.ports.connector import ResolvedConnector
from taktus.shared.v1 import Capability


class ConnectorPool(Protocol):
    async def resolve(self, capability: Capability) -> ResolvedConnector | None:
        """A connector whose declaration lists the capability, with the identifier of its
        adapter configuration and the declaration itself. None when none is configured."""
        ...


@runtime_checkable
class NamedConnectors(Protocol):
    """A pool that also answers for one configured member by its identifier (ADR-0311)."""

    async def named(self, adapter: str, capability: Capability) -> ResolvedConnector | None:
        """The member configured under `adapter`, where its declaration lists the capability.
        None when no member has the identifier, or it does not serve the capability."""
        ...
