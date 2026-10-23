"""A tenant's declaration of its sources: what is free of personal fields, what serves
personal data, recorded when it changes (ADR-0130, UC-7.7; NTC-0224)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fakes import FakeClock
from pydantic import ValidationError

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.governance.application.service import DeclareSources, TenantSources
from taktus.components.governance.domain.model import SourceDeclaration, shipped_declaration
from taktus.components.ledger.application.service import ChainedLedger

AT = datetime(2026, 10, 23, 9, 0, tzinfo=UTC)
TENANT = "t"


def sources() -> tuple[TenantSources, ChainedLedger, MemoryPersistence]:
    clock = FakeClock(AT)
    persistence = MemoryPersistence()
    ledger = ChainedLedger(MemoryLedgerStore(persistence), clock)
    declarations = MemoryRepository(persistence, SourceDeclaration)
    return TenantSources(declarations, ledger, persistence, clock), ledger, persistence


async def test_a_tenant_that_declared_nothing_has_no_free_and_no_personal_source() -> None:
    service, _, _ = sources()
    assert await service.declaration(TENANT) == shipped_declaration(TENANT)
    assert not await service.free_of_personal_fields(TENANT, "analytics.cohorts")
    assert not await service.personal(TENANT, "customers.accounts")


async def test_a_declaration_is_changed_and_recorded_in_the_ledger() -> None:
    service, ledger, persistence = sources()
    declared = await service.declare(
        DeclareSources(
            tenant=TENANT, free=("analytics.cohorts",), personal=("customers.accounts",)
        ),
        by="op",
    )
    assert (declared.free, declared.personal) == (("analytics.cohorts",), ("customers.accounts",))
    assert await service.free_of_personal_fields(TENANT, "analytics.cohorts")
    assert await service.personal(TENANT, "customers.accounts")
    async with persistence.transaction(TENANT):
        (entry,) = [e for e in await ledger.entries(TENANT) if e.kind == "sources.configured"]
    assert entry.refs.actor == "op"
    moved = await service.declare(
        DeclareSources(tenant=TENANT, personal=("analytics.cohorts",)), by="op"
    )
    assert moved.free == () and set(moved.personal) == {"analytics.cohorts", "customers.accounts"}
    withdrawn = await service.declare(
        DeclareSources(tenant=TENANT, withdrawn=("analytics.cohorts", "customers.accounts")),
        by="op",
    )
    assert (withdrawn.free, withdrawn.personal) == ((), ())


async def test_a_capability_is_never_free_and_personal_at_once() -> None:
    with pytest.raises(ValidationError, match="at once"):
        SourceDeclaration(id=TENANT, tenant=TENANT, free=("a.b",), personal=("a.b",))
    service, _, _ = sources()
    with pytest.raises(ValueError, match="at once"):
        await service.declare(
            DeclareSources(tenant=TENANT, free=("a.b",), personal=("a.b",)), by="op"
        )
    with pytest.raises(ValueError):
        await service.declare(DeclareSources(tenant=TENANT, free=("Mail",)), by="op")
