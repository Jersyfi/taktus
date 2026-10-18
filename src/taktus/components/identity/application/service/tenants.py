"""The instance's tenants: created by an administrator, named, and served (ADR-0104).

`TenantRegistry` is the identity component's half of the registry. An administrator creates a
tenant with a display name; the identifier is generated here, from the identifier port, and
never taken from the caller (DEC-0187 answer 1). The display name may change, the identifier
never does.

Creating a tenant inserts its row and appends `tenant.created` to the new tenant's own chain, in
one transaction: it is that chain's first entry. A rename appends `tenant.renamed` to the
tenant's chain. An entry carries the tenant, the acting administrator where one is named, and
the digest of the identifier and the name, never the name (ADR-0006). No other tenant's chain is
written: an entry there would tell one tenant that another exists.

`served` answers which tenants the instance serves now. It reads the registry each time it is
asked; every role asks it on every round. `TAKTUS_TENANTS`, while it is still accepted, narrows
the answer to the tenants it names (`narrowed_to`).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any

from taktus.ports.clock import Clock, Identifiers
from taktus.ports.identity import ServedTenants
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Tenant, TenantEntry, TenantStore, UnitOfWork
from taktus.shared.v1 import LedgerRefs

TENANT_CREATED = "tenant.created"
TENANT_RENAMED = "tenant.renamed"
PREFIX = "tnt"
"""What a generated identifier starts with: `tnt_` and 20 hexadecimal characters."""
NAME_LENGTH = 200


class TenantError(Exception):
    """A tenant act that cannot be done as asked; the message says why."""


class NoSuchTenant(TenantError):
    def __init__(self, tenant: Tenant) -> None:
        super().__init__(f"the instance has no tenant {tenant!r}")


class BadName(TenantError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"a tenant's display name {reason}")


def _name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise BadName("is required")
    if len(cleaned) > NAME_LENGTH:
        raise BadName(f"is at most {NAME_LENGTH} characters long")
    if any(not c.isprintable() for c in cleaned):
        raise BadName("holds printable characters only")
    return cleaned


def _digest_of(document: dict[str, Any]) -> str:
    canonical = json.dumps(document, ensure_ascii=False, sort_keys=True)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class TenantRegistry(ServedTenants):
    def __init__(
        self,
        *,
        store: TenantStore,
        work: UnitOfWork,
        ledger: Ledger,
        clock: Clock,
        ids: Identifiers,
        narrowed_to: Sequence[Tenant] | None = None,
    ) -> None:
        self._store = store
        self._work = work
        self._ledger = ledger
        self._clock = clock
        self._ids = ids
        self._narrowed_to = None if narrowed_to is None else frozenset(narrowed_to)

    async def create(self, name: str, *, by: str | None = None) -> TenantEntry:
        """A new tenant with a generated identifier, and its first ledger entry."""
        entry = TenantEntry(
            id=self._ids.new(PREFIX), name=_name(name), created_at=self._clock.now()
        )
        async with self._work.transaction(entry.id):
            await self._store.add(entry)
            await self._record(entry, TENANT_CREATED, "created", by)
        return entry

    async def rename(self, tenant: Tenant, name: str, *, by: str | None = None) -> TenantEntry:
        """The tenant's display name from now on; its identifier stays."""
        cleaned = _name(name)
        async with self._work.transaction(tenant):
            existing = await self._store.get(tenant)
            if existing is None:
                raise NoSuchTenant(tenant)
            renamed = existing.model_copy(update={"name": cleaned})
            if renamed != existing:
                await self._store.rename(tenant, cleaned)
                await self._record(renamed, TENANT_RENAMED, "renamed", by)
        return renamed

    async def every(self) -> tuple[TenantEntry, ...]:
        """The tenants this instance serves, with their names, oldest first."""
        return tuple(
            entry
            for entry in await self._store.every()
            if self._narrowed_to is None or entry.id in self._narrowed_to
        )

    async def served(self) -> tuple[Tenant, ...]:
        return tuple(entry.id for entry in await self.every())

    async def _record(self, entry: TenantEntry, kind: str, outcome: str, by: str | None) -> None:
        await self._ledger.record(
            entry.id,
            Fact(
                kind=kind,
                refs=LedgerRefs(tenant=entry.id, actor=by),
                outcome=outcome,
                content_digest=_digest_of({"tenant": entry.id, "name": entry.name}),
            ),
        )
