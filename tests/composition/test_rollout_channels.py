"""An assistant rolled out into a team chat (UC-12.1, ADR-0261), over the memory stores: the wiki
connector over the fake of the wiki, the chat connector over the fake of the chat service.

What is proven, bullet by bullet of UC-12.1 §2:

- the assistant is a registered process version with an agent — K-02, the flow of the agent
  `helpdesk` — and its run is an ordinary run of that version, in the ledger, called as the
  person and counted by profile;
- in a rollout channel every request is served with the user's own credential, within what the
  agent may do: a user without a credential gets nothing from the source, and a profile that
  does not grant the source is refused before anything is read, whatever credential its user
  holds;
- a message in a rollout channel never becomes a command: it is never completed into one, never
  matched against a process's trigger, never taken as an answer to something Taktus asked;
- the same message sent in a command channel and in a rollout channel is a command in the first
  and an assistant's answer in the second;
- rolling out into a further conversation is one more configuration entry;
- an assistant is switched off as any process is, and its rows are the tenant's export's.

What is faked: the wiki, the chat service and the model. The intake half of the chat connector
is a stand-in answering what the test hands it; its normalisation of the service's deliveries
is `tests/adapters/connectors/test_chat_channel.py`'s.
"""

from __future__ import annotations

import json
import secrets
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
import yaml
from components.run.test_outward_messages import Told
from fakes import FakeIdentifiers
from fakes import chat_service as chat_fake
from fakes.identity import FakeReplies, FixedTenants, directory
from fakes.maturity import VERIFIED
from fakes.takeover import instructed
from taktus_connectors.bookstack.server import Config as WikiConfig
from taktus_connectors.bookstack.server import build_server as wiki_server
from taktus_connectors.slack.server import Config as ChatConfig
from taktus_connectors.slack.server import build_server as chat_server

from composition.test_knowledge_answers import ADA, ANSWER, BOB, CAROL, QUESTION, Reader, Wiki
from composition.test_knowledge_answers import wiki as wiki  # the fixture
from composition.test_reactions import Clock, Connector
from composition.test_reactions import bundle as triggered_bundle
from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryObjectStore,
    MemoryOutbox,
    MemoryProvenanceStore,
    MemoryQueue,
    MemoryRepository,
)
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.postgres.archive import archived_tables
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.catalog.application.service import AgentCatalog
from taktus.components.catalog.domain.model import AgentCore, Grants, RoleProfile
from taktus.components.command.application.service import (
    CommissionPlanHandler,
    CompleteIntake,
    CompleteIntakeHandler,
    IntakeOutcome,
    NotACommand,
    ReceiveIntake,
    ReceiveIntakeHandler,
)
from taktus.components.command.domain.model import IntakeEvent, IntakeStatus
from taktus.components.knowledge.domain.model import KnowledgeEntry
from taktus.components.process.application.service.deactivate import (
    DeactivateProcess,
    DeactivateProcessHandler,
)
from taktus.components.process.application.service.reactions import ReactionsHandler
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.run.application.service import EngineOptions, ResumeRun, RunEngine
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.components.run.ports import MessageRules
from taktus.composition.agents import SharedAgents
from taktus.composition.assistants import NO_ROLE, SWITCHED_OFF, Assistants
from taktus.composition.knowledge import IndexedCitations
from taktus.composition.personal import ConfiguredPersonalCredentials
from taktus.composition.reactions import Reactions, run_id_of
from taktus.ports.connector import Delivery, IntakeResult, Taken
from taktus.ports.model import Completion, Prompt
from taktus.ports.outbox import INTAKE_ACCEPTED, INTAKE_ASSISTANT
from taktus.shared.v1 import Command, Plan, PriceKinds

ROOT = Path(__file__).resolve().parents[2]
K02 = ROOT / "blueprints" / "knowledge" / "processes" / "K-02-answer-in-the-chat.yaml"
TENANT = "default"
CHAT = "channel.chat"
THREAD = "1700000000.000100"
HELP, TEAM, SALES = "C0HELP", "C0TEAM", "C0SALES"
"""A conversation the assistant is rolled out into, one where people command Taktus, and one
the assistant is rolled out into later."""
DAN, EVE = "person:dan", "person:eve"
ACCOUNTS = {ADA: "U0ADA", BOB: "U0BOB", CAROL: "U0CAROL", DAN: "U0DAN", EVE: "U0EVE"}
LABEL = "Written by the organisation's assistant, an AI system."
CHECK, CLASSIFY = "You check an answer", "You classify an answer"


