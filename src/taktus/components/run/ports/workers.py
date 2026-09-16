"""Which execution unit serves which capabilities: configuration, seen from the run."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from taktus.ports.worker import Worker
from taktus.shared.v1 import Capability


class WorkerPool(Protocol):
    async def resolve(self, required: Sequence[Capability]) -> tuple[str, Worker] | None:
        """A worker that offers every required capability, with the identifier of its adapter
        configuration — what the ledger records as `adapter`, never a product name. None when
        no configured worker offers them all."""
        ...
