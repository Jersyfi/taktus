"""A run's purposes bound to one model each, for that run alone (ADR-0149 §1).

A model trial runs the same case once per candidate model. The run of a case binds the trial's
purpose to the candidate: the purpose's chain is that one model, routed as any chain is
(ADR-0116 §4) — a candidate that may not process where the step's data may go, or produce its
exactness class, fails the step with `no model` rather than moving to another member. Every
purpose the run does not bind routes through the configured chain, unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping

from taktus.components.run.ports.models import ModelPool
from taktus.ports.model import ResolvedModel


class BoundModels:
    """The configured pool, with some purposes bound to one model each."""

    def __init__(self, pool: ModelPool, bindings: Mapping[str, str]) -> None:
        self._pool = pool
        self._bindings = dict(bindings)

    async def resolve(self, purpose: str) -> ResolvedModel | None:
        chain = await self.chain(purpose)
        return chain[0] if chain else None

    async def chain(self, purpose: str) -> list[ResolvedModel]:
        adapter = self._bindings.get(purpose)
        if adapter is None:
            return await self._pool.chain(purpose)
        bound = await self._pool.bound(adapter)
        return [] if bound is None else [bound]

    async def bound(self, adapter: str) -> ResolvedModel | None:
        return await self._pool.bound(adapter)
