"""Taktus's own conversation, end to end over the memory stores (UC-1.14, ADR-0325, ADR-0326).

What is real: S-09 as shipped, the run engine with its queue, the loopback connector and the
wiring behind it, the plan dialogue, the conversation and its acts. What is faked: the language
model, which answers what its script says, and the chat, which records what is said in it.

What is proven: a turn runs as a process of its own, as the person, under its budget and in the
ledger; the model is told the message, the closed list of acts and what the person may see; an
act it proposes is checked by rule, read back, and done only on the person's yes; an act off the
list, an answer not in the agreed form and a no each change nothing; the model produces no exact
value; in a chat the conversation takes only what no rule and no trigger takes, and a yes there
does the act.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml
from fakes import FakeClock, FakeIdentifiers, FakeWorker
from fakes.identity import directory
from fakes.maturity import VERIFIED
from fakes.model import FakeModel
from fakes.owner_channel import RecordingDeliveries
from fakes.takeover import instructed

from taktus.adapters.driven.connectors.loopback import LoopbackConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.memory.queue import MemoryQueue
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.adapters.driving.rest.agent_surface import BUILD_RIGHTS, BY_NAME
from taktus.components.command.application.service import CommissionPlanHandler
from taktus.components.command.application.service.conversations import Conversations
from taktus.components.command.domain.model.conversation import ACTS, ActState, Conversation
from taktus.components.process.application.service.proposals import Proposals
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
    parse_bundle,
)
from taktus.components.process.domain.model import Process, ProcessVersion, Proposal
from taktus.components.reporting.domain.model import OwnerChannel
from taktus.components.run.application.service import ResumeRun, RunEngine
from taktus.components.run.domain.model import Run, RunState
from taktus.composition.agent_surface import AgentSurface
from taktus.composition.building import BuildActs
from taktus.composition.conversation import ConversationActs, ConversationInChat
from taktus.composition.owner_channel import OwnerAnswers
from taktus.composition.workspace import workspace_of
from taktus.ports.connector import Intake, IntakeIntent, IntakeReplyTo, Sender, SenderKind
from taktus.ports.identity import Resolution
from taktus.shared.v1 import Command, Plan

ROOT = Path(__file__).resolve().parents[2]
S09 = ROOT / "blueprints" / "self-operation" / "processes" / "S-09-conversation-turn.yaml"
TENANT = "t"
WHO = "idn_ada"
CHAT = IntakeReplyTo(channel="channel.chat", address="C1", thread="1.1")


def daily(triggers: list[dict[str, Any]] | None = None, name: str = "daily") -> dict[str, Any]:
    return instructed(
        {
            "id": name,
            "version": "1",
            "name": name.title(),
            "autonomy": {"level": 2, "reason": "a test", "toward_next": "nothing"},
            "triggers": triggers or [],
            "limits": {"quota": {"units": 5}},
            "steps": [
                {
                    "id": "one",
                    "method": "rule",
                    "reason": "a fixed value",
                    "rejected": [],
                    "exactness": "exact",
                    "checks": [{"kind": "recomputation"}],
                    "work": {"rule": "constant", "value": 1},
                }
            ],
        }
    )


def answer(say: str, act: dict[str, Any] | None = None) -> str:
    return json.dumps({"say": say, "act": act})


class World:
    def __init__(self) -> None:
        self.clock = FakeClock()
        self.ids = FakeIdentifiers()
        self.persistence = MemoryPersistence()
        self.identity = directory(
            (TENANT,), persistence=self.persistence, clock=self.clock, structured=True
        )
        self.ledger = self.identity.ledger
        self.runs = MemoryRepository(self.persistence, Run)
        self.processes = MemoryRepository(self.persistence, Process)
        self.versions = MemoryRepository(self.persistence, ProcessVersion)
        self.model = FakeModel(answer=answer("Hello."))
        self.queue = MemoryQueue(self.persistence, self.clock, lease_seconds=60)
        self.deliveries = RecordingDeliveries()
        loopback = LoopbackConnector()
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
            queue=self.queue,
        )
        commission = CommissionPlanHandler(
            MemoryRepository(self.persistence, Command),
            MemoryRepository(self.persistence, Plan),
            self.persistence,
            self.clock,
            self.ids,
        )
        self.agent = AgentSurface(
            processes=self.processes,
            versions=self.versions,
            commission=commission,
            engine=self.engine,
            ledger=self.ledger,
            work=self.persistence,
            clock=self.clock,
            ids=self.ids,
        )
        assert self.identity.structure is not None
        self.workspace = workspace_of(
            lambda kind: MemoryRepository(self.persistence, kind),
            self.persistence,
            self.ledger,
            self.clock,
            self.ids,
            self.identity.structure,
        )
        self.conversations = Conversations(
            MemoryRepository(self.persistence, Conversation),
            self.ledger,
            self.persistence,
            self.clock,
            self.ids,
        )
        self.building = BuildActs(
            planning=self.workspace.planning,
            proposals=Proposals(
                self.versions,
                self.processes,
                MemoryRepository(self.persistence, Proposal),
                self.persistence,
                self.clock,
                self.ids,
            ),
            acts=None,
            agent=self.agent,
            conversations=self.conversations,
        )
        self.talking = ConversationActs(
            conversations=self.conversations,
            building=self.building,
            agent=self.agent,
            identities=self.identity.directory,
            runs=self.runs,
            work=self.persistence,
            process="s09-conversation-turn",
            deliveries=self.deliveries,
        )
        loopback.bind(conversing=self.talking)
        self.chat = ConversationInChat(
            conversation=self.talking,
            conversations=self.conversations,
            building=self.building,
            identities=self.identity.directory,
            channels=MemoryRepository(self.persistence, OwnerChannel),
            processes=self.processes,
            versions=self.versions,
            work=self.persistence,
            deliveries=self.deliveries,
            secrets=_NoSecrets(),
        )

    async def setup(self, *bundles: dict[str, Any]) -> World:
        register = RegisterProcessVersionHandler(
            self.versions, self.persistence, self.processes, ledger=self.ledger
        )
        for one in (yaml.safe_load(S09.read_text(encoding="utf-8")), daily(), *bundles):
            await register.execute(RegisterProcessVersion(one, tenant=TENANT, by="idn_admin"))
        await self.identity.directory.add(TENANT, WHO, (TENANT,), roles=("ops",))
        return self

    async def who(self) -> Resolution:
        found = await self.identity.directory.identity(TENANT, WHO)
        assert found is not None
        return found

    async def answered(self, run_id: str) -> Run:
        """The turn's run, executed by a runner as the queue hands it out."""
        async with self.persistence.transaction(TENANT):
            await self.queue.claim(TENANT, "runner-a", 5)
        return await self.engine.resume(
            ResumeRun(run_id=run_id, actor="runner-a", tenant=TENANT, on_claim=True)
        )

    async def turn(self, text: str, model_says: str) -> tuple[Run, dict[str, Any]]:
        self.model.answer = model_says
        started = await self.talking.say(await self.who(), text)
        run = await self.answered(started["run"])
        return run, await self.talking.view(await self.who())


