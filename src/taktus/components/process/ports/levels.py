"""The levels a version was lowered to by rule, seen from registration (ADR-0110).

A level falls by rule in the governance component, without a person: a breach of an anchor, or
a correction rate above the tenant's limit. It rises again only where a version is registered,
with a person's approval and the quality history (ADR-0039 §3). Registration therefore measures
a new version against the levels the replaced version runs at now, lowered ones included. The
composition root answers from the governance component, because components never import each
other.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from pydantic import Field

from taktus.ports.persistence import Tenant
from taktus.shared.v1 import AutonomyLevel, Value


class LoweredLevels(Value):
    """The process's level and each action's, as far as they were lowered; None and absent
    where nothing was."""

    level: AutonomyLevel | None = None
    actions: Mapping[str, AutonomyLevel] = Field(default_factory=dict)


class LoweredVersions(Protocol):
    async def lowered(self, tenant: Tenant, process_version: str) -> LoweredLevels: ...
