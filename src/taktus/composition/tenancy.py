"""The tenants a role visits on one round, read from the registry (ADR-0104).

Every role asks the registry at the start of each round. A round must never take its role
down, so a registry that cannot be read is logged and the round visits nobody; the next round
asks again.
"""

from __future__ import annotations

import structlog

from taktus.ports.identity import ServedTenants
from taktus.ports.persistence import Tenant

log = structlog.get_logger("taktusd")


async def this_round(tenants: ServedTenants, role: str) -> tuple[Tenant, ...]:
    """The tenants served now, or none when the registry cannot be read."""
    try:
        return await tenants.served()
    except Exception as error:  # a round never takes its role down
        log.error(
            "the registry of tenants could not be read; this round visits none",
            role=role,
            error=f"{type(error).__name__}: {error}",
        )
        return ()
