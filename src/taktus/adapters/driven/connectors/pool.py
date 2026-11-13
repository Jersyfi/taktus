"""A fixed set of configured connectors, resolved by capability.

Configuration maps a capability to a connector; the ledger records the configuration's
identifier and never a product. This pool is the simplest such configuration: a list of
(identifier, connector), the first whose declaration lists the capability wins. Declarations
are read once and kept, so that a run does not pay a resource read per step. Each member's
location is the one its configuration declares, `elsewhere` where it declares none (ADR-0281).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from taktus.ports.connector import ActionConnector, Capabilities, ResolvedConnector
from taktus.ports.model import Location
from taktus.shared.v1 import Capability


class StaticConnectorPool:
    def __init__(
        self,
        connectors: Sequence[tuple[str, ActionConnector]],
        *,
        locations: Mapping[str, Location] | None = None,
    ) -> None:
        self._connectors = list(connectors)
        self._declared: dict[str, Capabilities] = {}
        self._locations = dict(locations or {})
        """Where each member's system processes, by adapter identifier, as configured."""

    def location(self, adapter: str) -> Location:
        """The location one member's configuration declares; `elsewhere` where none does."""
        return self._locations.get(adapter, "elsewhere")

    async def resolve(self, capability: Capability) -> ResolvedConnector | None:
        for adapter, connector in self._connectors:
            if adapter not in self._declared:
                self._declared[adapter] = await connector.capabilities()
            declaration = self._declared[adapter]
            if capability in declaration.capabilities:
                return ResolvedConnector(
                    adapter=adapter,
                    connector=connector,
                    declaration=declaration,
                    location=self.location(adapter),
                )
        return None

    async def named(self, adapter: str, capability: Capability) -> ResolvedConnector | None:
        """The member configured under `adapter`, where its declaration lists the capability
        (ADR-0311): what a step that names its connector is served by. None otherwise."""
        for configured, connector in self._connectors:
            if configured != adapter:
                continue
            if adapter not in self._declared:
                self._declared[adapter] = await connector.capabilities()
            declaration = self._declared[adapter]
            if capability not in declaration.capabilities:
                return None
            return ResolvedConnector(
                adapter=adapter,
                connector=connector,
                declaration=declaration,
                location=self.location(adapter),
            )
        return None

    def identifiers(self) -> list[str]:
        """The identifier of every configured member, in order, without reading a declaration."""
        return [adapter for adapter, _ in self._connectors]

    async def members(self) -> list[tuple[str, Capabilities]]:
        """Every configured connector with its declaration — what the removal test reads to
        know what is configured."""
        found = []
        for adapter, connector in self._connectors:
            if adapter not in self._declared:
                self._declared[adapter] = await connector.capabilities()
            found.append((adapter, self._declared[adapter]))
        return found

    async def member(self, adapter: str) -> Capabilities | None:
        """The declaration of one configured connector, read as `resolve` reads it; None when
        no connector has the identifier."""
        for configured, connector in self._connectors:
            if configured != adapter:
                continue
            if adapter not in self._declared:
                self._declared[adapter] = await connector.capabilities()
            return self._declared[adapter]
        return None

    def without(self, adapter: str) -> StaticConnectorPool:
        """The same configuration with one connector withheld; the original is untouched."""
        pool = StaticConnectorPool(
            [(a, c) for a, c in self._connectors if a != adapter], locations=self._locations
        )
        pool._declared = {a: d for a, d in self._declared.items() if a != adapter}
        return pool

    def first(self, adapter: str) -> StaticConnectorPool:
        """The same configuration with one connector moved to the front, for the removal test's
        baseline (ADR-0078); the original is untouched."""
        pool = StaticConnectorPool(
            sorted(self._connectors, key=lambda entry: entry[0] != adapter),
            locations=self._locations,
        )
        pool._declared = dict(self._declared)
        return pool
