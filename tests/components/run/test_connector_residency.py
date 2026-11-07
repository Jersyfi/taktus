"""A connector step, the hosts a worker's unit reaches, and every outward effect are held to the
tenant's residency rule (UC-11.1 §2, ADR-0281).

A connector is where its configuration declares it, `elsewhere` where nobody did. A connector
step whose connector the rule does not admit fails at its boundary without being called, naming
the rule; so does a worker step whose unit would reach a host outside it. Every egress entry is
followed by `residency.egress`, naming the location the effect went to. For each rule, `own` and
`eu`, data of the restricted class sent through a process with connectors and workers at several
locations leaves no egress entry outside the permitted location.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from fakes import FakeClock, FakeConnector, FakeIdentifiers, FakeMaturities, FakeWorker
from fakes.connector import READ, WRITE

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.run.application.service import EngineOptions, RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.ports.connector import CallContext, Capabilities, Result
from taktus.ports.model import Location, Permitted, admits
from taktus.ports.worker import ComputeLimit, Limits
from taktus.shared.v1 import (
    EGRESS_KINDS,
    Commissioned,
    ExactnessClass,
    Fallback,
    LedgerEntry,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    Step,
)

AT = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
TENANT = "t"
PERSON = "idn_operator"
CHANGE = "change.implement"
CREDENTIALS = [{"name": "FAKE_TOKEN", "injected_as": "env"}]


class Rule:
    """A tenant's residency rule: its own location, narrowed per data class."""

    def __init__(self, own: Permitted = "anywhere", **classes: Permitted) -> None:
        self.own = own
        self.classes = classes

    async def permitted(
        self, tenant: str, data_class: str | None, process: str | None = None
    ) -> Permitted:
        if data_class is not None and data_class in self.classes:
            return self.classes[data_class]
        return self.own


@dataclass
class Named(FakeConnector):
    """The fake connector under a capability of its own, so that several serve one process."""

    capability: str = "fake.records"

    async def capabilities(self) -> Capabilities:
        declared = (await super().capabilities()).model_dump(mode="json", exclude_none=True)
        declared["capabilities"] = [self.capability]
        for operation in declared["operations"]:
            operation["capability"] = self.capability
            operation["name"] = operation["name"].replace("fake.records", self.capability)
        return Capabilities.model_validate(declared)

    async def call(self, operation: str, context: CallContext, input: Mapping[str, Any]) -> Result:
        return await super().call(
            operation.replace(self.capability, "fake.records"), context, input
        )


def call(id: str, operation: str, data_class: str | None, after: str | None) -> tuple[Step, Any]:
    step = Step(
        id=id,
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.SOURCED,
        depends_on=(after,) if after else None,
    )
    work: dict[str, Any] = {
        "rule": "connector",
        "operation": operation,
        "input": {"title": "t", "id": "issue-1"},
        "credentials": CREDENTIALS,
    }
    if data_class is not None:
        work["data_class"] = data_class
    return step, work


def change(data_class: str | None, hosts: Sequence[str] = (), after: str | None = None) -> Any:
    step = Step(
        id="implement",
        method=Method.WORKER,
        reason="a change is implemented as a whole by a worker",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        fallback=Fallback(when="no worker may be handed the change", to=Method.HUMAN),
        requires=(CHANGE,),
        depends_on=(after,) if after else None,
    )
    work: dict[str, Any] = {
        "task": {"goal": "implement the change", "acceptance": ["the change is there"]},
        "allowed_hosts": list(hosts),
    }
    if data_class is not None:
        work["data_class"] = data_class
    return step, work


@dataclass
class Ran:
    run: Run
    entries: list[LedgerEntry]


