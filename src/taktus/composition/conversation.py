"""Taktus's own conversation: a person talks, Taktus answers and proposes acts, the person says
yes or no (ADR-0325, ADR-0326, UC-1.14).

- **Every turn is a run.** What the person said is kept in their conversation, and a run of the
  conversation process the operator names (`TAKTUS_CONVERSATION_PROCESS`, a tenant's bundle —
  `blueprints/self-operation/` ships S-09) forms the answer, acting as the person. Its budget,
  its ledger and its provenance hold the turn like any other run (control-plane.md §1). Its
  language-model step reads the message, the recent turns, the closed list of acts and what the
  person may see; its last step is a rule that keeps the answer.
- **The answer is kept by rule.** `answer` reads the model's text as one JSON object, `say` and
  at most one `act`. The act is checked against the closed list and read back by rule
  (`composition/building.py`); an act off the list, or one on something the person may not see,
  is not kept, and the answer says so. A text that is not the agreed form keeps no act and says
  so. Nothing the model says is acted on.
- **Only the person's yes acts.** An act waits in the conversation until the person confirms it
  — on the web page, or with a yes in the chat it was proposed in.
- **The chat, rule first.** `ConversationInChat` takes a message in a chat Taktus reads only
  after every rule of the owner's conversation passed it over, and only when no process of the
  tenant starts on that kind of message (ADR-0326).

This is wiring, because a turn crosses the command, process, run and reporting components.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

import structlog

from taktus.adapters.driving.rest.wiring import BuildRefused, StartRefused
from taktus.components.command.application.service.conversations import (
    ConversationError,
    Conversations,
)
from taktus.components.command.domain.model.conversation import (
    ACTS,
    ActState,
    Conversation,
    ProposedAct,
)
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.reporting.domain.model import OwnerChannel
from taktus.components.reporting.ports import Deliveries, SecretValues, Sent
from taktus.components.run.domain.model import DemandToAccept, Run
from taktus.composition.agent_surface import AgentSurface
from taktus.composition.building import BuildActs
from taktus.ports.connector import Intake
from taktus.ports.identity import IdentityResolver, Resolution
from taktus.ports.persistence import Repository, Tenant, UnitOfWork

log = structlog.get_logger("taktusd")

WEB = "channel.web"
HISTORY = 12
"""The turns before the message the model is shown."""
DRAFTS = 5
ENDED = ("waiting_human", "halted", "escalated", "finished")
"""The states in which a run forms no answer on its own any more."""
NOT_FORMED = (
    "No answer could be formed: the model's answer was not in the agreed form. Please say it "
    "again, perhaps in other words."
)
NO_PROCESS = (
    "Taktus has no conversation on this instance yet: the operator names its conversation "
    "process (TAKTUS_CONVERSATION_PROCESS)."
)
NOT_SAID = "Nothing of this answer can be shown here; the web page shows it."
FENCE = re.compile(r"^```[a-z]*\s*\n(.*)\n```\s*$", re.DOTALL)


def _turns(conversation: Conversation) -> list[dict[str, Any]]:
    return [t.document() for t in conversation.turns]


class ConversationActs:
    """The conversation as the surfaces and the loopback connector reach it."""

    def __init__(
        self,
        *,
        conversations: Conversations,
        building: BuildActs,
        agent: AgentSurface,
        identities: IdentityResolver,
        runs: Repository[Run],
        work: UnitOfWork,
        process: str | None,
        deliveries: Deliveries | None = None,
        secrets: SecretValues | None = None,
    ) -> None:
        """`process` is the conversation process, as the operator names it; None, the default:
        no conversation is had on this instance."""
        self._conversations = conversations
        self._building = building
        self._agent = agent
        self._identities = identities
        self._runs = runs
        self._work = work
        self.process = process
        self._deliveries = deliveries
        self._secrets = secrets

    # --- the surfaces ---------------------------------------------------------------------------

    async def view(self, who: Resolution) -> dict[str, Any]:
        found = await self._fresh(await self._conversations.of(who.tenant, who.identity))
        return {
            "available": self.process is not None,
            "conversation": found.id,
            "turns": _turns(found),
            "acts": [a.document() for a in found.acts],
            "thinking": found.thinking,
            "acts_offered": {name: spec.summary for name, spec in ACTS.items()},
        }

    async def say(
        self,
        who: Resolution,
        text: str,
        *,
        channel: str = WEB,
        reply: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """The person's turn kept, and the run forming the answer started as them."""
        if self.process is None:
            raise BuildRefused(NO_PROCESS)
        text = text.strip()
        if not text:
            raise BuildRefused("say something")
        await self._fresh(await self._conversations.of(who.tenant, who.identity))
        try:
            kept = await self._conversations.said(who.tenant, who.identity, channel, text, reply)
        except ConversationError as error:
            raise BuildRefused(str(error)) from error
        try:
            run = await self._agent.start(
                who,
                self.process,
                {"conversation": kept.id, "message": text},
                channel=channel,
                address=f"conversation:{kept.id}",
            )
        except DemandToAccept as error:
            raise BuildRefused(f"this answer would need much of what remains: {error}") from error
        except StartRefused as error:
            raise BuildRefused(f"no answer can be formed: {error}") from error
        await self._conversations.thinking(who.tenant, kept.id, run.id)
        return {"conversation": kept.id, "run": run.id}

    async def confirm(self, who: Resolution, act_id: str, yes: bool) -> ProposedAct:
        return await self._building.confirm(who, act_id, yes)

    # --- the conversation process, through the loopback connector ---------------------------

    async def context(self, tenant: Tenant, identity: str, conversation: str) -> dict[str, Any]:
        """What the model is told: the message, the turns before it, the closed list of acts and
        what the person may see — the processes, their open plan drafts."""
        found, who = await self._own(tenant, identity, conversation)
        said = [t for t in found.turns if t.speaker == "person"]
        if not said:
            raise ValueError(f"the conversation {conversation} has no message to answer")
        before = found.turns[: found.turns.index(said[-1])][-HISTORY:]
        history = "\n".join(
            f"{'Person' if t.speaker == 'person' else 'Taktus'}: {t.text}" for t in before
        )
        acts = "\n".join(
            f"- {name}({', '.join(a.name + ('' if a.required else '?') for a in spec.arguments)})"
            f": {spec.summary}"
            for name, spec in ACTS.items()
        )
        processes = [
            f"- {p['process']} ({p['name']}, {p['version']})"
            for p in await self._agent.processes(who)
            if p["process"] != self.process
        ]
        drafts = [
            f"- plan draft {v['draft']['id']}: {v['draft'].get('goal') or 'no goal yet'}"
            for v in (await self._building.plans(who))
            if not v["commissioned"]
        ][:DRAFTS]
        return {
            "message": said[-1].text,
            "history": history or "(none)",
            "acts": acts,
            "known": "\n".join(processes + drafts) or "(nothing yet)",
        }

    async def answer(
        self, tenant: Tenant, identity: str, run_id: str, conversation: str, text: str
    ) -> dict[str, Any]:
        """The model's answer kept as Taktus's turn, with its act checked and read back by rule;
        said in the chat too where the message came from one."""
        found, who = await self._own(tenant, identity, conversation)
        said, act, formed = await self._read(who, text)
        turn, proposed = await self._conversations.answered(
            tenant, conversation, said, run=run_id, act=act
        )
        if found.reply is not None and self._deliveries is not None:
            await self._said_in_chat(tenant, found.reply, run_id, turn.text, proposed)
        return {
            "formed": formed,
            "act": None if proposed is None else proposed.id,
            "read_back": None if proposed is None else proposed.read_back,
        }

    # --- helpers --------------------------------------------------------------------------------

    async def _read(
        self, who: Resolution, text: str
    ) -> tuple[str, tuple[str, Mapping[str, Any], str] | None, bool]:
        stripped = text.strip()
        fenced = FENCE.match(stripped)
        if fenced is not None:
            stripped = fenced.group(1).strip()
        try:
            document = json.loads(stripped)
        except json.JSONDecodeError:
            return NOT_FORMED, None, False
        said = document.get("say") if isinstance(document, dict) else None
        if not isinstance(said, str) or not said.strip():
            return NOT_FORMED, None, False
        said = said.strip()[:6000]
        proposed = document.get("act")
        if proposed is None:
            return said, None, True
        name = proposed.get("name") if isinstance(proposed, dict) else None
        arguments = proposed.get("arguments", {}) if isinstance(proposed, dict) else None
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return (
                f"{said}\n\n(An act was proposed in no form Taktus reads; none is kept.)",
                None,
                True,
            )
        try:
            read_back = await self._building.read_back(who, name, arguments)
        except BuildRefused as refused:
            return f"{said}\n\n(The act proposed is not kept: {refused}.)", None, True
        return said, (name, arguments, read_back), True

    async def _own(
        self, tenant: Tenant, identity: str, conversation: str
    ) -> tuple[Conversation, Resolution]:
        try:
            found = await self._conversations.get(tenant, conversation)
        except ConversationError as error:
            raise ValueError(str(error)) from error
        if found.participant != identity:
            raise ValueError(f"the conversation {conversation} is not the run's person's")
        who = await self._identities.identity(tenant, identity)
        if who is None:
            raise ValueError(f"the identity {identity!r} is not known to {tenant!r}")
        return found, who

    async def _fresh(self, conversation: Conversation) -> Conversation:
        """The conversation, with a run that ended without answering no longer thinking."""
        if conversation.thinking is None:
            return conversation
        async with self._work.transaction(conversation.tenant):
            run = await self._runs.get(conversation.tenant, conversation.thinking)
        if run is not None and str(run.state) not in ENDED:
            return conversation
        ended = "ended" if run is None else str(run.state)
        await self._conversations.answered(
            conversation.tenant,
            conversation.id,
            f"No answer was formed: run {conversation.thinking} is {ended}.",
            run=conversation.thinking,
        )
        return await self._conversations.get(conversation.tenant, conversation.id)

    async def _said_in_chat(
        self,
        tenant: Tenant,
        reply: Mapping[str, str],
        run_id: str,
        text: str,
        proposed: ProposedAct | None,
    ) -> None:
        if self._deliveries is None:
            return
        lines = [text]
        if proposed is not None:
            lines.append(f"I read this as: {proposed.read_back} Answer yes to do it, or no.")
        said = "\n\n".join(lines)
        if self._secrets is not None and self._secrets.carried_by(said):
            said = NOT_SAID
        await self._deliveries.say(
            tenant,
            reply["channel"],
            reply["address"],
            said,
            thread=reply.get("thread"),
            key=_key("answer", tenant, run_id),
        )


