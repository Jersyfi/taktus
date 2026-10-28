"""Where a run or a process spends, asked in the owner's conversation (#449, ADR-0148).

The owner-facing channel (ADR-0045) reads three requests, by the words of its phrasebook:

- `spend <run>` — the run, step by step: money at its own price table, Takte at its own
  weighting table, tokens in and out, turns;
- `spend <run> <other run>` — both runs side by side, step by step, and whether each step
  produced the same result;
- `spend process <process>` — the process over the last thirty days, step by step.

Each answer ends with the link to the same view in the web app, which draws it as a chart. What
cannot be priced is said, never shown as nothing. Only in the owner's conversation, only for the
owner or someone the owner named, and only on runs the person may see, by the predicate every
level is read through; anything else is answered with the sentence for what cannot be shown. An
answer that would carry a secret value the instance holds is not sent. A request acts on
nothing and writes nothing: it is a read, as `GET /runs/{id}/spend` is. No figure names a
person (principle 14). This is wiring, because it crosses the reporting and accounting
components.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import quote

from taktus.components.accounting.application.service import (
    CompareRuns,
    SpendHandler,
    SpendOfProcess,
    SpendOfRun,
    StepSpend,
)
from taktus.components.accounting.application.service.spend import tokens_in, tokens_out
from taktus.components.reporting.domain.model import (
    OwnerChannel,
    Phrasebook,
    ProcessRef,
    Reader,
    RunRef,
)
from taktus.components.reporting.domain.service import visibility
from taktus.components.reporting.ports import Deliveries, SecretValues, Sent
from taktus.components.run.domain.model import Run
from taktus.ports.clock import Clock
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Capability

SHOWN = "shown"
NOT_SHOWN = "not_shown"
DAYS = 30
"""The window a process's spend is read over in the channel; the web app chooses another."""
_AROUND = " \t\r\n.,;:!?\"'„“”«»()"


@dataclass(frozen=True)
class Spent:
    outcome: str
    replied: bool


@dataclass(frozen=True)
class Asked:
    kind: str
    """`run`, `against` or `process`."""
    subject: str
    other: str | None = None


def asked(text: str, book: Phrasebook) -> Asked | None:
    """A message that asks for spend: one of the words, then one run, two runs, or one process.
    The words are matched as the channel's other words are; identifiers are taken as written.
    None for anything else, and for a phrasebook that reads no such request."""
    if book.spend_words is None or book.spend_process_words is None:
        return None
    tokens = text.strip(_AROUND).split()
    folded = [t.casefold() for t in tokens]
    for word in sorted(book.spend_process_words, key=len, reverse=True):
        size = len(word.split())
        if " ".join(folded[:size]) == word and len(tokens) == size + 1:
            return Asked(kind="process", subject=tokens[size])
    for word in sorted(book.spend_words, key=len, reverse=True):
        size = len(word.split())
        if " ".join(folded[:size]) != word:
            continue
        rest = tokens[size:]
        if len(rest) == 1:
            return Asked(kind="run", subject=rest[0])
        if len(rest) == 2:
            return Asked(kind="against", subject=rest[0], other=rest[1])
    return None