async def run_once(
    steps: Sequence[tuple[Step, Any]],
    rule: Rule | None,
    *,
    connectors: Sequence[tuple[str, FakeConnector]] = (),
    locations: Mapping[str, Location] | None = None,
    workers: Sequence[tuple[str, FakeWorker]] = (),
    hosts: Mapping[str, Location] | None = None,
) -> Ran:
    clock = FakeClock(AT)
    persistence = MemoryPersistence()
    ledger = ChainedLedger(MemoryLedgerStore(persistence), clock)
    engine = RunEngine(
        runs=MemoryRepository(persistence, Run),
        work=persistence,
        objects=MemoryObjectStore(),
        ledger=ledger,
        provenance=MemoryProvenanceStore(persistence),
        workers=StaticWorkerPool(list(workers)),
        connectors=StaticConnectorPool(list(connectors), locations=locations),
        clock=clock,
        ids=FakeIdentifiers(),
        telemetry=NoTelemetry(),
        maturities=FakeMaturities(),
        residency=rule,
        options=EngineOptions(host_locations=dict(hosts or {})),
    )
    plan = Plan(
        id="pln_1",
        command_id="cmd_1",
        goal="g",
        autonomy_level=3,
        steps=tuple(step for step, _ in steps),
        results_in=PlanResult.RUN,
        status=PlanStatus.COMMISSIONED,
        commissioned=Commissioned(by=PERSON, at=AT),
    )
    run = await engine.start(
        StartRun(
            plan=plan,
            work={step.id: work for step, work in steps},
            budget=Limits(compute=ComputeLimit(seconds=10, resource_class="cpu.small")),
            process_version="payroll@1",
            actor=PERSON,
            tenant=TENANT,
        )
    )
    async with persistence.transaction(TENANT):
        entries = list(await ledger.entries(TENANT, run.id))
    return Ran(run, entries)


# --- a connector step ------------------------------------------------------------------------


async def test_a_connector_outside_the_rule_is_never_called_and_the_step_names_the_rule() -> None:
    """A tenant with an EU rule: a connector nobody declared counts as `elsewhere`; the step
    fails before it is called, and the reason names the rule, the connector and its location."""
    abroad = FakeConnector()
    ran = await run_once(
        [call("write", WRITE, None, None)], Rule("eu"), connectors=[("connector.abroad", abroad)]
    )
    assert abroad.calls == [] and abroad.acted == 0
    step_run = ran.run.step_run("write")
    assert step_run.state is StepState.FAILED
    reason = step_run.reason or ""
    assert "residency rule admits (eu)" in reason and "connector.abroad" in reason
    assert "is at elsewhere, so nothing was sent" in reason
    assert not [e for e in ran.entries if e.kind in EGRESS_KINDS]


async def test_a_declared_connector_inside_the_rule_is_called() -> None:
    inside = FakeConnector()
    ran = await run_once(
        [call("write", WRITE, None, None)],
        Rule("eu"),
        connectors=[("connector.inside", inside)],
        locations={"connector.inside": "eu"},
    )
    assert ran.run.state is RunState.FINISHED, ran.run.reason
    assert inside.acted == 1


async def test_the_step_s_data_class_narrows_the_rule_for_a_connector() -> None:
    """A read of `personal` data is kept to `own`; the same read of no class is not."""
    inside = FakeConnector()
    rule = Rule("eu", personal="own")
    pool = {"connectors": [("connector.inside", inside)], "locations": {"connector.inside": "eu"}}
    ran = await run_once([call("read", READ, "personal", None)], rule, **pool)
    assert ran.run.step_run("read").state is StepState.FAILED and inside.calls == []
    assert "residency rule admits (own)" in (ran.run.step_run("read").reason or "")
    ran = await run_once([call("read", READ, None, None)], rule, **pool)
    assert ran.run.state is RunState.FINISHED and len(inside.calls) == 1


async def test_a_tenant_without_a_rule_calls_an_undeclared_connector_as_before() -> None:
    abroad = FakeConnector()
    ran = await run_once(
        [call("write", WRITE, "personal", None)], None, connectors=[("connector.abroad", abroad)]
    )
    assert ran.run.state is RunState.FINISHED and abroad.acted == 1


# --- every outward effect names where it went --------------------------------------------------


