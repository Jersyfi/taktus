"""A fixed set of configured connectors, resolved by capability.

Configuration maps a capability to a connector; the ledger records the configuration's
identifier and never a product. This pool is the simplest such configuration: a list of
(identifier, connector), the first whose declaration lists the capability wins. Declarations
are read once and kept, so that a run does not pay a resource read per step.
"""

from __future__ import annotations

from collections.abc import Sequence

from taktus.ports.connector import ActionConnector, Capabilities, ResolvedConnector
from taktus.shared.v1 import Capability


class StaticConnectorPool:
    def __init__(self, connectors: Sequence[tuple[str, ActionConnector]]) -> None:
        self._connectors = list(connectors)
        self._declared: dict[str, Capabilities] = {}

    async def resolve(self, capability: Capability) -> ResolvedConnector | None:
        for adapter, connector in self._connectors:
            if adapter not in self._declared:
                self._declared[adapter] = await connector.capabilities()
            declaration = self._declared[adapter]
            if capability in declaration.capabilities:
                return ResolvedConnector(
                    adapter=adapter, connector=connector, declaration=declaration
                )
        return None

    async def members(self) -> list[tuple[str, Capabilities]]:
        """Every configured connector with its declaration — what the removal test reads to
        know what is configured."""
        found = []
        for adapter, connector in self._connectors:
            if adapter not in self._declared:
                self._declared[adapter] = await connector.capabilities()
            found.append((adapter, self._declared[adapter]))
        return found

    def without(self, adapter: str) -> StaticConnectorPool:
        """The same configuration with one connector withheld; the original is untouched."""
        pool = StaticConnectorPool([(a, c) for a, c in self._connectors if a != adapter])
        pool._declared = {a: d for a, d in self._declared.items() if a != adapter}
        return pool