class SpendInChannel:
    def __init__(
        self,
        *,
        channels: Repository[OwnerChannel],
        runs: Repository[Run],
        work: UnitOfWork,
        spend: SpendHandler,
        deliveries: Deliveries,
        secrets: SecretValues,
        clock: Clock,
    ) -> None:
        self._channels = channels
        self._runs = runs
        self._work = work
        self._spend = spend
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
    ) -> Spent | None:
        """The answer, or None when the message asks for no spend in the owner's conversation:
        it goes on as any other message would."""
        if identity is None:
            return None
        async with self._work.transaction(tenant):
            found = await self._channels.get(tenant, tenant)
        if found is None or channel != found.channel or address != found.address:
            return None
        book = found.phrasebook
        request = asked(text, book)
        if request is None or book.not_shown is None:
            return None
        said: str | None = None
        if found.may_answer(identity):
            reader = Reader(tenant=tenant, identity=identity, roles=roles)
            said = await self._said(found, reader, request)
        outcome = SHOWN
        if said is None or self._secrets.carried_by(said):
            said, outcome = book.not_shown, NOT_SHOWN
        sent = await self._deliveries.say(
            tenant, found.channel, found.address, said, thread=thread, key=_idempotency(event)
        )
        return Spent(outcome=outcome, replied=isinstance(sent, Sent))

    async def _said(self, found: OwnerChannel, reader: Reader, request: Asked) -> str | None:
        book = found.phrasebook
        tenant = reader.tenant
        if request.kind == "process":
            if not visibility.may_see_process(
                reader, ProcessRef(id=request.subject, tenant=tenant)
            ):
                return None
            until = self._clock.now()
            spent = await self._spend.of_process(
                SpendOfProcess(
                    request.subject, tenant, since=until - timedelta(days=DAYS), until=until
                )
            )
            if spent.runs == 0:
                return None
            currency = next(iter(spent.amounts), None) if len(spent.amounts) == 1 else None
            lines = [
                _filled(
                    book.spend_of_process,
                    process=request.subject,
                    days=str(DAYS),
                    runs=str(spent.runs),
                ),
                *(f"• {_line(book, step, currency)}" for step in spent.steps),
            ]
            route = f"spend/processes/{quote(request.subject, safe='')}"
            return _with_link(found, lines, route)
        for run_id in (request.subject, *(() if request.other is None else (request.other,))):
            if not await self._visible(reader, run_id):
                return None
        if request.kind == "run":
            spent_run = await self._spend.of_run(SpendOfRun(request.subject, tenant))
            lines = [
                _filled(book.spend_of_run, run=request.subject),
                *(f"• {_line(book, step, spent_run.currency)}" for step in spent_run.steps),
            ]
            route = f"spend/runs/{quote(request.subject, safe='')}"
            return _with_link(found, lines, route)
        other = request.other or ""
        compared = await self._spend.compare(CompareRuns(request.subject, other, tenant))
        before = {s.step_id: s for s in compared.left.steps}
        after = {s.step_id: s for s in compared.right.steps}
        lines = [_filled(book.spend_against, run=request.subject, other=other)]
        lines += [f"• {caveat}" for caveat in compared.comparable]
        for difference in compared.steps:
            result = "-"
            if difference.same_result is not None:
                result = (book.same_result if difference.same_result else book.other_result) or ""
            lines.append(
                "• "
                + _filled(
                    book.spend_compared,
                    step=difference.step_id,
                    left=_side(book, before.get(difference.step_id), compared.left.currency),
                    right=_side(book, after.get(difference.step_id), compared.right.currency),
                    result=result,
                )
            )
        route = f"spend/runs/{quote(request.subject, safe='')}/{quote(other, safe='')}"
        return _with_link(found, lines, route)

    async def _visible(self, reader: Reader, run_id: str) -> bool:
        async with self._work.transaction(reader.tenant):
            run = await self._runs.get(reader.tenant, run_id)
        if run is None:
            return False
        ref = RunRef(id=run.id, tenant=run.tenant, process_version=run.process_version)
        return visibility.may_see(reader, ref)


def _money(book: Phrasebook, step: StepSpend, currency: str | None) -> str:
    if step.amount is None or currency is None:
        return book.not_priced or ""
    return f"{step.amount:.4f} {currency.upper()}"


def _line(book: Phrasebook, step: StepSpend, currency: str | None) -> str:
    return _filled(
        book.spend_line,
        step=step.step_id,
        money=_money(book, step, currency),
        takte=book.not_priced or "" if step.takte is None else f"{step.takte:.3f}",
        tokens_in=str(tokens_in(step.meter)),
        tokens_out=str(tokens_out(step.meter)),
        turns=str(step.meter.turns),
    )


def _side(book: Phrasebook, step: StepSpend | None, currency: str | None) -> str:
    if step is None:
        return "-"
    return f"{_money(book, step, currency)}, {tokens_in(step.meter)}/{tokens_out(step.meter)}"


def _filled(template: str | None, **values: str) -> str:
    return "" if template is None else template.format(**values)


def _with_link(found: OwnerChannel, lines: list[str], route: str) -> str:
    """The lines, and the link to the same view in the web app where a view base is known."""
    live = found.phrasebook.live
    if found.view_base is not None and live is not None:
        lines = [*lines, "", f"{live}: {found.view_base.rstrip('/')}/app/#/{route}"]
    return "\n".join(lines)


def _idempotency(event: str) -> str:
    """The idempotency key of the answer to one message: a redelivery answers once."""
    raw = f"taktus:spend:{event}"
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]", "-", raw)
    if len(cleaned) <= 128:
        return cleaned
    return "taktus:spend:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]
