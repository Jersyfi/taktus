"""A running step taken over and its result handed back, in the owner's conversation (UC-4.19,
ADR-0128 §7).

The owner-facing channel (ADR-0045) reads three acts, by the words of its phrasebook:

- **a take-over** — `take over <run> <step>` — is read back first, and asked only on the same
  person's `yes` in the same thread (ADR-0008). The answer names the take-over identifier and
  links the run's page in the web app;
- **a question** — `show takeover <takeover>` — says where the take-over stands: asked and not
  yet served, refused, held with the state the step reached, handed back, or lapsed. It acts on
  nothing, so it needs no confirmation;
- **a hand-back** — `hand back <takeover>: <result>` — is read back with how the result was read,
  as JSON or as the text written, and handed back only on the same person's `yes`. A `no` drops
  it. Until then nothing changes;
- **a message to a running step** — `message <run> <step>: <text>` — is read back with its
  text, and asked only on the same person's `yes` (ADR-0156 §7). A refusal says the engine's
  reason: the step does not run, no runner holds it, or its worker takes no message.

Only in the owner's conversation, and only for the owner or someone the owner named (UC-1.7),
and only on a run the person may see, by the predicate every level is read through. Anything
else is answered with the same sentence as an act that cannot be done, and the run's page says
why. A result that carries a secret value the instance holds is not read back, kept or handed
back. A take-over asked here is kept under its identifier, so that its state is shown and its
result handed back from any thread of the conversation; one asked on another surface is handed
back there (ADR-0128 §3). Who asked is kept only to know who may confirm: no measure is ever
computed from it (principle 14). This is wiring, because each act crosses the reporting and run
components.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from taktus.components.reporting.domain.model import (
    OwnerChannel,
    PendingAct,
    Phrasebook,
    Reader,
    RunRef,
)
from taktus.components.reporting.domain.service import reading as rules
from taktus.components.reporting.domain.service import visibility
from taktus.components.reporting.ports import Deliveries, SecretValues, Sent
from taktus.components.run.application.service import HandBack, SteerStep, TakeOver
from taktus.components.run.domain.model import (
    Run,
    RunError,
    RunState,
    StepRun,
    TakeoverStanding,
    UnknownTakeover,
)
from taktus.components.run.domain.model.run import IN_FLIGHT
from taktus.ports.clock import Clock
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Capability, Method

TAKEN = "taken"
"""A take-over was asked, a result handed back, or a take-over's standing said."""
ASKED = "read_back"
REFUSED = "refused"
KINDS = ("take_over", "hand_back", "steer")
"""The acts read back here; a commissioning or a rollback waits in the same thread under the
change in dialogue's (`composition/change_in_channel.py`)."""
INPUTS_SHOWN = 600
"""How many characters of the inputs the state shows in the channel; the run's page shows all."""


class Takeovers(Protocol):
    """The run engine's take-over, state and hand-back (ADR-0128)."""

    async def take_over(self, command: TakeOver) -> str: ...

    async def takeover_state(self, tenant: Tenant, run_id: str, takeover: str) -> Any: ...

    async def hand_back(self, command: HandBack) -> Run: ...

    async def steer(self, command: SteerStep) -> str: ...


@dataclass(frozen=True)
class Taking:
    outcome: str
    replied: bool


