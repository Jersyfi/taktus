"""A process changed in dialogue in the owner's conversation (UC-4.15, ADR-0091 §6).

The owner-facing channel (ADR-0045) reads four acts, by the words of its phrasebook:

- **a change** — `change process <process>: <words>` — starts S-07 for the owner, which works out
  the proposal; the answer names the run and links the process's page;
- **a rehearsal** — `rehearse <proposal>` — rehearses the proposal; it acts on nothing outside,
  so it needs no confirmation;
- **a commissioning** — `commission <proposal>` — and **a rollback** — `roll back
  <process>@<version>` — are read back first, and take effect only on the same person's `yes` in
  the same thread (ADR-0008). A `no` drops them. Until then nothing changes.

A proposal held to the process's evaluation cases (ADR-0134 §4) is read back with its verdict:
the cases, both scores and the tolerance. While its cases run, or where the verdict is a
regression or a case without a score, the verdict is said instead of a reading, with the page:
a commissioning against the verdict needs the person's reason, which the page takes (ADR-0134
§9). A phrasebook without the verdict's sentences reads back as before.

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
from typing import Protocol

from taktus.components.process.application.service.proposals import ProposalError, Proposals
from taktus.components.process.domain.model import InvalidProcess, Proposal
from taktus.components.process.domain.model.evaluation import (
    Evaluation,
    EvaluationState,
    Side,
    Verdict,
)
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
HELD = "held"
"""A commissioning its proposal's evaluation holds: the verdict was said, nothing read back."""
CHANGE_KINDS = ("commission", "rollback")
"""The acts read back here; a take-over waits in the same thread under another handler's kinds
(`composition/takeover_in_channel.py`)."""


class EvaluationsRead(Protocol):
    async def get(self, tenant: Tenant, process_id: str, evaluation_id: str) -> Evaluation: ...


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
        evaluations: EvaluationsRead | None = None,
    ) -> None:
        """`evaluations` reads a proposal's evaluation on the process's cases; None: no
        verdict is read back."""
        self._evaluations = evaluations
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
        if (
            waiting is not None
            and waiting.kind in CHANGE_KINDS
            and waiting.state == "awaiting"
            and waiting.by == identity
        ):
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
                verdict, readable = await self._verdict(tenant, proposal, book)
                if not readable:
                    said = verdict + _page(found, proposal.process_id, book)
                    return await self._say(found, said, thread, event, HELD)
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
                if verdict:
                    read = f"{read} {verdict}"
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
                read = _filled(
                    book.rollback_read, process=asked.target, version=asked.version or ""
                )
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
        process, version = waiting.process or "", waiting.version or ""
        async with self._work.transaction(tenant):
            await self._pending.put(
                tenant, waiting.model_copy(update={"state": "done" if confirmed else "dropped"})
            )
        if not confirmed:
            return await self._say(found, book.reread, thread, event, REFUSED)
        try:
            if waiting.kind == "commission" and waiting.proposal is not None:
                made = await self._acts.commission(tenant, process, waiting.proposal, waiting.by)
                said = _filled(book.commissioned, process=process, version=made.version)
            else:
                made = await self._acts.rollback(tenant, process, version, waiting.by)
                said = _filled(book.rolled_back, process=process, version=version, new=made.version)
        except (ProposalError, InvalidProcess):
            return await self._say(found, book.act_refused, thread, event, REFUSED)
        return await self._say(found, said + _page(found, process, book), thread, event, CHANGED)

    async def _verdict(
        self, tenant: Tenant, proposal: Proposal, book: Phrasebook
    ) -> tuple[str, bool]:
        """The sentence that names the proposal's verdict on the process's cases, and whether
        the commissioning may be read back: only a verdict that passed lets it be, or no
        evaluation at all. Empty, and readable, where nothing is held or the phrasebook names
        no verdict."""
        if (
            self._evaluations is None
            or proposal.evaluation is None
            or book.evaluation_passed is None
        ):
            return "", True
        try:
            evaluation = await self._evaluations.get(
                tenant, proposal.process_id, proposal.evaluation
            )
        except ProposalError:
            return "", True
        cases = str(len(evaluation.cases))
        if evaluation.state is not EvaluationState.SCORED:
            return _filled(book.evaluation_running, cases=cases), False
        active, proposed = evaluation.side(Side.ACTIVE), evaluation.side(Side.PROPOSED)
        figures = {
            "cases": cases,
            "active": _figure(None if active is None else active.score),
            "proposed": _figure(None if proposed is None else proposed.score),
            "tolerance": _figure(evaluation.tolerance),
        }
        if evaluation.verdict is Verdict.PASSED:
            return _filled(book.evaluation_passed, **figures), True
        if evaluation.verdict is Verdict.REGRESSED:
            return _filled(book.evaluation_regressed, **figures), False
        unscored = sum(s.unscored for s in evaluation.sides)
        return _filled(book.evaluation_incomplete, cases=cases, unscored=str(unscored)), False

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


def _figure(value: float | None) -> str:
    """A score or a tolerance as it is said: two decimals, or a dash where there is none."""
    return "—" if value is None else f"{value:.2f}"


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
