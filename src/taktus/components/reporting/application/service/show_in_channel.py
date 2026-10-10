"""Use case: a live representation is asked for in a channel that cannot draw it (UC-6.10
*beyond the web app*, ADR-0069).

The owner-facing channel (ADR-0045) is a chat: it shows text and links, never a moving
picture. A message there that asks for a run or a process — one of the phrasebook's words and
one identifier — is answered in the same conversation with the level's text equivalent, exactly
as the level hands it to the web app, and the link to the level live in the web app.

What the answer may carry is what its readers may see:

- **Only in the owner's conversation.** A message at another address of the channel is not
  this use case's: whoever reads there is unknown, and it goes on as any other message would.
- **Only for the owner, or someone the owner named.** They are the readers of that
  conversation the configuration knows. Anyone else is told that nothing of that name can be
  shown — the same sentence as for a run that does not exist.
- **Only what the asker may see**, by the one predicate every level is read through
  (`application/query/levels.py`). A run or a process they may not see is answered exactly as
  one that does not exist.
- **No secret value the instance holds.** An answer that would carry one is not sent; the same
  sentence is said instead.

A sender nobody could place is not answered here: the identity component offers them a link,
as for any other message. Nothing is stored and nothing is written to the ledger: showing a
level is a read, as `GET /levels/…` is.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from taktus.components.reporting.application.query.levels import LevelQueries
from taktus.components.reporting.domain.model import OwnerChannel, Reader
from taktus.components.reporting.domain.service import reading as rules
from taktus.components.reporting.domain.service.rendering import shown
from taktus.components.reporting.ports import Deliveries, SecretValues, Sent
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Capability

SHOWN = "shown"
NOT_SHOWN = "not_shown"


@dataclass(frozen=True)
class ShowInChannel:
    tenant: Tenant
    channel: Capability
    address: str
    thread: str | None
    identity: str | None
    """Who asked, as the identity component placed them; None for a sender it could not."""
    roles: tuple[str, ...]
    """The roles that identity holds now, for the predicate (ADR-0055 §5)."""
    text: str
    event: str
    """The channel's identifier of the message: the answer to it is said once."""


@dataclass(frozen=True)
class Shown:
    outcome: str
    """`shown`, or `not_shown` when nothing of that name could be shown to whoever asked."""
    replied: bool


class ShowInChannelHandler:
    def __init__(
        self,
        channels: Repository[OwnerChannel],
        work: UnitOfWork,
        levels: LevelQueries,
        deliveries: Deliveries,
        secrets: SecretValues,
    ) -> None:
        self._channels = channels
        self._work = work
        self._levels = levels
        self._deliveries = deliveries
        self._secrets = secrets

    async def execute(self, command: ShowInChannel) -> Shown | None:
        """The answer, or None when the message asks for no representation in the owner's
        conversation: it goes on as any other message would."""
        if command.identity is None:
            return None
        async with self._work.transaction(command.tenant):
            channel = await self._channels.get(command.tenant, command.tenant)
        if (
            channel is None
            or command.channel != channel.channel
            or command.address != channel.address
        ):
            return None
        book = channel.phrasebook
        asked = rules.representation(command.text, book)
        if asked is None or book.not_shown is None:
            return None
        said: str | None = None
        if channel.may_answer(command.identity):
            reader = Reader(tenant=command.tenant, identity=command.identity, roles=command.roles)
            level = (
                await self._levels.run(reader, asked.id)
                if asked.level == "run"
                else await self._levels.process(reader, asked.id, asked.version)
            )
            if level is not None:
                said = shown(level, channel)
        outcome = SHOWN
        if said is None or self._secrets.carried_by(said):
            said, outcome = book.not_shown, NOT_SHOWN
        sent = await self._deliveries.say(
            command.tenant,
            command.channel,
            command.address,
            said,
            thread=command.thread,
            key=_key(command.event),
        )
        return Shown(outcome=outcome, replied=isinstance(sent, Sent))


def _key(event: str) -> str:
    """The idempotency key of the answer to one message: a redelivery answers once."""
    raw = f"taktus:shown:{event}"
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]", "-", raw)
    if len(cleaned) <= 128:
        return cleaned
    return "taktus:shown:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]