class TakeoverInChannel:
    def __init__(
        self,
        *,
        channels: Repository[OwnerChannel],
        pending: Repository[PendingAct],
        runs: Repository[Run],
        work: UnitOfWork,
        takeovers: Takeovers,
        deliveries: Deliveries,
        secrets: SecretValues,
        clock: Clock,
    ) -> None:
        self._channels = channels
        self._pending = pending
        self._runs = runs
        self._work = work
        self._takeovers = takeovers
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
    ) -> Taking | None:
        """The answer, or None when the message is no take-over act in the owner's
        conversation: it goes on as any other message would."""
        if identity is None:
            return None
        async with self._work.transaction(tenant):
            found = await self._channels.get(tenant, tenant)
            waiting = await self._pending.get(tenant, _key(address, thread))
        if found is None or channel != found.channel or address != found.address:
            return None
        book = found.phrasebook
        if book.takeover_words is None:
            return None
        if (
            waiting is not None
            and waiting.kind in KINDS
            and waiting.state == "awaiting"
            and waiting.by == identity
        ):
            confirmed = rules.confirmation(text, book)
            if confirmed is not None:
                return await self._confirmed(found, waiting, confirmed, thread, event)
        asked = rules.takeover_act(text, book)
        if asked is None:
            return None
        not_done = (found, book.takeover_not_done, thread, event, REFUSED)
        if not found.may_answer(identity):
            return await self._say(*not_done)
        reader = Reader(tenant=tenant, identity=identity, roles=roles)
        if asked.kind == "take_over":
            run = await self._visible(reader, asked.run or "")
            step_run = None if run is None else _step(run, asked.step or "")
            if run is None or step_run is None or not _runs_in_worker(run, step_run):
                return await self._say(*not_done)
            act = PendingAct(
                id=_key(address, thread),
                tenant=tenant,
                kind="take_over",
                run=run.id,
                step=step_run.step_id,
                by=identity,
                asked_at=self._clock.now(),
            )
            read = _filled(book.takeover_read, run=run.id, step=step_run.step_id)
            return await self._read_back(found, act, read, thread, event)
        if asked.kind == "steer":
            run = await self._visible(reader, asked.run or "")
            step_run = None if run is None else _step(run, asked.step or "")
            said = asked.result or ""
            if run is None or step_run is None or self._secrets.carried_by(said):
                return await self._say(*not_done)
            act = PendingAct(
                id=_key(address, thread),
                tenant=tenant,
                kind="steer",
                run=run.id,
                step=step_run.step_id,
                result=said,
                by=identity,
                asked_at=self._clock.now(),
            )
            read = _filled(book.steer_read, run=run.id, step=step_run.step_id, text=said)
            return await self._read_back(found, act, read, thread, event)
        record = await self._asked(tenant, asked.takeover or "")
        run = None if record is None else await self._visible(reader, record.run or "")
        if record is None or run is None:
            return await self._say(*not_done)
        step_id = record.step or ""
        if asked.kind == "show":
            said = await self._standing(found, run, step_id, asked.takeover or "")
            return await self._say(found, said + _page(found, run.id, book), thread, event, TAKEN)
        standing = _standing_of(run, step_id, asked.takeover or "")
        if standing != "held":
            said = _standing_sentence(book, standing, asked.takeover or "", step_id)
            return await self._say(found, said, thread, event, REFUSED)
        words = asked.result or ""
        if self._secrets.carried_by(words):
            return await self._say(*not_done)
        result, form = _read_result(words, book)
        act = PendingAct(
            id=_key(address, thread),
            tenant=tenant,
            kind="hand_back",
            run=run.id,
            step=step_id,
            takeover=asked.takeover,
            result=result,
            by=identity,
            asked_at=self._clock.now(),
        )
        read = _filled(
            book.hand_back_read, takeover=asked.takeover or "", run=run.id, step=step_id, form=form
        )
        return await self._read_back(found, act, read, thread, event)

    async def _read_back(
        self, found: OwnerChannel, act: PendingAct, read: str, thread: str | None, event: str
    ) -> Taking:
        book = found.phrasebook
        async with self._work.transaction(found.tenant):
            await self._pending.put(found.tenant, act)
        confirm = book.confirm.format(yes=book.yes_words[0], no=book.no_words[0])
        return await self._say(found, f"{read} {confirm}", thread, event, ASKED)

    async def _confirmed(
        self,
        found: OwnerChannel,
        waiting: PendingAct,
        confirmed: bool,
        thread: str | None,
        event: str,
    ) -> Taking:
        book = found.phrasebook
        tenant = found.tenant
        run_id, step_id = waiting.run or "", waiting.step or ""
        async with self._work.transaction(tenant):
            await self._pending.put(
                tenant, waiting.model_copy(update={"state": "done" if confirmed else "dropped"})
            )
        if not confirmed:
            return await self._say(found, book.reread, thread, event, REFUSED)
        if waiting.kind == "take_over":
            try:
                takeover = await self._takeovers.take_over(
                    TakeOver(run_id=run_id, step_id=step_id, actor=waiting.by, tenant=tenant)
                )
            except RunError:
                return await self._say(found, book.takeover_not_done, thread, event, REFUSED)
            async with self._work.transaction(tenant):
                await self._pending.put(
                    tenant,
                    waiting.model_copy(
                        update={"id": takeover, "takeover": takeover, "state": "done"}
                    ),
                )
            said = _filled(book.takeover_asked, takeover=takeover, run=run_id, step=step_id)
            return await self._say(found, said + _page(found, run_id, book), thread, event, TAKEN)
        if waiting.kind == "steer":
            try:
                message = await self._takeovers.steer(
                    SteerStep(
                        run_id=run_id,
                        step_id=step_id,
                        text=str(waiting.result),
                        actor=waiting.by,
                        tenant=tenant,
                    )
                )
            except RunError as error:
                said = _filled(book.steer_refused, reason=str(error).rstrip("."))
                return await self._say(found, said, thread, event, REFUSED)
            said = _filled(book.steered, message=message, run=run_id, step=step_id)
            return await self._say(found, said + _page(found, run_id, book), thread, event, TAKEN)
        takeover = waiting.takeover or ""
        try:
            await self._takeovers.hand_back(
                HandBack(
                    run_id=run_id,
                    takeover=takeover,
                    result=waiting.result,
                    actor=waiting.by,
                    tenant=tenant,
                )
            )
        except UnknownTakeover:
            async with self._work.transaction(tenant):
                run = await self._runs.get(tenant, run_id)
            standing = "unknown" if run is None else _standing_of(run, step_id, takeover)
            said = _standing_sentence(book, standing, takeover, step_id)
            return await self._say(found, said, thread, event, REFUSED)
        except RunError:
            # A hand-back after the lease passed and a runner took the step back fails the
            # fence (ADR-0128 §5): nothing of it landed.
            said = _filled(book.takeover_lapsed, takeover=takeover, step=step_id)
            return await self._say(found, said, thread, event, REFUSED)
        said = _filled(book.handed_back, run=run_id, step=step_id)
        return await self._say(found, said + _page(found, run_id, book), thread, event, TAKEN)

    async def _visible(self, reader: Reader, run_id: str) -> Run | None:
        """The run, when the reader may see it; None alike when it does not exist."""
        async with self._work.transaction(reader.tenant):
            run = await self._runs.get(reader.tenant, run_id)
        if run is None:
            return None
        ref = RunRef(id=run.id, tenant=run.tenant, process_version=run.process_version)
        return run if visibility.may_see(reader, ref) else None

    async def _asked(self, tenant: Tenant, takeover: str) -> PendingAct | None:
        """The take-over asked in this conversation under that identifier."""
        async with self._work.transaction(tenant):
            record = await self._pending.get(tenant, takeover)
        if record is None or record.kind != "take_over" or record.takeover != takeover:
            return None
        return record

    async def _standing(self, found: OwnerChannel, run: Run, step_id: str, takeover: str) -> str:
        """Where the take-over stands, in words; while it is held, with the state it reached."""
        book = found.phrasebook
        standing = _standing_of(run, step_id, takeover)
        if standing != "held":
            return _standing_sentence(book, standing, takeover, step_id)
        try:
            state = await self._takeovers.takeover_state(found.tenant, run.id, takeover)
        except RunError:
            return book.takeover_not_done or ""
        return _state_text(book, state)

    async def _say(
        self, found: OwnerChannel, said: str | None, thread: str | None, event: str, outcome: str
    ) -> Taking:
        if said and self._secrets.carried_by(said):
            said, outcome = found.phrasebook.takeover_not_done, REFUSED
        sent = await self._deliveries.say(
            found.tenant,
            found.channel,
            found.address,
            said or "",
            thread=thread,
            key=_idempotency(event),
        )
        return Taking(outcome=outcome, replied=isinstance(sent, Sent))


