"""Writing on a connection, granted and withdrawn by a person (ADR-0262 §2, UC-5.6).

The run asks `granted` through its port `WriteGrants` before an outward call of a capability
whose connection reads until granted. Only a person grants or withdraws: an identity the tenant
knows, holding the role `owner`, acting with its own key — never a run and never a worker's
assignment. Each act is a ledger entry in the transaction that stores it, naming the person:
`connection.granted`, `connection.withdrawn`; a refused attempt is `connection.refused` with
the reason as outcome, and changes nothing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from taktus.components.governance.domain.model.connections import (
    GRANTING_ROLE,
    ConnectionGrant,
)
from taktus.ports.clock import Clock
from taktus.ports.connector import READ_UNLESS_GRANTED
from taktus.ports.identity import IdentityResolver
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

GRANTED = "connection.granted"
WITHDRAWN = "connection.withdrawn"
REFUSED = "connection.refused"


@dataclass(frozen=True)
class Granter:
    """Who asks, and through what. An act that arrives from a run or a worker's assignment is a
    process's or a worker's, whoever it acts for."""

    identity: str
    run_id: str | None = None
    assignment_id: str | None = None


class GrantRefused(Exception):
    """An act on a grant that is not a person's with the right. Recorded; nothing changed."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason


class NotGrantable(ValueError):
    """A capability whose connection writes without a grant: there is nothing to grant."""


def _digest(grant: ConnectionGrant) -> str:
    text = json.dumps(grant.document(), sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


class ConnectionGrants:
    def __init__(
        self,
        grants: Repository[ConnectionGrant],
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
        identities: IdentityResolver,
    ) -> None:
        self._grants = grants
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._identities = identities

    async def granted(self, tenant: Tenant, capability: str) -> bool:
        """The run's port: whether the tenant's grant of writing on the connection is in
        force."""
        found = await self.grant(tenant, capability)
        return found is not None and found.in_force

    async def grant(self, tenant: Tenant, capability: str) -> ConnectionGrant | None:
        async with self._work.transaction(tenant):
            return await self._grants.get(tenant, capability)

    async def every(self, tenant: Tenant) -> list[ConnectionGrant]:
        async with self._work.transaction(tenant):
            return sorted(await self._grants.list(tenant), key=lambda g: g.capability)

    async def give(self, tenant: Tenant, capability: str, *, by: Granter) -> ConnectionGrant:
        """Writing granted on the connection by a person with the right. `GrantRefused` for
        anyone else, recorded; `NotGrantable` for a capability that needs no grant."""
        return await self._change(tenant, capability, by, withdrawn=False)

    async def withdraw(self, tenant: Tenant, capability: str, *, by: Granter) -> ConnectionGrant:
        """The grant withdrawn by a person with the right: the connection reads again."""
        return await self._change(tenant, capability, by, withdrawn=True)

    async def _change(
        self, tenant: Tenant, capability: str, by: Granter, *, withdrawn: bool
    ) -> ConnectionGrant:
        if capability not in READ_UNLESS_GRANTED:
            raise NotGrantable(
                f"{capability!r} is no connection that reads until granted; those are "
                + ", ".join(sorted(READ_UNLESS_GRANTED))
            )
        await self._holds(tenant, by)
        grant = ConnectionGrant(
            id=capability,
            tenant=tenant,
            capability=capability,
            created_at=self._clock.now(),
            withdrawn=withdrawn,
        )
        async with self._work.transaction(tenant):
            await self._grants.put(tenant, grant)
            await self._ledger.record(
                tenant,
                Fact(
                    kind=WITHDRAWN if withdrawn else GRANTED,
                    refs=LedgerRefs(tenant=tenant, actor=by.identity),
                    outcome="withdrawn" if withdrawn else "granted",
                    content_digest=_digest(grant),
                ),
            )
        return grant

    async def _holds(self, tenant: Tenant, by: Granter) -> None:
        if by.run_id is not None:
            await self._refuse(tenant, "process", by, "a process does not grant writing")
        if by.assignment_id is not None:
            await self._refuse(tenant, "worker", by, "a worker does not grant writing")
        placed = await self._identities.identity(tenant, by.identity)
        if placed is None:
            await self._refuse(tenant, "unknown", by, f"{by.identity!r} is not known to {tenant}")
        elif GRANTING_ROLE not in placed.roles:
            await self._refuse(
                tenant,
                "role",
                by,
                f"{by.identity!r} does not hold the role {GRANTING_ROLE!r}, which holds the "
                "right to grant writing on a connection",
            )

    async def _refuse(self, tenant: Tenant, reason: str, by: Granter, detail: str) -> None:
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=REFUSED,
                    refs=LedgerRefs(
                        tenant=tenant,
                        actor=by.identity,
                        run_id=by.run_id,
                        assignment_id=by.assignment_id,
                    ),
                    outcome=reason,
                ),
            )
        raise GrantRefused(reason, detail)