class _NoSecrets:
    def carried_by(self, text: str) -> bool:
        return False


async def test_a_turn_runs_as_a_budgeted_process_and_its_act_waits_for_the_yes() -> None:
    world = await World().setup()
    proposed = {"name": "open_plan", "arguments": {"said": "answer supplier invoices"}}
    run, view = await world.turn(
        "I want our supplier invoices answered", answer("I can open a plan for that.", proposed)
    )

    assert run.state is RunState.FINISHED, run
    assert run.identity == WHO and run.process_version == "s09-conversation-turn@1"
    assert run.budget is not None, "the turn runs under its budget"
    async with world.persistence.transaction(TENANT):
        kinds = {e.kind for e in await world.ledger.entries(TENANT) if e.refs.run_id == run.id}
    assert {"run.created", "budget.set", "conversation.answered"} <= kinds

    (prompt,) = world.model.prompts
    assert "I want our supplier invoices answered" in prompt.user
    assert "open_plan(said)" in prompt.user and "rollback_process(" in prompt.user
    assert "daily (Daily, daily@1)" in prompt.user, "what the person may see"
    assert "s09-conversation-turn (" not in prompt.user

    person, taktus = view["turns"]
    assert (person["speaker"], taktus["speaker"]) == ("person", "taktus")
    assert taktus["text"] == "I can open a plan for that." and taktus["run"] == run.id
    (act,) = view["acts"]
    assert act["state"] == "waiting" and act["id"] == taktus["act"]
    assert act["read_back"] == "Open a plan draft for “answer supplier invoices”. Nothing runs yet."
    assert view["thinking"] is None
    assert await world.workspace.planning.mine(TENANT, WHO) == [], "nothing before the yes"

    done = await world.talking.confirm(await world.who(), act["id"], True)
    assert done.state is ActState.DONE and "draft" in done.links
    (draft,) = await world.workspace.planning.mine(TENANT, WHO)
    assert draft.id == done.links["draft"] and draft.goal == "answer supplier invoices"
    last = (await world.talking.view(await world.who()))["turns"][-1]
    assert last["speaker"] == "taktus" and last["text"].startswith(f"Plan draft {draft.id} is open")


async def test_an_act_off_the_list_a_wrong_form_and_a_no_change_nothing() -> None:
    world = await World().setup()
    _, off = await world.turn(
        "delete it all", answer("Done.", {"name": "delete_everything", "arguments": {}})
    )
    assert off["acts"] == []
    assert "not kept: 'delete_everything' is not an act" in off["turns"][-1]["text"]

    _, unformed = await world.turn("hello", "Hello! How can I help?")
    assert unformed["turns"][-1]["text"].startswith("No answer could be formed")
    assert unformed["acts"] == []

    proposed = {"name": "start_process", "arguments": {"process": "daily"}}
    _, waiting = await world.turn("run daily", answer("Shall I start it?", proposed))
    (act,) = waiting["acts"]
    declined = await world.talking.confirm(await world.who(), act["id"], False)
    assert declined.state is ActState.DECLINED
    async with world.persistence.transaction(TENANT):
        started = [r for r in await world.runs.list(TENANT) if r.process_version == "daily@1"]
    assert started == [], "a no starts nothing"