def k02() -> dict[str, Any]:
    found: dict[str, Any] = yaml.safe_load(K02.read_text(encoding="utf-8"))
    return found


class Assistant(Reader):
    """K-01's reader, which also checks the answer it is shown and classifies it."""

    async def complete(self, prompt: Prompt) -> Completion:
        system = prompt.system or ""
        if not (system.startswith(CHECK) or system.startswith(CLASSIFY)):
            return await super().complete(prompt)
        self.prompts.append(prompt)
        return Completion(
            text="send" if system.startswith(CHECK) else "none",
            model=self.name,
            tokens_in=5,
            tokens_out=1,
            by_kind=PriceKinds(input=5, output=1),
            finish="stop",
        )


@dataclass
class ChatService:
    url: str

    def messages(self, conversation: str) -> list[dict[str, Any]]:
        """What was said in the conversation in answer: the messages in the question's thread."""
        found: list[dict[str, Any]] = httpx.get(
            f"{self.url}/_fake/messages", params={"channel": conversation}, timeout=5
        ).json()["messages"]
        return [m for m in found if m.get("thread_ts") == THREAD]


@pytest.fixture
def chat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ChatService]:
    """The chat service, and the assistant's own token in a file its variable names."""
    token = "chat-" + secrets.token_hex(8)
    server = chat_fake.make_server("127.0.0.1", 0, {token: "write"})
    threading.Thread(target=server.serve_forever, daemon=True).start()
    path = tmp_path / "CHAT_TOKEN"
    path.write_text(token, encoding="utf-8")
    monkeypatch.delenv("CHAT_TOKEN", raising=False)
    monkeypatch.setenv("TAKTUS_CREDENTIAL_CHAT_TOKEN_FILE", str(path))
    host, port = server.server_address[:2]
    url = f"http://{host!s}:{port}"
    for conversation in (HELP, TEAM, SALES):
        # The question every test asks, as the service holds it: what an answer hangs from.
        httpx.post(
            f"{url}/_fake/messages",
            json={"channel": conversation, "user": "U0ADA", "text": QUESTION, "ts": THREAD},
            timeout=5,
        ).raise_for_status()
    yield ChatService(url)
    server.shutdown()
    server.server_close()


class Answers:
    """The owner-facing channel's half that takes a message in the thread of something Taktus
    asked: here, every message a person writes is taken as such an answer."""

    def __init__(self) -> None:
        self.taken: list[str] = []

    async def take(self, tenant: str, intake: Any, identity: Any, roles: Any) -> Taken:
        self.taken.append(intake.event_id)
        return Taken(outcome="filed", replied=False)


