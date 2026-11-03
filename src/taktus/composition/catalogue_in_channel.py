"""What a person may ask Taktus for, asked and started in the owner's conversation (UC-1.13,
ADR-0159 §3).

The owner-facing channel (ADR-0045) reads two requests, by the words of its phrasebook:

- **the catalogue** — `what can I ask for` standing alone — lists the processes the person may
  start, each with what to write to start it, or the inputs it needs where a reply cannot give
  them. It acts on nothing, so it needs no confirmation;
- **a start** — `start <process>` — is read back first, and the process starts only on the same
  person's `yes` in the same thread (ADR-0008). A `no` drops it. The start is the one start
  command every channel issues (`command/domain/service/start.py`), on the conversation's
  channel, acting as the person who confirmed it.

Only in the owner's conversation, only for the owner or someone the owner named (UC-1.7), and only
for a process the person may see, by the predicate every level is read through. Anything else is
answered with the same sentence, and the list in the web app says why. Who asked is kept only to
know who may confirm: no measure is computed from it (principle 14). This is wiring, because a
start crosses the reporting, process, command and run components.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from taktus.adapters.driving.rest.wiring import StartRefused
from taktus.components.reporting.domain.model import OwnerChannel, PendingAct
from taktus.components.reporting.domain.service import reading as rules
from taktus.components.reporting.ports import Deliveries, SecretValues, Sent
from taktus.composition.agent_surface import AgentSurface
from taktus.ports.clock import Clock
from taktus.ports.identity import IdentityResolver
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Capability

LISTED = "listed"
ASKED = "read_back"
STARTED = "started"
REFUSED = "refused"
KIND = "start"


@dataclass(frozen=True)
class Starting:
    outcome: str
    replied: bool


class CatalogueInChannel:
    def __init__(
        self,
        *,
        channels: Repository[OwnerChannel],
        pending: Repository[PendingAct],
        work: UnitOfWork,
        surface: AgentSurface,
        identities: IdentityResolver,
        deliveries: Deliveries,
        secrets: SecretValues,
        clock: Clock,
    ) -> None:
        self._channels = channels
        self._pending = pending
        self._work = work
        self._surface = surface
        self._identities = identities
        self._deliveries = deliveries
        self._secrets = secrets
        self._clock = clock

    async def take(
        self,
        tenant: Tenant,
        channel: Capability,
        address: str,
        thread: str | None,
        identity: str | None,
        roles: tuple[str, ...],
        text: str,
        event: str,
    ) -> Starting | None:
        """The answer, or None when the message asks for neither the catalogue nor a start in
        the owner's conversation: it goes on as any other message would."""
        if identity is None:
            return None
        async with self._work.transaction(tenant):
            found = await self._channels.get(tenant, tenant)
            waiting = await self._pending.get(tenant, _key(address, thread))
        if found is None or channel != found.channel or address != found.address:
            return None
        book = found.phrasebook
        if book.catalogue_words is None:
            return None
        if (
            waiting is not None
            and waiting.kind == KIND
            and waiting.state == "awaiting"
            and waiting.by == identity
        ):
            confirmed = rules.confirmation(text, book)
            if confirmed is not None:
                return await self._confirmed(found, waiting, confirmed, thread, event)
        asked = rules.catalogue_request(text, book)
        if asked is None:
            return None
        who = await self._identities.identity(tenant, identity)
        if who is None or not found.may_answer(identity):
            return await self._say(found, book.start_not_done, thread, event, REFUSED)
        listed = await self._surface.catalogue(who, agent_may_start=False)
        if asked.kind == "list":
            lines = [book.catalogue_heading or ""]
            for entry in listed.entries:
                if entry.start.chat is not None:
                    line = _filled(book.catalogue_line, name=entry.name, start=entry.start.chat)
                else:
                    needed = ", ".join(i.name for i in entry.needs if i.required)
                    line = _filled(book.catalogue_needs, name=entry.name, inputs=needed)
                lines.append(f"• {line}")
            return await self._say(found, _with_link(found, lines), thread, event, LISTED)
        chosen = next((e for e in listed.entries if e.process == asked.process), None)
        if chosen is None or chosen.start.chat is None:
            return await self._say(found, book.start_not_done, thread, event, REFUSED)
        act = PendingAct(
            id=_key(address, thread),
            tenant=tenant,
            kind=KIND,
            process=chosen.process,
            version=chosen.version.split("@", 1)[1],
            by=identity,
            asked_at=self._clock.now(),
        )
        async with self._work.transaction(tenant):
            await self._pending.put(tenant, act)
        read = _filled(book.start_read, process=chosen.process, name=chosen.name)
        confirm = book.confirm.format(yes=book.yes_words[0], no=book.no_words[0])
        return await self._say(found, f"{read} {confirm}", thread, event, ASKED)

    async def _confirmed(
        self,
        found: OwnerChannel,
        waiting: PendingAct,
        confirmed: bool,
        thread: str | None,
        event: str,
    ) -> Starting:
        book = found.phrasebook
        tenant = found.tenant
        async with self._work.transaction(tenant):
            await self._pending.put(
                tenant, waiting.model_copy(update={"state": "done" if confirmed else "dropped"})
            )
        if not confirmed:
            return await self._say(found, book.reread, thread, event, REFUSED)
        who = await self._identities.identity(tenant, waiting.by)
        process = waiting.process or ""
        if who is None:
            return await self._say(found, book.start_not_done, thread, event, REFUSED)
        try:
            run = await self._surface.start(
                who, process, {}, channel=found.channel, address=found.address
            )
        except StartRefused:
            return await self._say(found, book.start_not_done, thread, event, REFUSED)
        said = _filled(book.started, process=process, run=run.id)
        if found.view_base is not None and book.live is not None:
            said += f"\n{book.live}: {found.view_base.rstrip('/')}/app/#/runs/{run.id}"
        return await self._say(found, said, thread, event, STARTED)

    async def _say(
        self, found: OwnerChannel, said: str | None, thread: str | None, event: str, outcome: str
    ) -> Starting:
        if said and self._secrets.carried_by(said):
            said, outcome = found.phrasebook.start_not_done, REFUSED
        sent = await self._deliveries.say(
            found.tenant,
            found.channel,
            found.address,
            said or "",
            thread=thread,
            key=_idempotency(event),
        )
        return Starting(outcome=outcome, replied=isinstance(sent, Sent))


def _filled(template: str | None, **values: str) -> str:
    return (template or "").format(**values)


def _with_link(found: OwnerChannel, lines: list[str]) -> str:
    """The lines, and the link to the list in the web app where a view base is known."""
    live = found.phrasebook.live
    if found.view_base is not None and live is not None:
        lines = [*lines, "", f"{live}: {found.view_base.rstrip('/')}/app/#/catalogue"]
    return "\n".join(lines)


def _key(address: str, thread: str | None) -> str:
    return f"{address}:{thread or '-'}"


def _idempotency(event: str) -> str:
    """The idempotency key of the answer to one message: a redelivery answers once."""
    raw = f"taktus:catalogue:{event}"
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]", "-", raw)
    if len(cleaned) <= 128:
        return cleaned
    return "taktus:catalogue:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]
