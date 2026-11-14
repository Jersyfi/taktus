"""Use case: a person's conversation with Taktus, and the acts read back in it (ADR-0325,
UC-1.14; ADR-0324 for the agent's read-back).

`said` keeps what the person said; `thinking` names the run forming the answer; `answered`
keeps Taktus's answer and, where it proposes an act, that act read back and waiting. `propose`
keeps an act read back without a turn, as the MCP surface asks it. `settle` records the person's
yes or no and what came of it. Nothing here does an act: that is the composition's
(`composition/building.py`), through the same services every surface uses.

Every settlement is a ledger entry with the person as actor; no measure is computed from them
per person (principle 14).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from taktus.components.command.domain.model.conversation import (
    ActState,
    Conversation,
    Exchange,
    ProposedAct,
    conversation_id,
    validated,
)
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

SAID = "conversation.said"
ANSWERED = "conversation.answered"
CONFIRMED = "conversation.act_confirmed"
DECLINED = "conversation.act_declined"
KEPT_TURNS = 200
"""The turns a conversation keeps; older ones leave it, the ledger keeps that they happened."""


class ConversationError(Exception):
    pass


class Conversations:
    def __init__(
        self,
        conversations: Repository[Conversation],
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
        ids: Identifiers,
    ) -> None:
        self._conversations = conversations
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._ids = ids

    async def of(self, tenant: Tenant, participant: str) -> Conversation:
        """The person's conversation; an empty one the first time, kept only once used."""
        async with self._work.transaction(tenant):
            found = await self._conversations.get(tenant, conversation_id(tenant, participant))
        return found or Conversation(
            id=conversation_id(tenant, participant),
            tenant=tenant,
            participant=participant,
            opened_at=self._clock.now(),
        )

    async def get(self, tenant: Tenant, conversation: str) -> Conversation:
        async with self._work.transaction(tenant):
            found = await self._conversations.get(tenant, conversation)
        if found is None:
            raise ConversationError(f"no conversation {conversation!r}")
        return found

    async def said(
        self,
        tenant: Tenant,
        participant: str,
        channel: str,
        text: str,
        reply: Mapping[str, str] | None = None,
    ) -> Conversation:
        """What the person said, kept as their turn. A turn while Taktus still forms the answer
        to the last one is refused: one answer at a time."""
        current = await self.of(tenant, participant)
        if current.thinking is not None:
            raise ConversationError("Taktus is still answering your last message")
        turn = Exchange(at=self._clock.now(), channel=channel, speaker="person", text=text)
        updated = current.model_copy(
            update={
                "turns": (*current.turns, turn)[-KEPT_TURNS:],
                "reply": None if reply is None else dict(reply),
            }
        )
        await self._put(updated, SAID, participant)
        return updated

    async def thinking(self, tenant: Tenant, conversation: str, run: str | None) -> Conversation:
        """The run forming the answer, or None once there is none."""
        current = await self.get(tenant, conversation)
        updated = current.model_copy(update={"thinking": run})
        async with self._work.transaction(tenant):
            await self._conversations.put(tenant, updated)
        return updated

    async def answered(
        self,
        tenant: Tenant,
        conversation: str,
        text: str,
        *,
        run: str | None,
        act: tuple[str, Mapping[str, Any], str] | None = None,
    ) -> tuple[Exchange, ProposedAct | None]:
        """Taktus's answer kept as its turn. `act` — name, arguments, read-back — is checked by
        rule against the closed list once more and kept waiting for the person's yes."""
        current = await self.get(tenant, conversation)
        channel = (current.reply or {}).get("channel") or (
            current.turns[-1].channel if current.turns else "channel.web"
        )
        proposed = None
        if act is not None:
            name, arguments, read_back = act
            proposed = ProposedAct(
                id=self._ids.new("act"),
                act=name,
                arguments=validated(name, arguments),
                read_back=read_back,
                channel=channel,
                asked_at=self._clock.now(),
            )
        turn = Exchange(
            at=self._clock.now(),
            channel=channel,
            speaker="taktus",
            text=text,
            act=None if proposed is None else proposed.id,
            run=run,
        )
        updated = current.model_copy(
            update={
                "turns": (*current.turns, turn)[-KEPT_TURNS:],
                "acts": current.acts if proposed is None else (*current.acts, proposed),
                "thinking": None,
            }
        )
        await self._put(updated, ANSWERED, current.participant, run=run)
        return turn, proposed

    async def propose(
        self,
        tenant: Tenant,
        participant: str,
        channel: str,
        act: str,
        arguments: Mapping[str, Any],
        read_back: str,
    ) -> ProposedAct:
        """An act read back without a turn, waiting for the person's yes (ADR-0324 §3)."""
        current = await self.of(tenant, participant)
        proposed = ProposedAct(
            id=self._ids.new("act"),
            act=act,
            arguments=validated(act, arguments),
            read_back=read_back,
            channel=channel,
            asked_at=self._clock.now(),
        )
        updated = current.model_copy(update={"acts": (*current.acts, proposed)})
        async with self._work.transaction(tenant):
            await self._conversations.put(tenant, updated)
        return proposed

    async def waiting(self, tenant: Tenant, participant: str, act_id: str) -> ProposedAct:
        """The person's act still waiting for their yes; `ConversationError` otherwise."""
        found = (await self.of(tenant, participant)).act(act_id)
        if found is None:
            raise ConversationError(f"no act {act_id!r} of yours")
        if found.state is not ActState.WAITING:
            raise ConversationError(f"the act {act_id} is {found.state} already")
        return found

    async def settle(
        self,
        tenant: Tenant,
        participant: str,
        act_id: str,
        state: ActState,
        outcome: str,
        links: Mapping[str, str] | None = None,
        *,
        say: bool = True,
    ) -> ProposedAct:
        """The act settled: done, declined or failed, with what came of it. With `say`, the
        outcome is Taktus's next turn too."""
        current = await self.of(tenant, participant)
        found = current.act(act_id)
        if found is None:
            raise ConversationError(f"no act {act_id!r} of yours")
        now = self._clock.now()
        settled = found.model_copy(
            update={
                "state": state,
                "outcome": outcome[:2000],
                "links": dict(links or {}),
                "settled_at": now,
            }
        )
        turns = current.turns
        if say:
            turns = (
                *turns,
                Exchange(at=now, channel=found.channel, speaker="taktus", text=outcome[:8000]),
            )[-KEPT_TURNS:]
        updated = current.model_copy(
            update={
                "acts": tuple(settled if a.id == act_id else a for a in current.acts),
                "turns": turns,
            }
        )
        kind = DECLINED if state is ActState.DECLINED else CONFIRMED
        await self._put(updated, kind, participant, outcome=str(state))
        return settled

    async def _put(
        self,
        conversation: Conversation,
        kind: str,
        actor: str,
        *,
        run: str | None = None,
        outcome: str | None = None,
    ) -> None:
        async with self._work.transaction(conversation.tenant):
            await self._conversations.put(conversation.tenant, conversation)
            await self._ledger.record(
                conversation.tenant,
                Fact(
                    kind=kind,
                    refs=LedgerRefs(tenant=conversation.tenant, run_id=run, actor=actor),
                    outcome=outcome,
                ),
            )
