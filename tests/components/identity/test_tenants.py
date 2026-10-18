"""The instance's registry of tenants (ADR-0104): an identifier Taktus generates, a display name
that may change, a ledger entry in the tenant's own chain, and a set every role reads anew."""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes import FakeClock, FakeIdentifiers

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryTenantStore
from taktus.components.identity.application.service import (
    TENANT_CREATED,
    TENANT_RENAMED,
    BadName,
    NoSuchTenant,
    TenantRegistry,
)
from taktus.components.ledger.application.service import ChainedLedger


def registry(
    persistence: MemoryPersistence | None = None, narrowed_to: tuple[str, ...] | None = None
) -> tuple[TenantRegistry, MemoryPersistence, ChainedLedger]:
    persistence = persistence or MemoryPersistence()
    clock = FakeClock()
    ledger = ChainedLedger(MemoryLedgerStore(persistence), clock)
    made = TenantRegistry(
        store=MemoryTenantStore(persistence),
        work=persistence,
        ledger=ledger,
        clock=clock,
        ids=FakeIdentifiers(),
        narrowed_to=narrowed_to,
    )
    return made, persistence, ledger


async def test_a_new_registry_holds_default_alone() -> None:
    tenants, _, _ = registry()
    assert await tenants.served() == ("default",)


async def test_a_tenant_is_created_with_a_generated_identifier_and_its_first_entry() -> None:
    tenants, persistence, ledger = registry()
    created = await tenants.create("  Acme Software  ", by="idn_admin")
    assert created.id == "tnt_0001" and created.name == "Acme Software"
    assert await tenants.served() == ("default", created.id), "served from now on"
    async with persistence.transaction(created.id):
        entries = await ledger.entries(created.id)
    assert [e.kind for e in entries] == [TENANT_CREATED]
    assert entries[0].refs.tenant == created.id and entries[0].refs.actor == "idn_admin"
    assert entries[0].content_digest is not None
    assert "Acme" not in entries[0].model_dump_json(), "a digest, never the name"
    async with persistence.transaction("default"):
        assert await ledger.entries("default") == [], "no other tenant's chain is written"


async def test_a_rename_keeps_the_identifier_and_is_an_entry() -> None:
    tenants, persistence, ledger = registry()
    created = await tenants.create("Acme")
    renamed = await tenants.rename(created.id, "Acme GmbH", by="idn_admin")
    assert (renamed.id, renamed.name) == (created.id, "Acme GmbH")
    assert [(e.id, e.name) for e in await tenants.every()][-1] == (created.id, "Acme GmbH")
    async with persistence.transaction(created.id):
        kinds = [e.kind for e in await ledger.entries(created.id)]
    assert kinds == [TENANT_CREATED, TENANT_RENAMED]
    await tenants.rename(created.id, "Acme GmbH")
    async with persistence.transaction(created.id):
        assert len(await ledger.entries(created.id)) == 2, "the same name changes nothing"


async def test_a_name_is_required_short_and_printable_and_the_tenant_must_exist() -> None:
    tenants, _, _ = registry()
    for name in ("", "   ", "x" * 201, "line\nbreak"):
        with pytest.raises(BadName):
            await tenants.create(name)
    with pytest.raises(NoSuchTenant):
        await tenants.rename("tnt_nobody", "Nobody")
    assert await tenants.served() == ("default",), "nothing was created by a refusal"


async def test_the_deprecated_list_narrows_the_registry_and_adds_nothing() -> None:
    tenants, _, _ = registry(narrowed_to=("tnt_0002", "absent"))
    first = await tenants.create("First")
    second = await tenants.create("Second")
    assert (first.id, second.id) == ("tnt_0001", "tnt_0002")
    assert await tenants.served() == ("tnt_0002",)


async def test_the_registry_survives_a_restart_through_the_snapshot(tmp_path: Path) -> None:
    tenants, _, _ = registry(MemoryPersistence(tmp_path))
    created = await tenants.create("Acme")
    again, _, _ = registry(MemoryPersistence(tmp_path))
    assert await again.served() == ("default", created.id)