async def test_every_egress_entry_is_followed_by_the_location_it_went_to() -> None:
    inside = FakeConnector()
    ran = await run_once(
        [call("write", WRITE, None, None)],
        None,
        connectors=[("connector.inside", inside)],
        locations={"connector.inside": "eu"},
    )
    kinds = [e.kind for e in ran.entries]
    egress = kinds.index("egress.write")
    located = ran.entries[egress + 1]
    assert located.kind == "residency.egress" and located.outcome == "eu"
    assert located.adapter == "connector.inside" == ran.entries[egress].adapter
    assert located.refs.step_id == "write"
    assert located.content_digest == ran.entries[egress].content_digest


# --- the hosts a unit may reach --------------------------------------------------------------


async def test_a_host_outside_the_rule_is_never_reached() -> None:
    """A worker inside the rule, handed a frame with a host outside it: nothing is assigned, and
    the reason names the rule and the host. Declared inside it, the same step runs."""
    own = FakeWorker(capabilities_offered=(CHANGE,), data_location="own")
    steps = [change("personal", hosts=("api.example.com", "api.example.eu"))]
    rule = Rule("anywhere", personal="eu")
    ran = await run_once(steps, rule, workers=[("worker.own", own)], hosts={"api.example.eu": "eu"})
    assert own.assignments == []
    step_run = ran.run.step_run("implement")
    assert step_run.state is StepState.FAILED
    reason = step_run.reason or ""
    assert "residency rule admits (eu)" in reason and "the host api.example.com" in reason
    ran = await run_once(
        steps,
        rule,
        workers=[("worker.own", own)],
        hosts={"api.example.eu": "eu", "api.example.com": "own"},
    )
    assert ran.run.state is RunState.FINISHED, ran.run.reason
    assert len(own.assignments) == 1


async def test_a_worker_s_own_service_hosts_are_held_to_the_rule() -> None:
    eu = FakeWorker(capabilities_offered=(CHANGE,), data_location="eu")
    pool = StaticWorkerPool([("worker.eu", eu)], hosts={"worker.eu": ("model.example.net",)})
    resolved = await pool.resolve((CHANGE,), "eu")
    assert resolved is not None and resolved.hosts == ("model.example.net",)


# --- an egress test per rule -----------------------------------------------------------------


@pytest.mark.parametrize("permitted", ["own", "eu"])
async def test_restricted_data_through_a_process_leaves_no_egress_outside_the_rule(
    permitted: Permitted,
) -> None:
    """UC-11.1 §2: data of class `personal` goes through a worker step and three writes, with
    workers and connectors at `elsewhere`, `eu` and `own`. Every egress entry the run leaves
    went to a location the rule admits, and no adapter outside it was handed anything."""
    workers = {
        location: FakeWorker(capabilities_offered=(CHANGE,), data_location=location)
        for location in ("elsewhere", "eu", "own")
    }
    connectors = {
        location: Named(capability=f"{location}.records") for location in ("own", "eu", "elsewhere")
    }
    steps = [
        change("personal"),
        call("own", "own.records.create", "personal", "implement"),
        call("eu", "eu.records.create", "personal", "own"),
        call("elsewhere", "elsewhere.records.create", "personal", "eu"),
    ]
    ran = await run_once(
        steps,
        Rule("anywhere", personal=permitted),
        connectors=[(f"connector.{loc}", c) for loc, c in connectors.items()],
        locations={f"connector.{loc}": loc for loc in connectors},
        workers=[(f"worker.{loc}", w) for loc, w in workers.items()],
    )
    egress = [e for e in ran.entries if e.kind in EGRESS_KINDS]
    located = [e for e in ran.entries if e.kind == "residency.egress"]
    assert egress, "the data left through the connectors the rule admits"
    assert len(located) == len(egress)
    assert all(admits(permitted, e.outcome) for e in located), [e.outcome for e in located]
    for location, worker in workers.items():
        if not admits(permitted, location):
            assert worker.assignments == [], location
    for location, connector in connectors.items():
        if not admits(permitted, location):
            assert connector.calls == [], location
        else:
            assert connector.acted == 1, location
    first_outside = "eu" if permitted == "own" else "elsewhere"
    failed = ran.run.step_run(first_outside)
    assert failed.state is StepState.FAILED
    assert f"residency rule admits ({permitted})" in (failed.reason or "")
