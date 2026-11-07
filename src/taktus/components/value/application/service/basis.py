"""The organisation's stated basis, one version at a time (ADR-0244 §2).

A version is stored once and never changed; `value.basis_set` records it with the person who
set it in `refs.actor` and the version's digest. Who set a version and when is read back from
that entry, so that a figure resting on it can say so (UC-6.6 §2).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from pydantic import Field

from taktus.components.value.domain.model import ValueBasis
from taktus.components.value.domain.model.basis import version_id
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs, Value

SET = "value.basis_set"


def digest(basis: ValueBasis) -> str:
    text = json.dumps(basis.document(), sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


class BasisSet(Value):
    """A version of the basis with the record of its setting: one act, by one person."""

    basis: ValueBasis
    set_by: str = Field(min_length=1)


class ValueBases:
    def __init__(
        self, bases: Repository[ValueBasis], ledger: Ledger, work: UnitOfWork, clock: Clock
    ) -> None:
        self._bases = bases
        self._ledger = ledger
        self._work = work
        self._clock = clock

    async def set(self, tenant: Tenant, stated: Mapping[str, Any], *, by: str) -> ValueBasis:
        """Store the stated basis as the next version. Raises `ValueError` where it does not
        validate; nothing is stored then."""
        async with self._work.transaction(tenant):
            held = await self._bases.list(tenant)
            version = 1 + max((b.version for b in held), default=0)
            basis = ValueBasis.model_validate(
                {
                    **{k: v for k, v in stated.items() if k not in ("id", "tenant", "version")},
                    "id": version_id(version),
                    "tenant": tenant,
                    "version": version,
                    "set_at": self._clock.now(),
                }
            )
            await self._bases.put(tenant, basis)
            await self._ledger.record(
                tenant,
                Fact(
                    kind=SET,
                    refs=LedgerRefs(tenant=tenant, actor=by),
                    outcome="set",
                    content_digest=digest(basis),
                ),
            )
        return basis

    async def current(self, tenant: Tenant) -> BasisSet | None:
        history = await self.history(tenant)
        return history[-1] if history else None

    async def history(self, tenant: Tenant) -> list[BasisSet]:
        async with self._work.transaction(tenant):
            held = sorted(await self._bases.list(tenant), key=lambda b: b.version)
            entries = await self._ledger.of_kinds(tenant, {SET})
        actors = {e.content_digest: e.refs.actor for e in entries}
        return [BasisSet(basis=b, set_by=actors.get(digest(b)) or "unknown") for b in held]
