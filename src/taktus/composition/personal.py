"""The own credentials of the identities a step may act on behalf of, from the instance's
configuration (`TAKTUS_PERSONAL_CREDENTIALS`, ADR-0264): parameters only, never values."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConfiguredPersonalCredentials:
    """The run's port `PersonalCredentials`, answered from a fixed mapping."""

    mapping: Mapping[tuple[str, str], str] = field(default_factory=dict)

    async def own(self, tenant: str, identity: str, parameter: str) -> str | None:
        return self.mapping.get((identity, parameter))
