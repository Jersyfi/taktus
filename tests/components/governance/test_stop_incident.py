"""A stop a person requested is followed by an incident and a situation package to the on-call
role (ADR-0280 §1 and §2, UC-7.2).

The runs are the run component's harness of `test_scoped_stop.py`; the confirmation is handed to
the governance component's `StopIncidents` through the composition's `StopIncidentsOfGovernance`,
as the instance wires it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.governance.application.service.stop_incidents import StopIncidents
from taktus.components.governance.domain.model.defects import PARTS
from taktus.components.governance.domain.model.domains import Domain
from taktus.components.governance.domain.model.incident import (
    Incident,
    IncidentKind,
    WatchConfiguration,
)
from taktus.components.run.domain.model import RunState
from taktus.composition.stops import RuleStops, StopIncidentsOfGovernance

from ..run.test_adapter_stop import OPERATOR, TENANT, Harness
from ..run.test_scoped_stop import start


class Followed:
    def __init__(self, h: Harness) -> None:
        self.incidents = MemoryRepository(h.persistence, Incident)
        self.watch = MemoryRepository(h.persistence, WatchConfiguration)
        self.domains = MemoryRepository(h.persistence, Domain)
        self.service = StopIncidents(
            self.incidents,
            self.watch,
            self.domains,
            h.ledger,
            h.objects,
            h.persistence,
            h.clock,
        )
        # The instance's wiring: the run component's port, answered from governance.
        h.stops._followed = StopIncidentsOfGovernance(self.service)

        self.persistence = h.persistence

    async def every(self) -> list[Incident]:
        async with self.persistence.transaction(TENANT):
            return list(await self.incidents.list(TENANT))


def followed(h: Harness) -> Followed:
    return Followed(h)


async def test_a_person_s_stop_that_holds_raises_one_incident_with_a_situation_package() -> None:
    h = Harness()
    f = followed(h)
    async with h.persistence.transaction(TENANT):
        await f.domains.put(
            TENANT,
            Domain(
                id="finance",
                tenant=TENANT,
                name="Finance",
                owner="idn_owner",
                jurisdiction="DE",
                processes=("p",),
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        )
    stop = await h.stops.request_process(TENANT, "p", OPERATOR)
    halted = await start(h, "p")
    assert halted.state is RunState.HALTED

    [confirmed] = await h.stops.confirm(TENANT)
    assert confirmed.stopped == (halted.id,)
    [incident] = await f.every()
    assert incident.kind is IncidentKind.STOP
    assert incident.facts["stop"] == stop.id and incident.facts["runs"] == halted.id
    assert incident.facts["role"] == "operator", "the shipped on-call role (NTC-0271)"
    assert incident.facts["domains"] == "finance", "the domain's owner reads it among its duties"
    assert OPERATOR not in {str(v) for v in incident.facts.values()}, "names no person"

    package = await f.service.package(TENANT, incident.id)
    assert package is not None
    for heading in (
        "What happened",
        "What was tried",
        "What is affected",
        "Options and their risks",
    ):
        assert f"## {heading}" in package
    assert halted.id in package and f"taktusctl stop lift {stop.id}" in package
    assert len(PARTS) == 5

    raised = [e for e in await h.entries() if e.kind == "incident.raised"]
    assert [(e.outcome, e.refs.incident_id, e.refs.actor) for e in raised] == [
        ("stop", incident.id, None)
    ]
    assert raised[0].content_digest == incident.facts["package"]

    # A second look at the same stop raises nothing new.
    await h.stops.show(TENANT, stop.id)
    assert len(await f.every()) == 1


async def test_a_stop_that_found_no_run_is_followed_by_an_incident_too_to_the_configured_role() -> (
    None
):
    h = Harness()
    f = followed(h)
    async with h.persistence.transaction(TENANT):
        await f.watch.put(
            TENANT, WatchConfiguration(id=TENANT, tenant=TENANT, on_call="night-desk")
        )
    stop = await h.stops.request_tenant(TENANT, OPERATOR)
    [confirmed] = await h.stops.confirm(TENANT)
    assert confirmed.stopped == ()
    [incident] = await f.every()
    assert incident.facts["role"] == "night-desk"
    assert incident.facts["stopped"] == 0 and incident.facts["runs"] is None
    package = await f.service.package(TENANT, incident.id)
    assert package is not None and "found no run to halt" in package
    assert stop.id in package


async def test_a_rule_s_stop_raises_no_second_incident() -> None:
    h = Harness()
    f = followed(h)
    await RuleStops(h.stops).stop_process(TENANT, "p", rule="window", incident="inc_rule")
    halted = await start(h, "p")
    assert halted.state is RunState.HALTED
    [confirmed] = await h.stops.confirm(TENANT)
    assert confirmed.rule is not None
    assert await f.every() == [], "the rule's own incident carries it (ADR-0256 §3)"
