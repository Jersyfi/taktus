"""A process changed in dialogue in the owner's conversation (UC-4.15, ADR-0091 §6).

The owner-facing channel (ADR-0045) reads four acts, by the words of its phrasebook:

- **a change** — `change process <process>: <words>` — starts S-07 for the owner, which works out
  the proposal; the answer names the run and links the process's page;
- **a rehearsal** — `rehearse <proposal>` — rehearses the proposal; it acts on nothing outside,
  so it needs no confirmation;
- **a commissioning** — `commission <proposal>` — and **a rollback** — `roll back
  <process>@<version>` — are read back first, and take effect only on the same person's `yes` in
  the same thread (ADR-0008). A `no` drops them. Until then nothing changes.

Only in the owner's conversation, and only for the owner or someone the owner named (UC-1.7);
anyone else is told the act cannot be done. Whatever is refused — a proposal not yet rehearsed, a
version taken — is answered with the same sentence, and the process's page in the web app says
why. This is wiring, because each act crosses the reporting and process components and the
composition root's acts (`composition/proposals.py`).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from taktus.components.process.application.service.proposals import ProposalError, Proposals
from taktus.components.process.domain.model import InvalidProcess
from taktus.components.reporting.domain.model import OwnerChannel, PendingAct, Phrasebook
from taktus.components.reporting.domain.service import reading as rules
from taktus.components.reporting.ports import Deliveries, SecretValues, Sent
from taktus.composition.proposals import ProposalActs
from taktus.ports.clock import Clock
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Capability

CHANGED = "changed"
ASKED = "read_back"
REFUSED = "refused"


@dataclass(frozen=True)
class Changing:
    outcome: str
    replied: bool


class ChangeInChannel:
    def __init__(
        self,
        *,
        channels: Repository[OwnerChannel],
        pending: Repository[PendingAct],
        work: UnitOfWork,
        acts: ProposalActs,
        proposals: Proposals,
        deliveries: Deliveries,
        secrets: SecretValues,
        clock: Clock,
    ) -> None:
        self._secrets = secrets
        self._channels = channels
        self._pending = pending
        self._work = work
        self._acts = acts
        self._proposals = proposals
        self._deliveries = deliveries
        self._clock = clock

    async def take(
        self,
        tenant: Tenant,
        channel: Capability,
        address: str,
        thread: str | None,
        identity: str | None,
        text: str,
        event: str,
    ) -> Changing | None:
        """The answer, or None when the message is no act of a change in dialogue in the owner's
        conversation: it goes on as any other message would."""
        if identity is None:
            return None
        async with self._work.transaction(tenant):
            found = await self._channels.get(tenant, tenant)
            waiting = await self._pending.get(tenant, _key(address, thread))
        if found is None or channel != found.channel or address != found.address:
            return None
        book = found.phrasebook
        if book.change_words is None:
            return None
        if waiting is not None and waiting.state == "awaiting" and waiting.by == identity:
            confirmed = rules.confirmation(text, book)
            if confirmed is not None:
                return await self._confirmed(found, waiting, confirmed, thread, event)
        asked = rules.act(text, book)
        if asked is None:
            return None
        if not found.may_answer(identity):
            return await self._say(found, book.act_refused, thread, event, REFUSED)
        try:
            if asked.kind == "change":
                run = await self._acts.ask(tenant, asked.target, asked.words or "", identity)
                said = _filled(book.change_started, process=asked.target, run=run.id)
                said += _page(found, asked.target, book)
                return await self._say(found, said, thread, event, CHANGED)
            if asked.kind == "rehearse":
                proposal = await self._proposals.find(tenant, asked.target)
                _, run = await self._acts.rehearse(
                    tenant, proposal.process_id, proposal.id, identity
                )
                said = _filled(book.rehearsing, proposal=proposal.id, run=run.id)
                return await self._say(found, said, thread, event, CHANGED)
            if asked.kind == "commission":
                proposal = await self._proposals.find(tenant, asked.target)
                act = PendingAct(
                    id=_key(address, thread),
                    tenant=tenant,
                    kind="commission",
                    process=proposal.process_id,
                    proposal=proposal.id,
                    version=proposal.version,
                    by=identity,
                    asked_at=self._clock.now(),
                )
                read = _filled(
                    book.commission_read,
                    proposal=proposal.id,
                    process=proposal.process_id,
                    version=proposal.version,
                )
            else:
                act = PendingAct(
                    id=_key(address, thread),
                    tenant=tenant,
                    kind="rollback",
                    process=asked.target,
                    version=asked.version or "",
                    by=identity,
                    asked_at=self._clock.now(),
                )
                read = _filled(book.rollback_read, process=asked.target, version=act.version)
        except (ProposalError, InvalidProcess):
            return await self._say(found, book.act_refused, thread, event, REFUSED)
        async with self._work.transaction(tenant):
            await self._pending.put(tenant, act)
        confirm = book.confirm.format(yes=book.yes_words[0], no=book.no_words[0])
        return await self._say(found, f"{read} {confirm}", thread, event, ASKED)

    async def _confirmed(
        self,
        found: OwnerChannel,
        waiting: PendingAct,
        confirmed: bool,
        thread: str | None,
        event: str,
    ) -> Changing:
        book = found.phrasebook
        tenant = found.tenant
        async with self._work.transaction(tenant):
            await self._pending.put(
                tenant, waiting.model_copy(update={"state": "done" if confirmed else "dropped"})
            )
        if not confirmed:
            return await self._say(found, book.reread, thread, event, REFUSED)
        try:
            if waiting.kind == "commission" and waiting.proposal is not None:
                version = await self._acts.commission(
                    tenant, waiting.process, waiting.proposal, waiting.by
                )
                said = _filled(book.commissioned, process=waiting.process, version=version.version)
            else:
                version = await self._acts.rollback(
                    tenant, waiting.process, waiting.version, waiting.by
                )
                said = _filled(
                    book.rolled_back,
                    process=waiting.process,
                    version=waiting.version,
                    new=version.version,
                )
        except (ProposalError, InvalidProcess):
            return await self._say(found, book.act_refused, thread, event, REFUSED)
        return await self._say(
            found, said + _page(found, waiting.process, book), thread, event, CHANGED
        )

    async def _say(
        self, found: OwnerChannel, said: str | None, thread: str | None, event: str, outcome: str
    ) -> Changing:
        if said and self._secrets.carried_by(said):
            said, outcome = found.phrasebook.act_refused, REFUSED
        sent = await self._deliveries.say(
            found.tenant,
            found.channel,
            found.address,
            said or "",
            thread=thread,
            key=_idempotency(event),
        )
        return Changing(outcome=outcome, replied=isinstance(sent, Sent))


def _filled(template: str | None, **values: str) -> str:
    return (template or "").format(**values)


def _page(found: OwnerChannel, process: str, book: Phrasebook) -> str:
    """The link to the process's page of changes in the web app, where a view base is known."""
    if found.view_base is None or book.live is None:
        return ""
    return f"\n{book.live}: {found.view_base.rstrip('/')}/app/#/changes/{process}"


def _key(address: str, thread: str | None) -> str:
    return f"{address}:{thread or '-'}"


def _idempotency(event: str) -> str:
    """The idempotency key of the answer to one message: a redelivery answers once."""
    raw = f"taktus:changed:{event}"
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]", "-", raw)
    if len(cleaned) <= 128:
        return cleaned
    return "taktus:changed:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]
