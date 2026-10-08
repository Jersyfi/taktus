"""An object store that holds its caller: a runner paused inside a step, before its commit.

A rule step stores its result and then commits the step's end. A runner whose object store
holds the `put` of one particular content stops exactly there: inside the step, outside any
transaction, with nothing of the step's end written. That is the runner of #107 — alive, but
not reaching the database for longer than its lease.
"""

from __future__ import annotations

import asyncio

from taktus.adapters.driven.memory import MemoryObjectStore
from taktus.shared.v1 import Digest


class HeldObjects(MemoryObjectStore):
    def __init__(self, held: bytes) -> None:
        super().__init__()
        self._held = held
        self.reached = asyncio.Event()
        """Set when the held content arrives: the caller is now paused."""
        self.release = asyncio.Event()
        """Set it to let the caller go on."""

    async def put(self, content: bytes) -> Digest:
        if content == self._held:
            self.reached.set()
            await self.release.wait()
        return await super().put(content)