class World:
    def __init__(
        self,
        wiki: Wiki,
        chat: ChatService,
        *,
        rollout: dict[str, str] | None = None,
        answers: Answers | None = None,
    ) -> None:
        self.clock = Clock(datetime(2026, 11, 7, 9, 0, tzinfo=UTC))
        self.ids = FakeIdentifiers()
        self.identity = directory((TENANT,), clock=self.clock)
        self.persistence = self.identity.persistence
        self.ledger = self.identity.ledger
        self.runs = MemoryRepository(self.persistence, Run)
        self.events = MemoryRepository(self.persistence, IntakeEvent)
        self.commands = MemoryRepository(self.persistence, Command)
        self.outbox = MemoryOutbox(self.persistence, self.clock)
        self.objects = MemoryObjectStore()
        self.queue = MemoryQueue(self.persistence, self.clock, lease_seconds=60)
        self.connector = Connector()
        self.replies = FakeReplies()
        self.wiki = wiki
        self.chat = chat
        self.model = Assistant()
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.runs,
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=MemoryProvenanceStore(self.persistence),
            workers=StaticWorkerPool([]),
            clock=self.clock,
            ids=self.ids,
            telemetry=NoTelemetry(),
            options=EngineOptions(uncalibrated_margin=0.0),
            queue=self.queue,
            connectors=StaticConnectorPool(
                [
                    (
                        "connector.knowledge",
                        McpActionConnector(
                            wiki_server(WikiConfig(target=wiki.url, timeout=5.0)), timeout=10.0
                        ),
                    ),
                    (
                        "connector.chat",
                        McpActionConnector(
                            chat_server(ChatConfig(target=chat.url, timeout=5.0)), timeout=10.0
                        ),
                    ),
                ]
            ),
            models=StaticModelPool(
                [("model.fake", ["triage", "support", "check"], self.model, "fake-model@1")]
            ),
            personal=ConfiguredPersonalCredentials(
                {
                    (ADA, "KNOWLEDGE_TOKEN"): "KNOWLEDGE_TOKEN_ADA",
                    (BOB, "KNOWLEDGE_TOKEN"): "KNOWLEDGE_TOKEN_BOB",
                }
            ),
            citations=IndexedCitations(
                MemoryRepository(self.persistence, KnowledgeEntry), self.persistence
            ),
            messages=Told(rules_=MessageRules(LABEL, 0, None, 10)),
        )
        self.processes = MemoryRepository(self.persistence, Process)
        self.versions = MemoryRepository(self.persistence, ProcessVersion)
        self.register = RegisterProcessVersionHandler(
            self.versions, self.persistence, self.processes, ledger=self.ledger, clock=self.clock
        )
        self.deactivate = DeactivateProcessHandler(self.processes, self.persistence, self.ledger)
        self.receive = ReceiveIntakeHandler(
            {CHAT: self.connector},
            self.events,
            self.persistence,
            self.identity.directory,
            replies=self.replies,
            answers=answers,
            outbox=self.outbox,
            rollout={f"{CHAT}/{HELP}": "helpdesk"} if rollout is None else rollout,
        )
        self.complete = CompleteIntakeHandler(
            self.events,
            self.commands,
            self.identity.directory,
            self.persistence,
            self.clock,
            self.ids,
        )
        commission = CommissionPlanHandler(
            self.commands,
            MemoryRepository(self.persistence, Plan),
            self.persistence,
            self.clock,
            self.ids,
        )
        self.agents = AgentCatalog(
            MemoryRepository(self.persistence, AgentCore),
            MemoryRepository(self.persistence, RoleProfile),
            self.persistence,
            self.ledger,
            self.clock,
        )
        self.shared = SharedAgents(
            catalog=self.agents,
            processes=self.processes,
            versions=self.versions,
            evaluations=cast(Any, None),  # a call evaluates nothing
            commission=commission,
            engine=self.engine,
            identities=self.identity.directory,
            ledger=self.ledger,
            work=self.persistence,
            clock=self.clock,
            ids=self.ids,
        )
        self.reactions = Reactions(
            tenants=FixedTenants((TENANT,)),
            outbox=self.outbox,
            intake=self.complete,
            reactions=ReactionsHandler(self.processes, self.versions, self.persistence),
            commission=commission,
            engine=self.engine,
            runs=self.runs,
            ledger=self.ledger,
            work=self.persistence,
            clock=self.clock,
            identities=self.identity.directory,
            ids=self.ids,
            assistants=Assistants(
                agents=self.shared,
                identities=self.identity.directory,
                runs=self.runs,
                ledger=self.ledger,
                work=self.persistence,
                replies=self.replies,
            ),
        )

    async def setup(self) -> World:
        """K-02 registered, the agent `helpdesk` running it for the role `staff`, which may
        search the knowledge and answer in the chat, and for the role `guest`, which may only
        answer; Ada, Bob and Carol on staff, each with their chat account linked."""
        await self.identity.directory.add(TENANT, "idn_op", (TENANT, "ops"))
        await self.register.execute(RegisterProcessVersion(k02(), tenant=TENANT, by="idn_op"))
        await self.agents.propose_core(
            TENANT,
            agent="helpdesk",
            version="1",
            purpose="Answer staff from the organisation's knowledge in the team chat.",
            instructions="Answer from the documents the person may read; name every source.",
            flow="k-02",
            autonomy_level=3,
            grants=Grants(connectors=("connector.knowledge",), tools=("knowledge.documents", CHAT)),
            by="idn_op",
        )
        await self.agents.set_profile(
            TENANT,
            agent="helpdesk",
            role="staff",
            version="1",
            grants=Grants(tools=("knowledge.documents", CHAT)),
        )
        await self.agents.set_profile(
            TENANT, agent="helpdesk", role="guest", version="1", grants=Grants(tools=(CHAT,))
        )
        for who in (ADA, BOB, CAROL):
            await self.person(who, ("staff",))
        return self

    async def person(self, who: str, roles: tuple[str, ...]) -> None:
        await self.identity.directory.add(TENANT, who, (TENANT, "staff"), roles=roles)
        placed = await self.identity.directory.identity(TENANT, who)
        assert placed is not None
        code = await self.identity.code(placed, CHAT)
        linked = await self.identity.directory.unknown_sender(CHAT, ACCOUNTS[who], code)
        assert linked.linked is not None

    async def says(
        self,
        who: str,
        conversation: str,
        text: str = QUESTION,
        *,
        delivery: str | None = None,
        account: str | None = None,
        kind: str = "person",
    ) -> IntakeOutcome:
        delivery = delivery or f"dlv_{secrets.token_hex(4)}"
        self.connector.answer = IntakeResult.model_validate(
            {
                "accepted": {
                    "event_id": delivery,
                    "event": "message.posted",
                    "channel": CHAT,
                    "sender": {"account": account or ACCOUNTS[who], "kind": kind},
                    "intent": {"raw": text},
                    "context": {
                        "conversation": conversation,
                        "message": THREAD,
                        "event": "message",
                    },
                    "reply_to": {
                        "channel": CHAT,
                        "address": conversation,
                        "thread": THREAD,
                    },
                    "occurred_at": "2026-11-07T09:00:00Z",
                }
            }
        )
        self.clock.current += timedelta(seconds=1)
        return await self.receive.execute(
            ReceiveIntake(
                channel=CHAT,
                delivery=Delivery(headers={}, body="{}", received_at=self.clock.now()),
                tenant=TENANT,
            )
        )

    async def drain(self) -> list[Run]:
        ran: list[Run] = []
        while True:
            async with self.persistence.transaction(TENANT):
                jobs = await self.queue.claim(TENANT, "runner-a", 10)
            if not jobs:
                return ran
            for job in jobs:
                ran.append(
                    await self.engine.resume(
                        ResumeRun(
                            run_id=job.payload["run_id"],
                            actor="runner-a",
                            tenant=TENANT,
                            on_claim=True,
                        )
                    )
                )
                async with self.persistence.transaction(TENANT):
                    await self.queue.complete(TENANT, job.id, "runner-a")

    async def pending(self, topic: str) -> int:
        async with self.persistence.transaction(TENANT):
            return len(await self.outbox.unpublished(TENANT, topic, 100))

    async def entries(self, kind: str) -> list[Any]:
        async with self.persistence.transaction(TENANT):
            return list(await self.ledger.of_kinds(TENANT, (kind,)))

    async def all_runs(self) -> list[Run]:
        async with self.persistence.transaction(TENANT):
            return list(await self.runs.list(TENANT))

    async def commands_kept(self) -> list[Command]:
        async with self.persistence.transaction(TENANT):
            return list(await self.commands.list(TENANT))


