"""What a domain's view reads from outside this component: whether each of its processes passed
its takeover test and its removal test (UC-15.5 §2, ADR-0259 §4).

The trials of takeover instructions are the process component's, the removal verdicts the
catalog component's; the composition root answers this port from both."""

from __future__ import annotations

from typing import Protocol

from taktus.ports.persistence import Tenant


class DomainTests(Protocol):
    async def takeover_passed(self, tenant: Tenant, process: str) -> bool:
        """Whether a person passed the trial of the takeover instructions of the process's
        active version (UC-6.3, ADR-0180 §3)."""
        ...

    async def removal_passed(self, tenant: Tenant, process: str) -> bool:
        """Whether every adapter serving a step of the process's active version has a removal
        verdict, and none of them found the process broken (ADR-0030)."""
        ...
