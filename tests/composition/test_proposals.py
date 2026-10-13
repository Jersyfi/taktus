"""A proposal rehearsed and commissioned, and a process rolled back (UC-4.15, ADR-0091 §3 to §5,
issues #296 and #297), over the memory stores.

The rehearsal is a run of the proposed version that acts on nothing outside and is counted as no
version; only a proposal whose rehearsal finished is commissioned, and only against the version it
was made against; commissioning registers through registration and is in the ledger with who did
it; a rollback registers an earlier version's content again as a new version, and deletes nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from fakes import FakeConnector, FakeIdentifiers, FakeWorker
from fakes.identity import directory
from fakes.maturity import VERIFIED

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryQueue,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.command.application.service import CommissionPlanHandler
from taktus.components.process.application.service.proposals import (
    ProposalError,
    Proposals,
    Propose,
)
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import Process, ProcessVersion, Proposal, ProposalState
from taktus.components.run.application.service import ResumeRun, RunEngine
from taktus.components.run.domain.model import Run, RunState
from taktus.composition.proposals import ProposalActs
from taktus.shared.v1 import Command, Plan

TENANT = "t"
WHO = "idn_ada"


class Clock:
    def __init__(self) -> None:
        self.current = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    async def sleep(self, seconds: float) -> None:
        return None


def bundle(version: str, *, extra: bool = False) -> dict[str, Any]:
    steps: list[dict[str, Any]] = [
        {
            "id": "one",
            "method": "rule",
            "reason": "a fixed value",
            "rejected": [],
            "exactness": "exact",
            "checks": [{"kind": "recomputation"}],
            "work": {"rule": "constant", "value": {"$input": "target"}},
        }
    ]
    if extra:
        steps.append(
            {
                "id": "two",
                "method": "rule",
                "reason": "a second fixed value",
                "rejected": [],
                "exactness": "exact",
                "checks": [{"kind": "recomputation"}],
                "depends_on": ["one"],
                "work": {"rule": "constant", "value": 2},
            }
        )
    return {
        "id": "daily",
        "version": version,
        "name": "Daily",
        "autonomy": {"level": 2, "reason": "a test", "toward_next": "nothing"},
        "inputs": {"target": {"description": "what to read", "example": "a"}},
        "steps": steps,
        "limits": {"quota": {"units": 5}},
    }


class World:
    def __init__(self, change_process: str | None = "s07-change-in-dialogue") -> None:
        self.clock = Clock()
        self.ids = FakeIdentifiers()
        self.persistence = MemoryPersistence()
        self.runs = MemoryRepository(self.persistence, Run)
        self.identity = directory((TENANT,), persistence=self.persistence, clock=self.clock)
        self.ledger = self.identity.ledger
        self.queue = MemoryQueue(self.persistence, self.clock, lease_seconds=60)
        self.connector = FakeConnector()
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.runs,
            work=self.persistence,
            objects=MemoryObjectStore(),
            ledger=self.ledger,
            provenance=MemoryProvenanceStore(self.persistence),
            workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
            clock=self.clock,
            ids=self.ids,
            telemetry=NoTelemetry(),
            queue=self.queue,
            connectors=StaticConnectorPool([("connector.fake", self.connector)]),
        )
        self.processes = MemoryRepository(self.persistence, Process)
        self.versions = MemoryRepository(self.persistence, ProcessVersion)
        self.register = RegisterProcessVersionHandler(
            self.versions, self.persistence, self.processes, ledger=self.ledger
        )
        self.proposals = Proposals(
            self.versions,
            self.processes,
            MemoryRepository(self.persistence, Proposal),
            self.persistence,
            self.clock,
            self.ids,
        )
        self.acts = ProposalActs(
            proposals=self.proposals,
            processes=self.processes,
            versions=self.versions,
            runs=self.runs,
            register=self.register,
            commission=CommissionPlanHandler(
                MemoryRepository(self.persistence, Command),
                MemoryRepository(self.persistence, Plan),
                self.persistence,
                self.clock,
                self.ids,
            ),
            engine=self.engine,
            identities=self.identity.directory,
            ledger=self.ledger,
            work=self.persistence,
            clock=self.clock,
            ids=self.ids,
            change_process=change_process,
        )

    async def setup(self) -> World:
        await self.identity.directory.add(TENANT, WHO, (TENANT, "ops"))
        await self.register.execute(RegisterProcessVersion(bundle("1"), tenant=TENANT, by=WHO))
        return self

    async def propose(self, version: str = "2") -> Proposal:
        return await self.proposals.propose(
            Propose(TENANT, "daily", bundle(version, extra=True), by=WHO)
        )

    async def run_through(self, run_id: str) -> Run:
        async with self.persistence.transaction(TENANT):
            (job,) = await self.queue.claim(TENANT, "runner-a", 5)
        assert job.payload == {"run_id": run_id}
        return await self.engine.resume(
            ResumeRun(run_id=run_id, actor="runner-a", tenant=TENANT, on_claim=True)
        )

    async def active(self) -> str | None:
        async with self.persistence.transaction(TENANT):
            process = await self.processes.get(TENANT, "daily")
        return None if process is None else process.active_version

    async def kinds(self) -> list[str]:
        async with self.persistence.transaction(TENANT):
            entries = await self.ledger.entries(TENANT)
        return [entry.kind for entry in entries if entry.kind.startswith("process.")]


async def test_a_rehearsal_runs_the_proposal_as_no_version_and_acts_on_nothing_outside() -> None:
    world = await World().setup()
    proposal = await world.propose()
    rehearsed, run = await world.acts.rehearse(TENANT, "daily", proposal.id, WHO, {"target": "x"})
    assert rehearsed.state is ProposalState.REHEARSED and rehearsed.rehearsal_run == run.id
    assert run.rehearsal and run.process_version == f"daily@proposal-{proposal.id}"
    finished = await world.run_through(run.id)
    assert finished.state is RunState.FINISHED
    assert world.connector.calls == []
    assert await world.active() == "1", "a rehearsal registers nothing"


async def test_only_a_proposal_whose_rehearsal_finished_is_commissioned() -> None:
    world = await World().setup()
    proposal = await world.propose()
    with pytest.raises(ProposalError) as unrehearsed:
        await world.acts.commission(TENANT, "daily", proposal.id, WHO)
    assert unrehearsed.value.kind == "unrehearsed"
    _, run = await world.acts.rehearse(TENANT, "daily", proposal.id, WHO, {"target": "x"})
    with pytest.raises(ProposalError, match="has not finished"):
        await world.acts.commission(TENANT, "daily", proposal.id, WHO)
    await world.run_through(run.id)
    version = await world.acts.commission(TENANT, "daily", proposal.id, WHO)
    assert version.version == "2" and await world.active() == "2"
    assert await world.kinds() == ["process.commissioned"]
    async with world.persistence.transaction(TENANT):
        entries = await world.ledger.entries(TENANT)
    (commissioned,) = [e for e in entries if e.kind == "process.commissioned"]
    assert commissioned.refs.actor == WHO and commissioned.outcome == proposal.id
    stored = await world.proposals.get(TENANT, "daily", proposal.id)
    assert stored.state is ProposalState.COMMISSIONED


async def test_a_proposal_against_a_version_no_longer_active_is_not_commissioned() -> None:
    world = await World().setup()
    proposal = await world.propose()
    _, run = await world.acts.rehearse(TENANT, "daily", proposal.id, WHO, {"target": "x"})
    await world.run_through(run.id)
    await world.register.execute(RegisterProcessVersion(bundle("3"), tenant=TENANT, by=WHO))
    with pytest.raises(ProposalError) as stale:
        await world.acts.commission(TENANT, "daily", proposal.id, WHO)
    assert stale.value.kind == "stale"
    assert await world.active() == "3"


async def test_a_rollback_registers_an_earlier_version_again_and_deletes_nothing() -> None:
    world = await World().setup()
    await world.register.execute(
        RegisterProcessVersion(bundle("2", extra=True), tenant=TENANT, by=WHO)
    )
    restored = await world.acts.rollback(TENANT, "daily", "1", WHO)
    assert restored.version == "3" and await world.active() == "3"
    assert [s.id for s in restored.steps] == ["one"]
    assert restored.reason == "rolled back to 1"
    async with world.persistence.transaction(TENANT):
        names = sorted(v.version for v in await world.versions.list(TENANT))
    assert names == ["1", "2", "3"], "every version stays"
    assert await world.kinds() == ["process.rolled_back"]
    with pytest.raises(ProposalError) as taken:
        await world.acts.rollback(TENANT, "daily", "1", WHO, as_version="2")
    assert taken.value.kind == "taken"
    with pytest.raises(ProposalError) as unknown:
        await world.acts.rollback(TENANT, "daily", "9", WHO)
    assert unknown.value.kind == "unknown"


S07 = Path(__file__).resolve().parents[2] / "blueprints/self-operation/processes"


async def test_a_change_asked_in_words_starts_s07_for_the_person() -> None:
    world = await World().setup()
    with pytest.raises(ProposalError) as unavailable:
        await world.acts.ask(TENANT, "daily", "add a step", WHO)
    assert unavailable.value.kind == "unavailable"
    document = yaml.safe_load((S07 / "S-07-change-in-dialogue.yaml").read_text(encoding="utf-8"))
    await world.register.execute(RegisterProcessVersion(document, tenant=TENANT, by=WHO))
    run = await world.acts.ask(TENANT, "daily", "add a step", WHO)
    assert run.process_version == "s07-change-in-dialogue@1"
    assert run.inputs == {"process": "daily", "request": "add a step"}
    assert not run.rehearsal and run.state is RunState.PLANNED
    with pytest.raises(ProposalError) as unknown:
        await world.acts.ask(TENANT, "nothing", "add a step", WHO)
    assert unknown.value.kind == "unknown"


async def test_without_a_named_change_process_no_request_in_words_is_taken() -> None:
    """Which process turns words into a proposal is the operator's configuration, never a
    default of the product (ADR-0092): with none named, the change is handed over as a bundle,
    even where the tenant registered a process that could do it."""
    world = await World(change_process=None).setup()
    document = yaml.safe_load((S07 / "S-07-change-in-dialogue.yaml").read_text(encoding="utf-8"))
    await world.register.execute(RegisterProcessVersion(document, tenant=TENANT, by=WHO))
    with pytest.raises(ProposalError, match="TAKTUS_CHANGE_PROCESS") as unavailable:
        await world.acts.ask(TENANT, "daily", "add a step", WHO)
    assert unavailable.value.kind == "unavailable"
