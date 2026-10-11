"""The anchors that name a step's act, and the decision requests an anchored step raises, seen
from the run (ADR-0042).

An anchor keeps an act with a person whatever the autonomy level (ADR-0008, ADR-0022). The
governance component keeps a tenant's anchors and decides which apply to a step; the decision
component keeps the requests and the register. The run asks both through these ports before a
step starts, and the composition root answers from the two components, because components never
import each other.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from pydantic import Field

from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Anchor, Value


class Anchors(Protocol):
    async def applying(
        self, tenant: Tenant, process: str, actions: Sequence[str]
    ) -> tuple[Anchor, ...]:
        """The tenant's anchors that name the act of a step of `process` using `actions` —
        its capabilities, the connector operation it calls or waits on, that operation's
        capability."""
        ...


@dataclass(frozen=True)
class DraftOption:
    id: str
    proposal: str
    consequence: str
    recommended: bool
    reason: str | None = None


@dataclass(frozen=True)
class Draft:
    """A decision request as the run proposes it, before the decision component checks its
    shape. Deliberately unchecked here: a draft missing a part is refused there, not raised."""

    id: str
    run: str
    step: str
    class_: str
    situation: str
    question: str
    options: tuple[DraftOption, ...]
    blocking: tuple[str, ...]
    due: date
    decider: str
    anchor: str | None = None
    """The anchor that raised it; None for a request no anchor raised, such as a proposal to
    move a step to another method (ADR-0084)."""


class NotRaised(Exception):
    """The request could not be raised; the message says why."""


class Verdict(Value):
    """Where a request stands, as far as the run needs it."""

    applied: bool
    option: str | None = Field(default=None, pattern=r"^[A-Z]$")
    """The option that took effect, once applied."""
    decided_by: str | None = Field(default=None, min_length=1)
    entry: str | None = Field(default=None, min_length=1)
    """The decision register's entry, once applied."""


class Decisions(Protocol):
    async def raise_request(self, tenant: Tenant, draft: Draft) -> None:
        """Raise the request, or meet the one raised under the same id. `NotRaised` when it
        is missing a part."""
        ...

    async def verdict(self, tenant: Tenant, request_id: str) -> Verdict | None:
        """None when no such request exists."""
        ...
