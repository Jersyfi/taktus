"""Only a person changes a cap on open work, and a stop for repetition raises an incident
(UC-8.12 §2, ADR-0132 §3 and §5).

A version whose caps differ from the version it replaces is stored only with a person's
approval. A process, or a worker, that registers one without it is refused, and the refusal is
a ledger entry. The tenant's limits on repetition are part of its watch configuration, with a
shipped default; a stop the run reports becomes one incident, however often it is reported.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fakes import FakeClock

from governance.test_raise import PERSON, TENANT, World, bundle
from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryRepository
from taktus.components.governance.application.service import (
    ConfigureWatch,
    ExpectedRuns,
    Repetitions,
    RepetitionSeen,
)
from taktus.components.governance.domain.model import Incident, WatchConfiguration
from taktus.components.governance.domain.model.incident import IncidentKind
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
)
from taktus.components.process.domain.model import InvalidProcess

WORKER = "idn_p03"


def capped(cap: int, *, version: str) -> dict[str, Any]:
    document = bundle(2, version=version)
    document["open_work"] = {"pull_requests": {"cap": cap}}
    return document


async def kinds(world: World) -> list[tuple[str, str | None, str | None]]:
    async with world.persistence.transaction(TENANT):
        entries = await world.ledger.entries(TENANT)
    return [(e.kind, e.outcome, e.refs.actor) for e in entries if e.kind.startswith("open_work")]


async def test_a_process_that_raises_its_own_cap_is_refused_and_the_refusal_recorded() -> None:
    world = World()
    await world.registered(capped(2, version="1"))
    with pytest.raises(InvalidProcess, match="only a person changes a cap"):
        await world.register.execute(_command(capped(5, version="2"), by=WORKER, approved_by=None))
    assert await kinds(world) == [("open_work.refused", "no_approval", WORKER)]
    async with world.persistence.transaction(TENANT):
        assert await world.versions.get(TENANT, "p@2") is None
        process = await world.processes.get(TENANT, "p")
    assert process is not None and process.active_version == "1"


async def test_removing_a_cap_is_a_change_too() -> None:
    world = World()
    await world.registered(capped(2, version="1"))
    with pytest.raises(InvalidProcess):
        await world.registered(bundle(2, version="2"))
    assert [k for k, _, _ in await kinds(world)] == ["open_work.refused"]


async def test_a_person_changes_a_cap_and_is_named_as_its_actor() -> None:
    world = World()
    await world.registered(capped(2, version="1"))
    stored = await world.registered(capped(3, version="2"), approved_by=PERSON)
    assert stored.open_work["pull_requests"].cap == 3
    assert await kinds(world) == [("open_work.changed", "changed", PERSON)]


async def test_a_version_that_keeps_its_caps_needs_no_approval() -> None:
    world = World()
    await world.registered(capped(2, version="1"))
    await world.registered(capped(2, version="2"))
    assert await kinds(world) == []


def _command(
    document: dict[str, Any], *, by: str, approved_by: str | None
) -> RegisterProcessVersion:
    return RegisterProcessVersion(document, tenant=TENANT, by=by, approved_by=approved_by)


class Governance:
    def __init__(self) -> None:
        self.world = World()
        self.clock = FakeClock(datetime(2026, 10, 23, tzinfo=UTC))
        persistence = self.world.persistence
        self.incidents = MemoryRepository(persistence, Incident)
        self.configurations = MemoryRepository(persistence, WatchConfiguration)
        self.repetitions = Repetitions(
            self.incidents, self.configurations, self.world.ledger, persistence, self.clock
        )


SEEN = RepetitionSeen(
    process_version="p@1",
    run_id="run_1",
    step_id="open",
    rule="calls",
    action="repository.pullrequests.open",
    count=3,
    limit=3,
)


async def test_a_stop_raises_one_incident_that_names_the_action_the_count_and_the_limit() -> None:
    g = Governance()
    incident = await g.repetitions.stopped(TENANT, SEEN)
    assert incident is not None and incident.kind is IncidentKind.REPEATED
    assert incident.rule == "repetition.calls" and incident.run_id == "run_1"
    assert incident.facts == {
        "step": "open",
        "action": "repository.pullrequests.open",
        "count": 3,
        "limit": 3,
    }
    assert await g.repetitions.stopped(TENANT, SEEN) is None, "the same stop raises nothing"
    async with g.world.persistence.transaction(TENANT):
        entries = await g.world.ledger.entries(TENANT)
    raised = [e for e in entries if e.kind == "incident.raised"]
    assert [(e.outcome, e.refs.incident_id, e.refs.step_id) for e in raised] == [
        ("repeated", incident.id, "open")
    ]


async def test_the_limits_are_the_shipped_default_until_the_tenant_sets_its_own() -> None:
    g = Governance()
    shipped = await g.repetitions.limits(TENANT)
    assert (shipped.repeated_calls, shipped.repeated_model_calls) == (3, 3)
    assert shipped.configured_at is None
    watch = ExpectedRuns(
        g.incidents,
        g.configurations,
        MemoryLedgerStore(g.world.persistence),
        g.world.ledger,
        g.world.persistence,
        g.clock,
    )
    await watch.configure(ConfigureWatch(tenant=TENANT, repeated_calls=5), by=PERSON)
    configured = await g.repetitions.limits(TENANT)
    assert (configured.repeated_calls, configured.repeated_model_calls) == (5, 3)
