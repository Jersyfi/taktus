"""The three pools the run engine resolves adapters from, as one configuration.

The removal test, the conformance suites and the maturity threshold all ask the same question
of them: what stands behind an adapter identifier now — which adapter, what it declared, which
version. `Pools.configuration` answers it once, so that a verdict, a conformance pass and the
standing a run reads name a configuration the same way (ADR-0030 §5, ADR-0044).
"""

from __future__ import annotations

from typing import Any

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.models.pool import StaticModelPool
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.catalog.domain.model import Configuration
from taktus.components.run.domain.model import ConnectorRule, LlmWork, WaitWork, WorkerWork
from taktus.shared.v1 import Step


class Pools:
    """The three pools the run engine resolves adapters from, as one configuration."""

    def __init__(
        self, workers: StaticWorkerPool, connectors: StaticConnectorPool, models: StaticModelPool
    ) -> None:
        self.workers = workers
        self.connectors = connectors
        self.models = models

    def without(self, integration: str) -> Pools:
        return Pools(
            self.workers.without(integration),
            self.connectors.without(integration),
            self.models.without(integration),
        )

    async def configuration(self, integration: str) -> Configuration | None:
        """What stands behind the identifier now: the adapter, what it declared and the version
        it declared — for a model, the model name it is configured with. None when no adapter
        of the pools has the identifier. The family is read from the identifier's first
        segment, so that asking about one adapter reads no other's declaration."""
        family = integration.split(".", 1)[0]
        if family == "worker":
            worker = await self.workers.member(integration)
            if worker is None:
                return None
            capabilities, version = worker
            return Configuration(
                adapter=integration, serves=tuple(sorted(capabilities)), version=version
            )
        if family == "connector":
            declaration = await self.connectors.member(integration)
            if declaration is None:
                return None
            return Configuration(
                adapter=integration,
                serves=tuple(declaration.capabilities),
                operations=tuple(operation.name for operation in declaration.operations),
                version=declaration.version,
            )
        if family == "model":
            model = self.models.member(integration)
            if model is None:
                return None
            purposes, _, version = model
            return Configuration(adapter=integration, serves=tuple(purposes), version=version)
        return None

    async def serving(self, step: Step, work: Any) -> tuple[str, str | None] | None:
        """What the step needs and which adapter serves it, or None when the step needs no
        adapter: (`served`, adapter identifier or None when nothing serves it)."""
        if isinstance(work, WorkerWork):
            needed = ", ".join(step.required_capabilities)
            worker = await self.workers.resolve(step.required_capabilities)
            return needed, None if worker is None else worker.adapter
        if isinstance(work, ConnectorRule):
            connector = await self.connectors.resolve(work.capability)
            return work.capability, None if connector is None else connector.adapter
        if isinstance(work, WaitWork) and work.until is not None:
            connector = await self.connectors.resolve(work.until.capability)
            return work.until.capability, None if connector is None else connector.adapter
        if isinstance(work, LlmWork):
            model = await self.models.resolve(work.purpose)
            return f"purpose {work.purpose}", None if model is None else model.adapter
        return None

    async def outward(self, work: Any) -> bool:
        """Whether the step's connector operation is declared outward: its effect would leave
        the system, and a rehearsal answers it from a recording instead."""
        if isinstance(work, ConnectorRule):
            connector = await self.connectors.resolve(work.capability)
            if connector is None:
                return False
            operation = connector.declaration.operation(work.operation)
            return operation is not None and operation.outward
        return False
