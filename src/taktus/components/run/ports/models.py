"""Which model serves which purpose: configuration, seen from the run."""

from __future__ import annotations

from typing import Protocol

from taktus.ports.model import ResolvedModel


class ModelPool(Protocol):
    async def resolve(self, purpose: str) -> ResolvedModel | None:
        """A model configured for the purpose, with the identifier of its adapter
        configuration. None when none is configured."""
        ...

    async def chain(self, purpose: str) -> list[ResolvedModel]:
        """Every model configured for the purpose, in the order a step is routed through
        them (ADR-0116); empty when none is."""
        ...

    async def bound(self, adapter: str) -> ResolvedModel | None:
        """The configured model under the identifier, whatever purposes it serves: what a run
        that binds a purpose to it routes that purpose to (ADR-0149 §1). None when no model of
        the configuration has it."""
        ...
