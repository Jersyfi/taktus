"""What a tenant rules about outward messages, and whether a person answered in a case, seen
from the run (ADR-0142).

The governance component keeps both; the composition root answers this port from it, because
components never import each other.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import time
from typing import Protocol

from taktus.ports.persistence import Tenant


@dataclass(frozen=True)
class QuietHours:
    """A span of the day in which no message is sent, read in `zone`. It runs across midnight
    where `begins` is later than `ends`."""

    begins: time
    ends: time
    zone: str


@dataclass(frozen=True)
class MessageRules:
    """One tenant's rules for a message step: the label added to what a model wrote — None
    where the tenant configured none, and then no such message is sent — the delay after
    approval, the quiet hours, and the most recipients an outward step may address without a
    person."""

    label: str | None
    delay_seconds: int
    quiet: QuietHours | None
    recipient_limit: int
    daily_limit: int | None = None
    """The most messages a process sends within 24 hours without a person (ADR-0335 §5)."""
    process_limits: Mapping[str, int] = field(default_factory=dict)
    """A process's own daily limit, in place of the tenant's."""

    def daily_for(self, process: str) -> int | None:
        return self.process_limits.get(process, self.daily_limit)


class Messages(Protocol):
    async def rules(self, tenant: Tenant) -> MessageRules:
        """The tenant's rules, or the shipped default where it configured none (NTC-0234)."""
        ...

    async def answered(self, tenant: Tenant, process: str, case: str) -> bool:
        """Whether a person answered in the case of the process: the process sends nothing more
        in it."""
        ...