async def test_the_model_produces_no_exact_value() -> None:
    version = parse_bundle(yaml.safe_load(S09.read_text(encoding="utf-8")))
    for step in version.ordered():
        if str(step.method) in ("llm", "neural", "ml", "worker"):
            assert step.exactness is not None and str(step.exactness) != "exact", step.id
    (think,) = [s for s in version.ordered() if str(s.method) == "llm"]
    assert str(think.exactness) == "free"


async def test_in_a_chat_a_rule_or_a_trigger_comes_first_and_a_yes_there_does_the_act() -> None:
    world = await World().setup()

    def said(text: str, event: str, kind: str = "message.posted") -> Intake:
        return Intake(
            event_id=event,
            event=kind,
            channel=CHAT.channel,
            sender=Sender(account="U1", kind=SenderKind.PERSON),
            intent=IntakeIntent(raw=text),
            context={},
            reply_to=CHAT,
            occurred_at=world.clock.now(),
        )

    assert await world.chat.take(TENANT, said("hi", "e0"), None, ()) is None, "nobody placed"
    world.model.answer = answer(
        "Shall I start it?", {"name": "start_process", "arguments": {"process": "daily"}}
    )
    taken = await world.chat.take(TENANT, said("start daily", "e1"), WHO, ("ops",))
    assert taken is not None and taken.outcome == "conversation"
    view = await world.talking.view(await world.who())
    run = await world.answered(view["thinking"])
    assert run.state is RunState.FINISHED
    (first,) = world.deliveries.said
    assert (first.channel, first.address, first.thread) == ("channel.chat", "C1", "1.1")
    assert "Shall I start it?" in first.text and "Start daily." in first.text

    confirmed = await world.chat.take(TENANT, said("yes", "e2"), WHO, ("ops",))
    assert confirmed is not None and confirmed.outcome == "conversation_settled"
    assert world.deliveries.said[-1].text.startswith("Run ")
    async with world.persistence.transaction(TENANT):
        started = [r for r in await world.runs.list(TENANT) if r.process_version == "daily@1"]
    assert len(started) == 1 and started[0].identity == WHO

    await RegisterProcessVersionHandler(
        world.versions, world.persistence, world.processes, ledger=world.ledger
    ).execute(
        RegisterProcessVersion(
            daily([{"event": "message.mentioned"}], name="mentions"), tenant=TENANT, by="idn_admin"
        )
    )
    mentioned = said("@taktus look", "e3", kind="message.mentioned")
    assert await world.chat.take(TENANT, mentioned, WHO, ("ops",)) is None, (
        "a process that starts on the message takes it"
    )


class _Answering:
    async def execute(self, command: Any) -> None:
        return None


class _Reader:
    def __init__(self, takes: bool) -> None:
        self.takes = takes
        self.asked = 0

    async def take(self, *args: Any) -> Any:
        self.asked += 1
        return SimpleNamespace(outcome="taken", replied=True) if self.takes else None


async def test_every_rule_of_the_owners_conversation_reads_before_the_conversation() -> None:
    message = Intake(
        event_id="e1",
        event="message.posted",
        channel=CHAT.channel,
        sender=Sender(account="U1", kind=SenderKind.PERSON),
        intent=IntakeIntent(raw="change process daily: add a step"),
        context={},
        reply_to=CHAT,
        occurred_at=FakeClock().now(),
    )
    for rule_takes in (True, False):
        answers = OwnerAnswers(_Answering())  # type: ignore[arg-type]
        rule, conversation = _Reader(rule_takes), _Reader(True)
        answers.change_with(rule)
        answers.converse_with(conversation)
        taken = await answers.take(TENANT, message, WHO, ("ops",))
        assert taken is not None
        assert conversation.asked == (0 if rule_takes else 1), rule_takes


def test_the_conversation_proposes_from_the_list_the_agent_is_offered_as_tools() -> None:
    assert set(BUILD_RIGHTS) | {"start_process"} == set(ACTS)
    assert set(ACTS) <= set(BY_NAME)


def test_the_guide_names_every_phrase_the_chat_reads_and_every_tool() -> None:
    """`docs/guides/use/talking.md` lists every word of the shipped English phrasebook and every
    tool of a person's own agent, so that what a person can say is findable (DEC-0239)."""
    guide = (ROOT / "docs" / "guides" / "use" / "talking.md").read_text(encoding="utf-8")
    phrasebook = ROOT / "src" / "taktus" / "composition" / "phrasebooks" / "en.json"
    book = json.loads(phrasebook.read_text(encoding="utf-8"))
    words = {w for key, listed in book.items() if key.endswith("_words") for w in listed}
    assert [w for w in sorted(words) if f"`{w}" not in guide] == []
    assert [t for t in sorted(BY_NAME) if f"`{t}`" not in guide] == []
