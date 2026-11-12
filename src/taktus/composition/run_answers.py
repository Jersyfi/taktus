"""A run answers in the channel its command came from, by itself (ADR-0239, UC-1.1).

When a run started from a channel's command finishes, escalates or comes to wait for a person,
the elected scheduler says so at the command's reply address, in the thread it arrived in: the
answer, or the question back. Which runs are owed an answer is the ledger's projection
`run.owed_answers.v1`: every `run.finished`, `run.escalated` and `run.waiting_human` not yet
followed by `run.answered`. Saying it records `run.answered` with what was said — `said`, or
`not_said` where the channel has no reply operation or the command came from no channel that
replies — so that each end is answered once, across restarts and instances. The idempotency key
names the run and the entry, so a connector asked twice says it once.

A run whose plan or command the stores no longer hold, and a run of no command — a trigger's, a
deadline's — is recorded `not_said` too: nobody asked in a channel. A delivery that fails is not
retried, as no answer in a channel is (`replies.py`).

Only an end of the last `WINDOW` is owed. An end older than that — the history an instance
holds when this first runs — is answered by nobody, so that an upgrade does not answer old runs
in their threads all at once.

This is wiring: it joins the run, the command and the ledger.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import structlog

from taktus.components.run.domain.model import Run
from taktus.composition.tenancy import this_round
from taktus.ports.clock import Clock
from taktus.ports.connector import ChannelReplies, IntakeReplyTo
from taktus.ports.identity import ServedTenants
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Command, LedgerEntry, LedgerRefs, Plan

log = structlog.get_logger("taktus.answers")

RUN_ANSWERED = "run.answered"
OWED = frozenset({"run.finished", "run.escalated", "run.waiting_human"})
NO_REPLY = frozenset({"channel.cli", "channel.schedule", "channel.event"})
"""Channels whose reply address nobody reads in a thread: the command line prints its own
answer, a schedule and an event have no person to answer."""
WINDOW = timedelta(hours=1)
"""How long after a run's end it is still owed an answer."""


@dataclass(frozen=True)
class Owed:
    run_id: str
    kind: str
    seq: int
    at: datetime


class OwedAnswers:
    """The ends of runs not yet answered, by run (ADR-0105)."""

    name = "run.owed_answers.v1"
    kinds: frozenset[str] | None = frozenset({*OWED, RUN_ANSWERED})

    def empty(self) -> Mapping[str, Owed]:
        return {}

    def fold(self, state: Mapping[str, Owed], entry: LedgerEntry) -> Mapping[str, Owed]:
        run_id = entry.refs.run_id
        if run_id is None:
            return state
        kept = {k: v for k, v in state.items() if k != run_id and entry.ts - v.at <= WINDOW}
        if entry.kind == RUN_ANSWERED:
            return kept
        return {**kept, run_id: Owed(run_id=run_id, kind=entry.kind, seq=entry.seq, at=entry.ts)}

    def dump(self, state: Mapping[str, Owed]) -> dict[str, Any]:
        return {
            "owed": [
                {"run_id": o.run_id, "kind": o.kind, "seq": o.seq, "at": o.at.isoformat()}
                for o in state.values()
            ]
        }

    def load(self, document: Mapping[str, Any]) -> Mapping[str, Owed]:
        return {
            d["run_id"]: Owed(
                run_id=d["run_id"],
                kind=d["kind"],
                seq=d["seq"],
                at=datetime.fromisoformat(d["at"]),
            )
            for d in document.get("owed", [])
        }


def said(run: Run, kind: str) -> str:
    """What the run says when it ended this way: the answer, or the question back."""
    if kind == "run.finished":
        return f"Done: run {run.id} of {run.process_version} finished."
    if kind == "run.escalated":
        why = f": {run.reason}" if run.reason else ""
        return f"Run {run.id} of {run.process_version} needs a person{why}."
    waiting = [s.step_id for s in run.step_runs if s.state.value == "waiting_human"]
    steps = ", ".join(waiting) or "a step"
    return (
        f"Run {run.id} of {run.process_version} waits for you: {steps} needs your answer "
        "before it continues."
    )


class RunAnswers:
    def __init__(
        self,
        tenants: ServedTenants,
        ledger: Ledger,
        runs: Repository[Run],
        plans: Repository[Plan],
        commands: Repository[Command],
        work: UnitOfWork,
        replies: ChannelReplies,
        clock: Clock,
    ) -> None:
        self._clock = clock
        self._tenants = tenants
        self._ledger = ledger
        self._runs = runs
        self._plans = plans
        self._commands = commands
        self._work = work
        self._replies = replies

    async def tick(self) -> list[tuple[str, str]]:
        """Every run answered this tick, with whether it was said."""
        answered: list[tuple[str, str]] = []
        for tenant in await this_round(self._tenants, "scheduler"):
            try:
                answered.extend(await self.answer(tenant))
            except Exception as error:  # a tick never takes the scheduler down
                log.error("runs could not be answered", tenant=tenant, error=str(error))
        return answered

    async def answer(self, tenant: Tenant) -> list[tuple[str, str]]:
        async with self._work.transaction(tenant):
            owed = await self._ledger.project(tenant, OwedAnswers())
        since = self._clock.now() - WINDOW
        answered: list[tuple[str, str]] = []
        for item in sorted(owed.values(), key=lambda o: o.seq):
            if item.at >= since:
                answered.append((item.run_id, await self._say(tenant, item)))
        return answered

    async def _say(self, tenant: Tenant, item: Owed) -> str:
        async with self._work.transaction(tenant):
            run = await self._runs.get(tenant, item.run_id)
            plan = None if run is None else await self._plans.get(tenant, run.plan_id)
            command = None if plan is None else await self._commands.get(tenant, plan.command_id)
        outcome = "not_said"
        if run is not None and command is not None and command.reply_to.channel not in NO_REPLY:
            to = command.reply_to
            delivered = await self._replies.reply(
                tenant,
                IntakeReplyTo(channel=to.channel, address=to.address, thread=to.thread),
                said(run, item.kind),
                key=_key(item.run_id, item.seq),
            )
            outcome = "said" if delivered else "not_said"
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=RUN_ANSWERED,
                    refs=LedgerRefs(
                        tenant=tenant,
                        run_id=item.run_id,
                        command_id=None if command is None else command.id,
                        plan_id=None if run is None else run.plan_id,
                    ),
                    outcome=outcome,
                ),
            )
        return outcome


def _key(run_id: str, seq: int) -> str:
    raw = f"taktus:answer:{run_id}:{seq}"
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]", "-", raw)
    if len(cleaned) <= 128:
        return cleaned
    return "taktus:answer:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]
