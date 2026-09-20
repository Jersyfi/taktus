"""Which connector serves which capability: configuration, seen from the run."""

from __future__ import annotations

from typing import Protocol

from taktus.ports.connector import ResolvedConnector
from taktus.shared.v1 import Capability


class ConnectorPool(Protocol):
    async def resolve(self, capability: Capability) -> ResolvedConnector | None:
        """A connector whose declaration lists the capability, with the identifier of its
        adapter configuration and the declaration itself. None when none is configured."""
        ...
