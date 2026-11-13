"""S-08 Process from a description, end to end over the memory stores (UC-4.1, ADR-0251).

What is real: the bundle as shipped, the run engine and its queue, the loopback connector and the
wiring behind it, the process component's proposals and registration, the acts on a proposal.
What is faked: the language model, which answers what its script says, and the connector the
described process reaches.

What is proven: a description of a process the tenant does not have becomes a proposal for its
first version that passed registration's validation, and nothing is registered; a step whose
method the model guessed against its exactness class leaves no proposal, and a step no
admissible method fits is a person's; the proposal's rehearsal acts on nothing outside and says,
step by step, what it would have sent; commissioning is the person's act, recorded, and only
then does the process exist; the proposal is the bundle in the open format.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from fakes import FakeConnector, FakeIdentifiers, FakeWorker
from fakes.connector import READ, WRITE
from fakes.identity import directory
from fakes.maturity import VERIFIED
from fakes.model import FakeModel
from fakes.takeover import instructed

from taktus.adapters.driven.connectors.loopback import LoopbackConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryQueue,
    MemoryRepository,
)
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.command.application.service import CommissionPlanHandler
from taktus.components.process.application.service.proposals import Proposals
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
    parse_bundle,
)
from taktus.components.process.domain.model import Process, ProcessVersion, Proposal
from taktus.components.run.application.service import ResumeRun, RunEngine
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.composition.proposals import InstanceChanges, ProposalActs
from taktus.shared.v1 import Command, Plan

ROOT = Path(__file__).resolve().parents[2]
S08 = ROOT / "blueprints" / "self-operation" / "processes" / "S-08-process-from-a-description.yaml"
TENANT = "t"
WHO = "idn_ada"
DESCRIPTION = "read the record, let someone in operations approve it, then create the follow-up"


class Clock:
    def __init__(self) -> None:
        self.current = datetime(2026, 11, 7, 10, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    async def sleep(self, seconds: float) -> None:
        return None


def described(*, guessed: bool = False) -> dict[str, Any]:
    """The bundle a model answers for DESCRIPTION. `guessed`: the approval is put on a language
    model and classed exact, which no admissible method allows."""
    approve: dict[str, Any] = {
        "id": "approve",
        "method": "human",
        "reason": "whether the follow-up is due is a judgement the organisation keeps",
        "rejected": [{"method": "llm", "why": "an approval binds the organisation"}],
        "role": "operations",
        "depends_on": ["read"],
    }
    if guessed:
        approve = {
            **{k: v for k, v in approve.items() if k != "role"},
            "method": "llm",
            "exactness": "exact",
            "checks": [{"kind": "recomputation"}],
            "fallback": {"when": "unsure", "to": "human"},
            "work": {"purpose": "reasoning", "prompt": "approve?"},
        }
    return instructed(
        {
            "id": "follow-up",
            "version": "1",
            "name": "Follow-up",
            "autonomy": {
                "level": 2,
                "reason": "a person confirms every step until the process has run",
                "toward_next": "twenty runs a person confirmed without a correction",
            },
            "limits": {"quota": {"units": 6}},
            "inputs": {"record": {"description": "the record to follow up", "example": "r1"}},
            "steps": [
                {
                    "id": "read",
                    "method": "rule",
                    "reason": "the record is read as it is stored",
                    "rejected": [{"method": "llm", "why": "a record is read, not judged"}],
                    "exactness": "tolerant",
                    "work": {
                        "rule": "connector",
                        "operation": READ,
                        "input": {"id": {"$input": "record"}},
                    },
                },
                approve,
                {
                    "id": "create",
                    "method": "rule",
                    "reason": "the follow-up is created with the record's identifier",
                    "rejected": [{"method": "llm", "why": "the fields are fixed"}],
                    "exactness": "tolerant",
                    "depends_on": ["approve"],
                    "work": {
                        "rule": "connector",
                        "operation": WRITE,
                        "input": {"follows": {"$from": "read", "$select": "output.id"}},
                    },
                },
            ],
        }
    )


def seed() -> dict[str, Any]:
    """A process the tenant already runs, whose real call of the write is the recording a
    rehearsal answers from (ADR-0030)."""
    return instructed(
        {
            "id": "seed",
            "version": "1",
            "name": "Seed",
            "autonomy": {"level": 3, "reason": "a test", "toward_next": "nothing"},
            "limits": {"quota": {"units": 4}},
            "steps": [
                {
                    "id": "create",
                    "method": "rule",
                    "reason": "a fixed record",
                    "rejected": [],
                    "exactness": "tolerant",
                    "work": {"rule": "connector", "operation": WRITE, "input": {"follows": "r0"}},
                }
            ],
        }
    )


class World:
    def __init__(self, answer: str) -> None:
        self.clock = Clock()
        self.ids = FakeIdentifiers()
        self.persistence = MemoryPersistence()
        self.identity = directory((TENANT,), persistence=self.persistence, clock=self.clock)
        self.ledger = self.identity.ledger
        self.runs = MemoryRepository(self.persistence, Run)
        self.processes = MemoryRepository(self.persistence, Process)
        self.versions = MemoryRepository(self.persistence, ProcessVersion)
        self.queue = MemoryQueue(self.persistence, self.clock, lease_seconds=60)
        self.objects = MemoryObjectStore()
        self.model = FakeModel(answer=answer)
        self.connector = FakeConnector()
        self.proposals = Proposals(
            self.versions,
            self.processes,
            MemoryRepository(self.persistence, Proposal),
            self.persistence,
            self.clock,
            self.ids,
        )
        loopback = LoopbackConnector(
            changes=InstanceChanges(self.proposals, self.processes, self.versions, self.persistence)
        )
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.runs,
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=MemoryProvenanceStore(self.persistence),
            workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
            models=StaticModelPool([("model.fake", ["reasoning"], self.model, "fake-model@1")]),
            clock=self.clock,
            ids=self.ids,
            telemetry=NoTelemetry(),
            queue=self.queue,
            connectors=StaticConnectorPool(
                [("connector.loopback", loopback), ("connector.fake", self.connector)]
            ),
        )
        self.register = RegisterProcessVersionHandler(
            self.versions, self.persistence, self.processes, ledger=self.ledger
        )
        commission = CommissionPlanHandler(
            MemoryRepository(self.persistence, Command),
            MemoryRepository(self.persistence, Plan),
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
            commission=commission,
            engine=self.engine,
            identities=self.identity.directory,
            ledger=self.ledger,
            work=self.persistence,
            clock=self.clock,
            ids=self.ids,
            describe_process="s08-process-from-a-description",
        )

    async def setup(self) -> World:
        await self.identity.directory.add(TENANT, WHO, (TENANT, "ops"))
        s08 = yaml.safe_load(S08.read_text(encoding="utf-8"))
        await self.register.execute(RegisterProcessVersion(s08, tenant=TENANT, by=WHO))
        await self.register.execute(RegisterProcessVersion(seed(), tenant=TENANT, by=WHO))
        return self

    async def run_through(self, run_id: str) -> Run:
        async with self.persistence.transaction(TENANT):
            (job,) = await self.queue.claim(TENANT, "runner-a", 5)
        assert job.payload == {"run_id": run_id}
        return await self.engine.resume(
            ResumeRun(run_id=run_id, actor="runner-a", tenant=TENANT, on_claim=True)
        )

    async def seeded(self) -> None:
        """The seed process run once for real, through the same path a proposal's rehearsal
        takes, so that the write has a recording."""
        version = parse_bundle(seed())
        run = await self.acts._started(
            TENANT,
            "seed",
            "TAKTUS_SEED",
            {},
            "seed",
            WHO,
            recognised="process.run",
            goal="seed",
            instead="",
        )
        assert run.process_version == version.ref
        assert (await self.run_through(run.id)).state is RunState.FINISHED

    async def result(self, run: Run, step: str) -> dict[str, Any]:
        (step_run,) = [s for s in run.step_runs if s.step_id == step]
        checkpoint = step_run.checkpoint
        assert checkpoint is not None and checkpoint.result_digest is not None
        found: dict[str, Any] = json.loads(await self.objects.get(checkpoint.result_digest) or b"")
        return found

    async def exists(self, process: str) -> bool:
        async with self.persistence.transaction(TENANT):
            found = await self.processes.get(TENANT, process)
        return found is not None and found.active_version is not None


async def test_a_description_becomes_a_proposal_for_a_first_version_and_nothing_is_registered() -> (
    None
):
    world = await World(json.dumps(described())).setup()
    run = await world.acts.ask(TENANT, "follow-up", DESCRIPTION, WHO)
    assert run.process_version == "s08-process-from-a-description@2"
    finished = await world.run_through(run.id)
    assert finished.state is RunState.FINISHED, finished
    (proposal,) = await world.proposals.of_process(TENANT, "follow-up")
    assert proposal.base_version is None, "made against no version: the process's first"
    assert proposal.request == DESCRIPTION and proposal.requested_by == WHO
    assert {c.id for c in proposal.difference.steps} == {"read", "approve", "create"}
    assert not await world.exists("follow-up"), "nothing of the proposal is registered"
    (prompt,) = world.model.prompts
    assert DESCRIPTION in prompt.user and "follow-up" in prompt.user
    assert "human step" in prompt.system, "the model is told never to guess a method"
    # The proposal is the bundle in the open format: it parses as a version a person can keep.
    kept = parse_bundle(proposal.bundle)
    for step in kept.steps:
        assert step.reason and step.method, step.id
    assert kept.autonomy.reason and kept.autonomy.toward_next


async def test_a_method_guessed_against_its_class_leaves_no_proposal_and_goes_to_a_person() -> None:
    world = await World("```json\n" + json.dumps(described(guessed=True)) + "\n```").setup()
    run = await world.run_through((await world.acts.ask(TENANT, "follow-up", "x", WHO)).id)
    keep = next(s for s in run.step_runs if s.step_id == "keep")
    assert keep.state is not StepState.SUCCEEDED
    assert run.state is not RunState.FINISHED
    assert "an exact result comes from rule, statistics only, never from llm" in (keep.reason or "")
    assert await world.proposals.of_process(TENANT, "follow-up") == []
    assert not await world.exists("follow-up")


async def test_the_rehearsal_sends_nothing_and_says_what_it_would_have_sent() -> None:
    world = await World(json.dumps(described())).setup()
    await world.seeded()
    written = world.connector.acted
    await world.run_through((await world.acts.ask(TENANT, "follow-up", DESCRIPTION, WHO)).id)
    (proposal,) = await world.proposals.of_process(TENANT, "follow-up")
    _, rehearsal = await world.acts.rehearse(TENANT, "follow-up", proposal.id, WHO)
    rehearsed = await world.run_through(rehearsal.id)
    assert rehearsed.state is RunState.FINISHED, rehearsed
    assert rehearsed.rehearsal
    assert world.connector.acted == written, "a rehearsal acts on nothing outside"
    assert [s.step_id for s in rehearsed.step_runs] == ["read", "approve", "create"]
    sent = await world.result(rehearsed, "create")
    assert sent["would_send"] == {"operation": WRITE, "input": {"follows": "r1"}}
    assert not await world.exists("follow-up"), "a rehearsal registers nothing"


async def test_only_the_persons_commissioning_registers_the_process_and_it_is_recorded() -> None:
    world = await World(json.dumps(described())).setup()
    await world.seeded()
    await world.run_through((await world.acts.ask(TENANT, "follow-up", DESCRIPTION, WHO)).id)
    (proposal,) = await world.proposals.of_process(TENANT, "follow-up")
    _, rehearsal = await world.acts.rehearse(TENANT, "follow-up", proposal.id, WHO)
    await world.run_through(rehearsal.id)
    assert not await world.exists("follow-up")
    version = await world.acts.commission(TENANT, "follow-up", proposal.id, WHO)
    assert version.ref == "follow-up@1" and await world.exists("follow-up")
    async with world.persistence.transaction(TENANT):
        entries = await world.ledger.entries(TENANT)
    (commissioned,) = [e for e in entries if e.kind == "process.commissioned"]
    assert commissioned.refs.actor == WHO and commissioned.outcome == proposal.id
