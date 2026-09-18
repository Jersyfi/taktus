"""Which model serves which purpose: configuration, seen from the run."""

from __future__ import annotations

from typing import Protocol

from taktus.ports.model import ResolvedModel


class ModelPool(Protocol):
    async def resolve(self, purpose: str) -> ResolvedModel | None:
        """A model configured for the purpose, with the identifier of its adapter
        configuration. None when none is configured."""
        ...