def why(run: Run) -> list[tuple[str, str, str | None]]:
    return [(s.step_id, s.state.value, s.reason) for s in run.step_runs]


# --- the same message, a command in one channel and an assistant's answer in the other ------------


async def test_the_same_message_is_a_command_in_a_command_channel_and_answered_in_a_rollout_one(
    wiki: Wiki, chat: ChatService
) -> None:
    world = await World(wiki, chat).setup()

    commanded = await world.says(ADA, TEAM)
    assert commanded.accepted is not None and commanded.assistant is None
    assert commanded.accepted.status is IntakeStatus.AWAITING_IDENTITY
    assert await world.pending(INTAKE_ACCEPTED) == 1
    command = await world.complete.execute(
        CompleteIntake(tenant=TENANT, event_id=commanded.accepted.id)
    )
    assert (command.identity, command.intent.raw) == (ADA, QUESTION), "a command, as Ada"

    served = await world.says(ADA, HELP)
    kept = served.assistant
    assert kept is not None and served.accepted is None
    assert kept.status is IntakeStatus.ASSISTANT
    assert await world.pending(INTAKE_ACCEPTED) == 1, "nothing for the triggers"
    assert await world.pending(INTAKE_ASSISTANT) == 1
    with pytest.raises(NotACommand):
        await world.complete.execute(CompleteIntake(tenant=TENANT, event_id=kept.id))

    started = await world.reactions.tick()
    assert started == [run_id_of(TENANT, "k-02", kept.id)]
    (run,) = await world.drain()
    assert run.state is RunState.FINISHED, why(run)
    assert (run.process_version, run.identity, run.profile) == ("k-02@1", ADA, "helpdesk:staff@1")
    assert run.inputs == {
        "message": QUESTION,
        "reply_address": HELP,
        "reply_thread": THREAD,
    }

    (said,) = chat.messages(HELP)
    holidays, leave = wiki.page_id("Holidays"), wiki.page_id("Leave")
    assert f"Document {holidays} says how holidays are taken." in said["text"]
    assert f"Document {leave} says how holidays are taken." in said["text"]
    assert said["text"].endswith(LABEL), "an outward message a model wrote carries the label"
    assert chat.messages(TEAM) == [], "nothing is said in the command channel"

    # Every command kept is Ada's message in the command channel, or the call of the agent;
    # none carries the rollout channel's message as what to do.
    intents = sorted(c.intent.raw for c in await world.commands_kept())
    assert intents == [QUESTION, "call helpdesk@1 as staff"]
    (called,) = await world.entries("agent.called")
    assert (called.refs.agent_id, called.refs.run_id) == ("helpdesk:staff@1", run.id)
    usage = await world.shared.usage(TENANT, "helpdesk")
    assert [(u["profile"], u["calls"]) for u in usage] == [("helpdesk:staff@1", 1)]
    finished = [e for e in await world.entries("run.finished") if e.refs.run_id == run.id]
    assert [e.refs.process_version for e in finished] == ["k-02@1"], "in the ledger as any run"
    assert await world.reactions.tick() == [], "once per message"