def _step(run: Run, step_id: str) -> StepRun | None:
    return next((s for s in run.step_runs if s.step_id == step_id), None)


def _runs_in_worker(run: Run, step_run: StepRun) -> bool:
    """Whether the step may be asked for: a worker step running in a running run (ADR-0128 §1).
    The engine decides again when the ask is confirmed."""
    return (
        run.state is RunState.RUNNING
        and step_run.state in IN_FLIGHT
        and run.step(step_run.step_id).method is Method.WORKER
    )


def _standing_of(run: Run, step_id: str, takeover: str) -> str:
    """`held`, `handed_back` or `lapsed` once served; `asked` while its step still runs in a
    running run; `refused` once the step ended another way before it stopped."""
    step_run = _step(run, step_id)
    if step_run is None:
        return "unknown"
    for served in step_run.takeovers():
        if served.id == takeover:
            return str(served.standing)
    if run.state is RunState.RUNNING and step_run.state in IN_FLIGHT:
        return "asked"
    return "refused"


def _standing_sentence(book: Phrasebook, standing: str, takeover: str, step: str) -> str:
    template = {
        "asked": book.takeover_waiting,
        "refused": book.takeover_refused,
        str(TakeoverStanding.LAPSED): book.takeover_lapsed,
        str(TakeoverStanding.HANDED_BACK): book.takeover_handed,
    }.get(standing)
    if template is None:
        return book.takeover_not_done or ""
    return _filled(template, takeover=takeover, step=step)


