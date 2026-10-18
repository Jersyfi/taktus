"""A signal's red value raises an incident (ADR-0109 §4, UC-6.13, UC-6.8).

One incident per cause: a second look at the same value raises nothing, and a further red value
of the same signal is recorded on its open incident. A person closes it, and a red value after
that is a new incident. The incident names no person.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fakes import FakeClock

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.governance.application.service import (
    CloseIncident,
    ExpectedRuns,
    RaiseRed,
    SignalIncidents,
)
from taktus.components.governance.domain.model import Incident, IncidentKind, WatchConfiguration
from taktus.components.ledger.application.service import ChainedLedger

TENANT = "t"
AT = datetime(2026, 10, 1, 6, 0, tzinfo=UTC)


class World:
    def __init__(self) -> None:
        self.clock = FakeClock(AT)
        self.persistence = MemoryPersistence()
        self.store = MemoryLedgerStore(self.persistence)
        self.ledger = ChainedLedger(self.store, self.clock)
        incidents = MemoryRepository(self.persistence, Incident)
        self.signals = SignalIncidents(incidents, self.ledger, self.persistence, self.clock)
        self.expected = ExpectedRuns(
            incidents,
            MemoryRepository(self.persistence, WatchConfiguration),
            self.store,
            self.ledger,
            self.persistence,
            self.clock,
        )

    def red(self, run: str, *, days: int = 0) -> RaiseRed:
        return RaiseRed(
            tenant=TENANT,
            signal="cost.cloud_daily",
            corridor="cost.cloud_daily@1",
            process_version="read-cost@1",
            run_id=run,
            step_id="read",
            at=AT + timedelta(days=days),
            value=412.0,
            median=150.0,
            red_at=300.0,
        )

    async def kinds(self) -> list[tuple[str, str | None]]:
        async with self.persistence.transaction(TENANT):
            return [(e.kind, e.outcome) for e in await self.ledger.entries(TENANT)]


async def test_a_red_value_raises_one_incident_however_often_it_is_looked_at() -> None:
    w = World()
    first = await w.signals.raise_red(w.red("run_1"))
    assert first.kind is IncidentKind.SIGNAL_RED and first.rule == "corridor.red"
    assert first.run_id == "run_1" and first.process_id == "read-cost"
    assert first.facts["signal"] == "cost.cloud_daily" and first.facts["red_at"] == 300.0
    again = await w.signals.raise_red(w.red("run_1"))
    assert again.id == first.id
    assert await w.kinds() == [("incident.raised", "red")]


async def test_a_further_red_value_is_recorded_on_the_open_incident() -> None:
    w = World()
    first = await w.signals.raise_red(w.red("run_1"))
    second = await w.signals.raise_red(w.red("run_2", days=1))
    assert second.id == first.id
    assert [(h.what, h.run and h.run.run_id) for h in second.timeline] == [("red", "run_2")]
    assert await w.signals.raise_red(w.red("run_2", days=1)) == second, "recorded once"
    assert await w.kinds() == [("incident.raised", "red"), ("incident.recorded", "red")]


async def test_after_a_person_closed_it_a_red_value_is_a_new_incident() -> None:
    w = World()
    first = await w.signals.raise_red(w.red("run_1"))
    await w.expected.close(CloseIncident(tenant=TENANT, incident_id=first.id, by="idn_owner"))
    later = await w.signals.raise_red(w.red("run_3", days=2))
    assert later.id != first.id
    listed = await w.expected.incidents(TENANT)
    assert [i.id for i in listed] == [later.id], "the closed one is listed with --all only"
    assert "idn_owner" not in later.model_dump_json(), "an incident names no person"