async def test_a_message_in_a_rollout_channel_starts_no_process_but_the_assistants_own(
    wiki: Wiki, chat: ChatService
) -> None:
    world = await World(wiki, chat).setup()
    notes = triggered_bundle("notes", triggers=[{"event": "message.posted", "from_event": {}}])
    notes["inputs"] = {}
    notes["steps"][0]["work"] = {"rule": "constant", "value": 1}
    await world.register.execute(
        RegisterProcessVersion(instructed(notes), tenant=TENANT, by="idn_op")
    )

    served = await world.says(ADA, HELP, "start process notes")
    assert served.assistant is not None
    started = await world.reactions.tick()
    assert [r.process_version for r in await world.all_runs()] == ["k-02@1"]
    assert len(started) == 1, "the trigger on every posted message is not matched"

    await world.says(ADA, TEAM, "start process notes")
    (other,) = await world.reactions.tick()
    run = next(r for r in await world.all_runs() if r.id == other)
    assert run.process_version == "notes@1", "in a command channel the trigger is matched"


async def test_a_message_in_a_rollout_channel_is_never_an_answer_to_what_taktus_asked(
    wiki: Wiki, chat: ChatService
) -> None:
    answers = Answers()
    world = await World(wiki, chat, answers=answers).setup()
    served = await world.says(ADA, HELP, "yes")
    assert served.assistant is not None and served.answer is None
    assert answers.taken == []
    in_team = await world.says(ADA, TEAM, "yes")
    assert in_team.answer == "filed", "a command channel hands it to whoever asked"


async def test_a_message_delivered_twice_is_answered_once(wiki: Wiki, chat: ChatService) -> None:
    world = await World(wiki, chat).setup()
    first = await world.says(ADA, HELP, delivery="dlv_twice")
    again = await world.says(ADA, HELP, delivery="dlv_twice")
    assert first.assistant is not None and again.assistant is not None
    assert await world.pending(INTAKE_ASSISTANT) == 1
    assert len(await world.reactions.tick()) == 1
    await world.drain()
    assert len(chat.messages(HELP)) == 1


# --- the user's own credential, within what the agent may do --------------------------------------


async def test_each_person_is_served_with_their_own_credential_and_without_one_gets_nothing(
    wiki: Wiki, chat: ChatService
) -> None:
    world = await World(wiki, chat).setup()
    await world.says(BOB, HELP)
    await world.reactions.tick()
    (bob,) = await world.drain()
    assert bob.state is RunState.FINISHED, why(bob)
    (said,) = chat.messages(HELP)
    leave, holidays = wiki.page_id("Leave"), wiki.page_id("Holidays")
    assert f"Document {leave} " in said["text"] and f"Document {holidays} " not in said["text"]

    before = wiki.requests()
    await world.says(CAROL, HELP)
    await world.reactions.tick()
    (carol,) = await world.drain()
    search = carol.step_run("search")
    assert search.state is StepState.FAILED, why(carol)
    assert "credential of its own" in (search.reason or "")
    assert wiki.requests() == before, "nothing was asked of the source for Carol"
    assert len(chat.messages(HELP)) == 1, "Carol is answered nothing from the source"