def _state_text(book: Phrasebook, state: Any) -> str:
    """The state a step was taken over in (ADR-0128 §3), as the phrasebook's sentence."""
    document = state if isinstance(state, dict) else {}
    inputs = json.dumps(document.get("inputs"), ensure_ascii=False, sort_keys=True)
    if len(inputs) > INPUTS_SHOWN:
        inputs = inputs[:INPUTS_SHOWN] + "…"
    artifacts = document.get("artifacts") or []
    produced = ", ".join(
        f"{a.get('id')} ({a.get('kind')})" for a in artifacts if isinstance(a, dict)
    )
    acceptance = document.get("acceptance") or []
    return _filled(
        book.takeover_state,
        takeover=str(document.get("takeover", "")),
        run=str(document.get("run_id", "")),
        step=str(document.get("step_id", "")),
        until=str(document.get("held_until", "")),
        goal=str(document.get("goal") or "—"),
        acceptance="; ".join(str(a) for a in acceptance) or "—",
        inputs=inputs,
        checkpoint=str(document.get("checkpoint") or "—"),
        produced=produced or "—",
    )


def _read_result(words: str, book: Phrasebook) -> tuple[Any, str]:
    """The result as it is read: a JSON value when the words parse as one, else the words as
    written — and how it was read, in the phrasebook's words, for the reading sent back."""
    try:
        return json.loads(words), book.as_json or ""
    except ValueError:
        return words, book.as_text or ""


def _filled(template: str | None, **values: str) -> str:
    return (template or "").format(**values)


def _page(found: OwnerChannel, run: str, book: Phrasebook) -> str:
    """The link to the run's page in the web app, where a view base is known."""
    if found.view_base is None or book.live is None:
        return ""
    return f"\n{book.live}: {found.view_base.rstrip('/')}/app/#/runs/{run}"


def _key(address: str, thread: str | None) -> str:
    return f"{address}:{thread or '-'}"


def _idempotency(event: str) -> str:
    """The idempotency key of the answer to one message: a redelivery answers once."""
    raw = f"taktus:takeover:{event}"
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]", "-", raw)
    if len(cleaned) <= 128:
        return cleaned
    return "taktus:takeover:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]