class InChat:
    """What became of a message the conversation took in a chat."""

    def __init__(self, outcome: str, replied: bool) -> None:
        self.outcome = outcome
        self.replied = replied


YES = ("yes",)
NO = ("no",)


class ConversationInChat:
    """The conversation in any chat Taktus reads, after every rule (ADR-0326 §3)."""

    def __init__(
        self,
        *,
        conversation: ConversationActs,
        conversations: Conversations,
        building: BuildActs,
        identities: IdentityResolver,
        channels: Repository[OwnerChannel],
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
        work: UnitOfWork,
        deliveries: Deliveries,
        secrets: SecretValues,
    ) -> None:
        self._conversation = conversation
        self._conversations = conversations
        self._building = building
        self._identities = identities
        self._channels = channels
        self._processes = processes
        self._versions = versions
        self._work = work
        self._deliveries = deliveries
        self._secrets = secrets

    async def take(
        self, tenant: Tenant, intake: Intake, identity: str | None, roles: tuple[str, ...]
    ) -> InChat | None:
        """None when the message is none of the conversation's: no conversation process, a
        sender nobody placed, or a process of the tenant that starts on this kind of message.
        Then it goes on as any other message would."""
        text = intake.intent.raw.strip()
        if self._conversation.process is None or identity is None or not text:
            return None
        if await self._starts_a_process(tenant, intake.event):
            return None
        who = await self._identities.identity(tenant, identity)
        if who is None:
            return None
        to = intake.reply_to
        waiting = [
            a
            for a in (await self._conversations.of(tenant, identity)).acts
            if a.state is ActState.WAITING and a.channel == to.channel
        ]
        yes, no = await self._words(tenant)
        word = text.lower().strip(" .!")
        if waiting and (word in yes or word in no):
            try:
                settled = await self._building.confirm(who, waiting[-1].id, word in yes)
                said, outcome = settled.outcome or "Done.", "conversation_settled"
            except BuildRefused as refused:
                said, outcome = str(refused), "conversation_refused"
        else:
            try:
                await self._conversation.say(
                    who,
                    text,
                    channel=to.channel,
                    reply={
                        k: v
                        for k, v in (
                            ("channel", to.channel),
                            ("address", to.address),
                            ("thread", to.thread),
                        )
                        if v
                    },
                )
                return InChat("conversation", replied=False)
            except BuildRefused as refused:
                said, outcome = str(refused), "conversation_refused"
        if self._secrets.carried_by(said):
            said = NOT_SAID
        sent = await self._deliveries.say(
            tenant,
            to.channel,
            to.address,
            said,
            thread=to.thread,
            key=_key("settled", tenant, intake.event_id),
        )
        return InChat(outcome, replied=isinstance(sent, Sent))

    async def _words(self, tenant: Tenant) -> tuple[tuple[str, ...], tuple[str, ...]]:
        async with self._work.transaction(tenant):
            found = await self._channels.get(tenant, tenant)
        if found is None:
            return YES, NO
        book = found.phrasebook
        return (
            tuple(w.lower() for w in book.yes_words),
            tuple(w.lower() for w in book.no_words),
        )

    async def _starts_a_process(self, tenant: Tenant, event: str) -> bool:
        """Whether an active version of the tenant has a trigger on this kind of event: then a
        rule of the tenant's own takes the message, and the conversation stays out."""
        async with self._work.transaction(tenant):
            for process in await self._processes.list(tenant):
                if process.active_version is None:
                    continue
                version = await self._versions.get(tenant, f"{process.id}@{process.active_version}")
                if version is not None and any(t.event == event for t in version.triggers):
                    return True
        return False


def _key(*parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"taktus:conversation:{digest}"