async def test_what_the_agent_may_not_do_no_users_credential_makes_possible(
    wiki: Wiki, chat: ChatService
) -> None:
    world = await World(wiki, chat).setup()
    await world.person(DAN, ("guest",))
    before = wiki.requests()
    await world.says(DAN, HELP)
    assert await world.reactions.tick() == []
    assert await world.all_runs() == [], "refused before anything runs"
    assert wiki.requests() == before
    (refused,) = await world.entries("agent.refused")
    assert (refused.refs.agent_id, refused.outcome) == ("helpdesk", "beyond_profile")
    assert [text for *_, text, _ in world.replies.said][-1].startswith("This assistant cannot")


async def test_a_person_whose_roles_have_no_profile_is_told_so(
    wiki: Wiki, chat: ChatService
) -> None:
    world = await World(wiki, chat).setup()
    await world.person(EVE, ("legal",))
    await world.says(EVE, HELP)
    assert await world.reactions.tick() == []
    assert [text for *_, text, _ in world.replies.said][-1] == NO_ROLE


# --- what a rollout channel passes over -----------------------------------------------------------


async def test_an_unknown_sender_in_a_rollout_channel_is_offered_a_link_and_gets_no_assistant(
    wiki: Wiki, chat: ChatService
) -> None:
    world = await World(wiki, chat).setup()
    outcome = await world.says(ADA, HELP, account="U0STRANGER")
    assert outcome.unknown_sender is not None and outcome.assistant is None
    assert outcome.replied, "offered how to link the account"
    assert await world.pending(INTAKE_ASSISTANT) == 0


async def test_an_automations_message_in_a_rollout_channel_is_passed_over(
    wiki: Wiki, chat: ChatService
) -> None:
    world = await World(wiki, chat).setup()
    outcome = await world.says(ADA, HELP, kind="automation")
    assert outcome.passed == "not_authored" and outcome.assistant is None
    assert await world.pending(INTAKE_ASSISTANT) == 0


# --- configuration only, switched off, exported ---------------------------------------------------


async def test_rolling_out_into_a_further_conversation_is_configuration_only(
    wiki: Wiki, chat: ChatService
) -> None:
    world = await World(wiki, chat).setup()
    assert (await world.says(ADA, SALES)).accepted is not None, "a command channel until named"
    world = await World(
        wiki, chat, rollout={f"{CHAT}/{HELP}": "helpdesk", f"{CHAT}/{SALES}": "helpdesk"}
    ).setup()
    assert (await world.says(ADA, SALES)).assistant is not None
    await world.reactions.tick()
    (run,) = await world.drain()
    assert run.state is RunState.FINISHED, why(run)
    assert len(chat.messages(SALES)) == 1


async def test_a_switched_off_assistant_answers_nothing_and_is_switched_on_again(
    wiki: Wiki, chat: ChatService
) -> None:
    world = await World(wiki, chat).setup()
    await world.deactivate.execute(DeactivateProcess(tenant=TENANT, process_id="k-02", by="idn_op"))
    await world.says(ADA, HELP)
    assert await world.reactions.tick() == []
    assert [text for *_, text, _ in world.replies.said][-1] == SWITCHED_OFF
    (refused,) = await world.entries("agent.refused")
    assert refused.outcome == "no_flow"

    switched_on = k02()
    switched_on["version"] = "2"
    await world.register.execute(RegisterProcessVersion(switched_on, tenant=TENANT, by="idn_op"))
    await world.says(ADA, HELP)
    assert len(await world.reactions.tick()) == 1


def test_an_assistant_is_exported_with_its_tenant_like_any_process() -> None:
    """The tenant's export carries every row of every table with the tenant's name (ADR-0221):
    the assistant's process and versions, its agent's cores and profiles, and its messages."""
    carried = {table.name for table in archived_tables()}
    assert {"process", "process_version", "agent_core", "role_profile", "intake_event"} <= carried


def test_k_02_reads_on_behalf_of_the_person_and_answers_under_the_message_frame() -> None:
    steps = {s["id"]: s for s in k02()["steps"]}
    assert steps["search"]["work"]["on_behalf"] is True
    assert steps["confirm"]["work"]["on_behalf"] is True
    frame = steps["reply"]["work"]["message"]
    assert (frame["check"], frame["classification"]) == ("verify", "promises")
    assert json.dumps(steps["nothing"]["work"]["input"]["text"]).count("found nothing") == 1
    assert ANSWER  # K-01's answering prompt is the one K-02 answers with
