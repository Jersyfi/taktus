"""The outbox port, in memory and in PostgreSQL (ADR-0002, ADR-0048): an entry lands with its
transaction or not at all, is read in the order it was written, per tenant and topic, and is not
read again once published."""

from __future__ import annotations

import pytest
from fakes import FakeClock

from adapters.persistence.conftest import Backend
from taktus.adapters.driven.memory import MemoryOutbox, MemoryPersistence
from taktus.adapters.driven.postgres import PostgresOutbox, PostgresPersistence
from taktus.ports.outbox import INTAKE_ACCEPTED, Outbox


def outbox_of(backend: Backend) -> Outbox:
    if isinstance(backend.work, MemoryPersistence):
        return MemoryOutbox(backend.work, FakeClock())
    assert isinstance(backend.work, PostgresPersistence)
    return PostgresOutbox(backend.work)


async def test_entries_are_read_in_order_and_once_published_never_again(backend: Backend) -> None:
    tenant = await backend.tenant()
    outbox = outbox_of(backend)
    async with backend.work.transaction(tenant):
        await outbox.write(tenant, INTAKE_ACCEPTED, {"event_id": "a"})
        await outbox.write(tenant, "other.topic", {"x": 1})
        await outbox.write(tenant, INTAKE_ACCEPTED, {"event_id": "b"})
    async with backend.work.transaction(tenant):
        first, second = await outbox.unpublished(tenant, INTAKE_ACCEPTED, 10)
    assert [first.payload, second.payload] == [{"event_id": "a"}, {"event_id": "b"}]
    assert first.id < second.id
    async with backend.work.transaction(tenant):
        await outbox.publish(tenant, first.id)
        await outbox.publish(tenant, first.id)  # again: a no-op
    async with backend.work.transaction(tenant):
        (left,) = await outbox.unpublished(tenant, INTAKE_ACCEPTED, 10)
        assert await outbox.unpublished(tenant, INTAKE_ACCEPTED, 0) == []
    assert left.payload == {"event_id": "b"}


async def test_an_entry_lands_with_its_transaction_or_not_at_all(backend: Backend) -> None:
    tenant = await backend.tenant()
    outbox = outbox_of(backend)
    with pytest.raises(RuntimeError):
        async with backend.work.transaction(tenant):
            await outbox.write(tenant, INTAKE_ACCEPTED, {"event_id": "a"})
            raise RuntimeError("the cause failed")
    async with backend.work.transaction(tenant):
        assert await outbox.unpublished(tenant, INTAKE_ACCEPTED, 10) == []


async def test_a_tenant_reads_only_its_own_entries(backend: Backend) -> None:
    a, b = await backend.tenant(), await backend.tenant()
    outbox = outbox_of(backend)
    async with backend.work.transaction(a):
        await outbox.write(a, INTAKE_ACCEPTED, {"event_id": "a"})
    async with backend.work.transaction(b):
        assert await outbox.unpublished(b, INTAKE_ACCEPTED, 10) == []
