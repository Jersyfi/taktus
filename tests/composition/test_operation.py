"""What keeps the operation running, read for the HTTP surface (ADR-0121): each read asks the
component that owns the record, and the incidents include the closed ones."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from fakes import FakeClock
from fakes.identity import directory

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.governance.application.service import CloseIncident, ExpectedRuns
from taktus.components.governance.domain.model import (
    Incident,
    IncidentKind,
    WatchConfiguration,
)
from taktus.composition.operation import OperationRecords

TENANT = "default"
AT = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)


def incident(name: str) -> Incident:
    return Incident(
        id=name,
        tenant=TENANT,
        kind=IncidentKind.MISSING,
        process_id="watch",
        process_version="watch@1",
        expected_at=AT,
        rule="expected.slot",
        raised_at=AT,
    )


class Asked:
    """Stands in for the alerts and the signals: says which read was asked."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    async def noticed(self, tenant: str) -> tuple[()]:
        self.asked.append(f"noticed {tenant}")
        return ()

    async def backup(self, tenant: str) -> None:
        self.asked.append(f"backup {tenant}")

    async def judged(self, tenant: str) -> list[Any]:
        self.asked.append(f"judged {tenant}")
        return []


async def test_every_incident_is_read_open_and_closed_and_each_read_asks_its_owner() -> None:
    persistence = MemoryPersistence()
    clock = FakeClock()
    identity = directory((TENANT,), persistence=persistence, clock=clock)
    incidents: MemoryRepository[Incident] = MemoryRepository(persistence, Incident)
    watch = ExpectedRuns(
        incidents,
        MemoryRepository(persistence, WatchConfiguration),
        MemoryLedgerStore(persistence),
        identity.ledger,
        persistence,
        clock,
    )
    async with persistence.transaction(TENANT):
        await incidents.put(TENANT, incident("inc_open"))
        await incidents.put(TENANT, incident("inc_closed"))
    await watch.close(CloseIncident(tenant=TENANT, incident_id="inc_closed", by="operator"))
    asked = Asked()
    records = OperationRecords(watch, cast(Any, asked), cast(Any, asked))
    assert {i.id for i in await records.incidents(TENANT)} == {"inc_open", "inc_closed"}
    await records.alerts(TENANT)
    await records.backup(TENANT)
    await records.signals(TENANT)
    assert asked.asked == [f"noticed {TENANT}", f"backup {TENANT}", f"judged {TENANT}"]
