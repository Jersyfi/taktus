"""Which execution unit serves which capabilities: configuration, seen from the run."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from taktus.ports.model import Permitted
from taktus.ports.worker import ResolvedWorker
from taktus.shared.v1 import Capability


class WorkerPool(Protocol):
    async def resolve(
        self, required: Sequence[Capability], permitted: Permitted = "anywhere"
    ) -> ResolvedWorker | None:
        """A worker that offers every required capability and stores where `permitted` admits,
        with the identifier of its adapter configuration, the version and the location it
        declares. A worker outside `permitted` is passed over for the next one (ADR-0157).
        None when no configured worker fits. UnaskedWorker when a worker it had to ask what it
        offers could not be asked."""
        ...
