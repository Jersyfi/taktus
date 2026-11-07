"""An assistant served in a rollout channel (UC-12.1, ADR-0261).

A message a placed person wrote in a rollout channel was kept by the intake as an event of
status `assistant`, never as a command, and the outbox entry `intake.assistant` names it and
the agent the channel serves. The automation role hands each entry here.

- **The assistant's own process runs, as the person.** The agent's flow is called as the
  person who wrote (ADR-0163 §3): the profile their roles resolve to, `agent.called` recorded,
  and the run acting as them. The call's plan names the call, never the message; the message is
  an input. The flow's version must declare the input `message`; the reply address is given as
  `reply_address` and `reply_thread` where it declares them; a version that requires any other
  input is no assistant's process.
- **Once per message.** The run's identifier is derived from the tenant, the flow and the
  event, so that a second pass, a restart or a second leader starts nothing twice.
- **The agent's grants cap the person's credential.** A flow that uses a tool action the
  profile does not grant is refused before it starts (`composition/agents.py`); a step on behalf
  of the person reads with their own credential, and without one gets nothing (ADR-0264).
- **The answer is the process's.** A step of the flow replies at the address it was given,
  under the frame of an outward message (ADR-0142). Only a refusal is said here, in one
  sentence: the assistant is switched off, none of the person's roles may use it, or it would
  need more than it may do. The refusal is recorded as `agent.refused`, its reason the outcome.

This is wiring: serving a message crosses the command, catalogue, process and run components.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import structlog

from taktus.components.catalog.domain.model import AgentError
from taktus.components.command.domain.model import IntakeEvent
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.run.domain.model import Run, RunError, RunExists
from taktus.composition.agents import SharedAgents
from taktus.composition.reactions import run_id_of
from taktus.ports.connector import ChannelReplies, IntakeReplyTo
from taktus.ports.identity import IdentityResolver
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs, ReplyTo

MESSAGE = "message"
REPLY_ADDRESS = "reply_address"
REPLY_THREAD = "reply_thread"
ASSISTANT_INPUTS = (MESSAGE, REPLY_ADDRESS, REPLY_THREAD)
"""The inputs a rollout run is given, as far as the flow's version declares them."""

REFUSED = "agent.refused"
NOT_AN_ASSISTANT = "not_an_assistant"

SWITCHED_OFF = "This assistant is switched off."
NO_ROLE = "None of your roles may use this assistant."
CANNOT = "This assistant cannot answer here: it would need more than it may do."
SAID = {"unknown": SWITCHED_OFF, "no_flow": SWITCHED_OFF, "no_profile": NO_ROLE}
"""What the person is told when the call is refused, by the refusal's reason; any other
reason is told `CANNOT`."""

log = structlog.get_logger("taktusd")


def inputs_of(version: ProcessVersion, kept: IntakeEvent) -> dict[str, Any]:
    """The inputs the flow's version is given for a message, or `AgentError` with the reason
    `not_an_assistant` for a version no message can run."""
    declared = version.inputs
    if MESSAGE not in declared:
        raise AgentError(
            NOT_AN_ASSISTANT,
            f"{version.ref} declares no input {MESSAGE!r}, which a rollout channel's message is",
        )
    other = sorted(n for n, d in declared.items() if d.required and n not in ASSISTANT_INPUTS)
    if other:
        raise AgentError(
            NOT_AN_ASSISTANT,
            f"{version.ref} requires {', '.join(other)}, which no message in a rollout channel "
            "gives",
        )
    given: dict[str, Any] = {
        MESSAGE: kept.intent,
        REPLY_ADDRESS: kept.reply_address,
        REPLY_THREAD: kept.reply_thread,
    }
    return {name: value for name, value in given.items() if name in declared and value is not None}


def refusal_key(event_id: str) -> str:
    """The idempotency key of the refusal said for one message: a second pass says it once."""
    return re.sub(r"[^A-Za-z0-9_.:-]", "-", f"taktus:assistant:{event_id}:refused")[:128]


class Assistants:
    """What the automation role hands a message in a rollout channel to."""

    def __init__(
        self,
        *,
        agents: SharedAgents,
        identities: IdentityResolver,
        runs: Repository[Run],
        ledger: Ledger,
        work: UnitOfWork,
        replies: ChannelReplies | None = None,
    ) -> None:
        self._agents = agents
        self._identities = identities
        self._runs = runs
        self._ledger = ledger
        self._work = work
        self._replies = replies

    async def serve(self, tenant: Tenant, kept: IntakeEvent, agent: str) -> list[str]:
        """The run the message started, by identifier; none when it started one before, when
        its sender is not placed any more, or when the call was refused."""
        placed = await self._identities.resolve(kept.channel, kept.sender_account, tenant=tenant)
        if placed is None:
            log.warning("a message in a rollout channel starts nothing: its sender is not placed")
            return []
        try:
            core, version = await self._agents.flow(tenant, agent)
            inputs = inputs_of(version, kept)
        except AgentError as error:
            await self._refused(tenant, kept, agent, placed.identity, error.reason, str(error))
            return []
        run_id = run_id_of(tenant, core.flow, kept.id)
        async with self._work.transaction(tenant):
            if await self._runs.get(tenant, run_id) is not None:
                return []  # started by an earlier pass
        trigger: Mapping[str, Any] = {
            "kind": "rollout",
            "agent": agent,
            "process": core.flow,
            "event": kept.event,
            "event_id": kept.id,
        }
        try:
            run = await self._agents.call(
                tenant,
                agent,
                identity=placed.identity,
                inputs=inputs,
                channel=kept.channel,
                reply_to=ReplyTo(
                    channel=kept.reply_channel, address=kept.reply_address, thread=kept.reply_thread
                ),
                run_id=run_id,
                trigger=trigger,
            )
        except RunExists:
            return []
        except AgentError as error:
            await self._refused(tenant, kept, agent, placed.identity, error.reason, str(error))
            return []
        except RunError as error:
            await self._refused(tenant, kept, agent, placed.identity, "refused", str(error))
            return []
        log.info("a message in a rollout channel started its assistant", tenant=tenant, run=run.id)
        return [run.id]

    async def _refused(
        self,
        tenant: Tenant,
        kept: IntakeEvent,
        agent: str,
        identity: str,
        reason: str,
        detail: str,
    ) -> None:
        log.info(
            "an assistant was refused", tenant=tenant, agent=agent, reason=reason, detail=detail
        )
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=REFUSED,
                    refs=LedgerRefs(tenant=tenant, agent_id=agent, actor=identity),
                    outcome=reason,
                ),
            )
        if self._replies is not None:
            to = IntakeReplyTo(
                channel=kept.reply_channel, address=kept.reply_address, thread=kept.reply_thread
            )
            await self._replies.reply(
                tenant, to, SAID.get(reason, CANNOT), key=refusal_key(kept.id)
            )
