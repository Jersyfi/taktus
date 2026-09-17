"""The leadership port in memory — DEVELOPMENT AND TEST ONLY.

One lead per role per process. A lead is lost when it is released, and — to let a test act
the death of a leader — when the holder is told to `drop()` it without releasing, which is what
a closed connection does in the database."""

from __future__ import annotations

from taktus.ports.leadership import Lead


class MemoryLead:
    def __init__(self, leadership: MemoryLeadership, role: str) -> None:
        self._leadership = leadership
        self._role = role
        self._alive = True

    async def held(self) -> bool:
        return self._alive and self._leadership._holders.get(self._role) is self

    async def release(self) -> None:
        self.drop()

    def drop(self) -> None:
        """The holder is gone without saying so: the lead is free for the next instance."""
        self._alive = False
        if self._leadership._holders.get(self._role) is self:
            del self._leadership._holders[self._role]


class MemoryLeadership:
    def __init__(self) -> None:
        self._holders: dict[str, MemoryLead] = {}

    async def try_lead(self, role: str) -> Lead | None:
        if role in self._holders:
            return None
        lead = MemoryLead(self, role)
        self._holders[role] = lead
        return lead
