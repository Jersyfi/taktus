"""S-07 Change in dialogue, end to end over the memory stores (UC-4.15, ADR-0091 §2, issue #295).

What is real: the bundle as shipped, the run engine, the loopback connector and the wiring behind
it, the process component's proposals. What is faked: the language model, which answers what its
script says.

What is proven: a request in words becomes a proposal with its difference, and nothing is
registered; a model answer that would not register leaves no proposal, and the step that keeps
it fails with the findings, so the run goes to a person; the model is told the active version and
the request, and nothing else of the instance.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from fakes import FakeIdentifiers, FakeWorker
from fakes.identity import directory
from fakes.maturity import VERIFIED
from fakes.model import FakeModel

from taktus.adapters.driven.connectors.loopback import LoopbackConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.command.application.service import CommissionPlan, CommissionPlanHandler
from taktus.components.process.application.service.proposals import Proposals
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
    parse_bundle,
)
from taktus.components.process.domain.model import Process, ProcessVersion, Proposal
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.composition.proposals import InstanceChanges
from taktus.ports.worker import Limits
from taktus.shared.v1 import Command, Intent, Plan, ReplyTo

ROOT = Path(__file__).resolve().parents[2]
S07 = ROOT / "blueprints" / "self-operation" / "processes" / "S-07-change-in-dialogue.yaml"
TENANT = "t"
WHO = "idn_ada"


class Clock:
    def __init__(self) -> None:
        self.current = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    async def sleep(self, seconds: float) -> None:
        return None


def target(version: str, *, second: bool = False) -> dict[str, Any]:
    steps: list[dict[str, Any]] = [
        {
            "id": "one",
            "method": "rule",
            "reason": "a fixed value",
            "rejected": [],
            "exactness": "exact",
            "checks": [{"kind": "recomputation"}],
            "work": {"rule": "constant", "value": 1},
        }
    ]
    if second:
        steps.append({**steps[0], "id": "two", "depends_on": ["one"]})
    return {
        "id": "daily",
        "version": version,
        "name": "Daily",
        "autonomy": {"level": 2, "reason": "a test", "toward_next": "nothing"},
        "steps": steps,
    }


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
        self.model = FakeModel(answer=answer)
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
            objects=MemoryObjectStore(),
            ledger=self.ledger,
            provenance=MemoryProvenanceStore(self.persistence),
            workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
            models=StaticModelPool([("model.fake", ["reasoning"], self.model, "fake-model@1")]),
            clock=self.clock,
            ids=self.ids,
            telemetry=NoTelemetry(),
            connectors=StaticConnectorPool([("connector.loopback", loopback)]),
        )
        self.register = RegisterProcessVersionHandler(
            self.versions, self.persistence, self.processes, ledger=self.ledger
        )
        self.commission = CommissionPlanHandler(
            MemoryRepository(self.persistence, Command),
            MemoryRepository(self.persistence, Plan),
            self.persistence,
            self.clock,
            self.ids,
        )

    async def setup(self) -> World:
        await self.register.execute(RegisterProcessVersion(target("1"), tenant=TENANT, by=WHO))
        return self

    async def ask(self, request: str) -> Run:
        version = parse_bundle(yaml.safe_load(S07.read_text(encoding="utf-8")))
        assert version.limits is not None
        command = Command(
            id=self.ids.new("cmd"),
            channel="channel.web",
            identity=WHO,
            org_path=(TENANT,),
            intent=Intent(raw=request, recognised="process.change"),
            context={},
            reply_to=ReplyTo(channel="channel.web", address="ledger"),
            received_at=self.clock.now(),
        )
        plan = await self.commission.execute(
            CommissionPlan(
                command=command,
                tenant=TENANT,
                goal="change daily",
                autonomy_level=version.autonomy_level,
                steps=version.ordered(),
            )
        )
        return await self.engine.start(
            StartRun(
                plan=plan,
                work=version.work,
                budget=Limits.model_validate(dict(version.limits)),
                process_version=version.ref,
                actor=WHO,
                tenant=TENANT,
                inputs={"process": "daily", "request": request},
            )
        )


async def test_a_request_in_words_becomes_a_proposal_and_nothing_is_registered() -> None:
    world = await World(json.dumps(target("2", second=True))).setup()
    run = await world.ask("add a second step after the first")
    assert run.state is RunState.FINISHED, run
    (proposal,) = await world.proposals.of_process(TENANT, "daily")
    assert proposal.request == "add a second step after the first"
    assert proposal.requested_by == WHO
    assert [(c.id, c.change) for c in proposal.difference.steps] == [("two", "added")]
    async with world.persistence.transaction(TENANT):
        process = await world.processes.get(TENANT, "daily")
    assert process is not None and process.active_version == "1", "nothing is registered"
    (prompt,) = world.model.prompts
    assert "add a second step after the first" in prompt.user
    assert '"one"' in prompt.user, "the model is told the active version"


async def test_an_answer_that_would_not_register_leaves_no_proposal_and_goes_to_a_person() -> None:
    broken = target("2", second=True)
    del broken["steps"][1]["checks"]  # an exact step without a check
    world = await World("```json\n" + json.dumps(broken) + "\n```").setup()
    run = await world.ask("add a second step")
    keep = next(s for s in run.step_runs if s.step_id == "keep")
    assert keep.state is not StepState.SUCCEEDED
    assert run.state is not RunState.FINISHED
    assert await world.proposals.of_process(TENANT, "daily") == []
