"""Leadership: one instance among several holds a role that must be singular.

The scheduler is such a role (ADR-0002): time triggers fire once, not once per instance. An
instance tries to lead; exactly one succeeds and holds the lead until it releases it or dies;
the others keep trying and one of them takes over. A lead is bound to a live connection to the
shared state — in the database, a session-level advisory lock — so that a dead leader loses it
without anyone declaring it dead. `Lead.held()` asks whether the lead is still this instance's;
a leader that has lost it stops acting as one at once.
"""

from __future__ import annotations

from typing import Protocol


class Lead(Protocol):
    async def held(self) -> bool:
        """Whether this instance still holds the lead. False once the connection that carried
        it is gone; a leader must not act on a lead it has lost."""
        ...

    async def release(self) -> None:
        """Give the lead up, so that another instance can take it at once."""
        ...


class Leadership(Protocol):
    async def try_lead(self, role: str) -> Lead | None:
        """Take the lead for `role` if nobody holds it; None when someone does. Never waits."""
        ...
