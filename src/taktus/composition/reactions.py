"""Event reactions: what the automation role does on every pass while it leads (ADR-0048).

For every tenant the instance serves, the role reads the outbox entries `intake.accepted` the
intake wrote, the oldest first. For each, it asks the process component which processes the
event starts, completes the intake into one command, and starts one run of each process through
the one path every channel takes (control-plane.md §1): a commissioned plan, a run submitted to
the queue with a job. A runner executes it like any other.

**Once per delivery.** Four things keep one delivery from starting a process twice (§4). The
intake keeps a delivery once. Only the elected automation role reacts. The run's identifier is
derived from the tenant, the process and the event's identifier, and the run engine refuses to
create a run that exists. The entry is published only once its runs exist, so that a leader
that dies in between leaves it to the next leader, which completes nothing twice and starts
what is missing.

**Who acts.** The command acts for the identity its sender was placed as (ADR-0040 §6); the
runs act for the command's identity. A sender the identity component no longer places starts
nothing.

**A condition waits.** A trigger whose condition does not hold leaves the entry unpublished;
the processes whose triggers need no condition, or whose condition holds, start now, and the
rest on a later pass (§2). Every pass says in the log what waits.

This is wiring, because a reaction crosses three components — command, process and run — and
only the composition root may hold them all (`composition/README.md`).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import structlog

from taktus.components.command.application.service import (
    CommissionPlan,
    CommissionPlanHandler,
    CompleteIntake,
    CompleteIntakeHandler,
    UnknownIntakeEvent,
    UnknownSender,
)
from taktus.components.command.domain.model import IntakeEvent
from taktus.components.process.application.service.reactions import (
    FindReactions,
    Reaction,
    ReactionsHandler,
)
from taktus.components.process.domain.model import Condition, Event, ProcessVersion
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunError, RunExists
from taktus.components.run.domain.service.capacity import (
    CapacityDemand,
    CapacityRules,
    admit_capacity,
)
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.outbox import INTAKE_ACCEPTED, Outbox, OutboxEntry
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.ports.platform import Platform
from taktus.ports.worker import Limits
from taktus.shared.v1 import Command, LedgerRefs, Method

REFUSED = "trigger.refused"
BATCH = 50

type ConditionCheck = Callable[[ProcessVersion], Awaitable[str | None]]
"""Why the condition does not hold for a version now, or None when it does."""

log = structlog.get_logger("taktusd")


def event_of(kept: IntakeEvent) -> Event | None:
    """The event an intake is, or None when its kind is outside the catalogue or its context
    lacks what its kind requires (`contracts/events/v1` §1)."""
    kind = Event.of(kept.event)
    if kind is None:
        return None
    event = Event(
        id=kept.id,
        kind=kind,
        channel=kept.channel,
        occurred_at=kept.occurred_at,
        received_at=kept.received_at,
        context=Event.context_of(kept.context),
    )
    return None if event.missing() else event


def run_id_of(tenant: Tenant, process_id: str, event_id: str) -> str:
    """The run one delivery starts of one process. Derived, never drawn: a second reaction to
    the same delivery — after a restart, or a lost lead — names the same run (ADR-0048 §4)."""
    document = {"tenant": tenant, "process": process_id, "event": event_id}
    canonical = json.dumps(document, ensure_ascii=False, sort_keys=True)
    return "run_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def triggered(reaction: Reaction, event: Event) -> dict[str, Any]:
    """What the run records as the trigger that started it; the ledger keeps its digest."""
    return {
        "kind": "event",
        "process": reaction.version.process_id,
        "trigger": reaction.trigger.key,
        "event": event.kind.value,
        "event_id": event.id,
    }


def capacity_condition(
    platform: Platform, rules: CapacityRules, unit_memory_bytes: int | None
) -> ConditionCheck:
    """`capacity.available` (`contracts/events/v1` §4): the admission the run itself meets
    against the platform, asked now — storage, and memory for one execution unit where a step
    of the version is a worker step. What the platform does not observe refuses nothing."""

    async def refuses(version: ProcessVersion) -> str | None:
        worker = any(step.method is Method.WORKER for step in version.steps)
        verdict = admit_capacity(
            await platform.observe(),
            CapacityDemand(memory_bytes=unit_memory_bytes if worker else None),
            rules,
        )
        return None if verdict.fits else "; ".join(verdict.findings)

    return refuses


class Reactions:
    """The automation role's pass. `tick()` never raises: an entry that fails is logged and
    left unpublished, so that reacting never stops the role."""

    def __init__(
        self,
        *,
        tenants: Sequence[Tenant],
        outbox: Outbox,
        intake: CompleteIntakeHandler,
        reactions: ReactionsHandler,
        commission: CommissionPlanHandler,
        engine: RunEngine,
        runs: Repository[Run],
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
        capacity: ConditionCheck | None = None,
    ) -> None:
        self._tenants = tuple(tenants)
        self._outbox = outbox
        self._intake = intake
        self._reactions = reactions
        self._commission = commission
        self._engine = engine
        self._runs = runs
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._capacity = capacity

    async def tick(self) -> list[str]:
        """The runs this pass started, by identifier."""
        started: list[str] = []
        for tenant in self._tenants:
            try:
                async with self._work.transaction(tenant):
                    entries = await self._outbox.unpublished(tenant, INTAKE_ACCEPTED, BATCH)
                for entry in entries:
                    try:
                        started.extend(await self._react(tenant, entry))
                    except Exception as error:  # one entry never stops the others
                        log.error(
                            "an event reaction failed; the next pass tries again",
                            tenant=tenant,
                            entry=entry.id,
                            error=f"{type(error).__name__}: {error}",
                        )
            except Exception as error:  # a pass must never take the role down
                log.error(
                    "event reactions failed; the next pass tries again",
                    tenant=tenant,
                    error=f"{type(error).__name__}: {error}",
                )
        return started

    async def _publish(self, tenant: Tenant, entry: OutboxEntry) -> None:
        async with self._work.transaction(tenant):
            await self._outbox.publish(tenant, entry.id)

    async def _react(self, tenant: Tenant, entry: OutboxEntry) -> list[str]:
        event_id = str(entry.payload.get("event_id", ""))
        kept = await self._intake.event(tenant, event_id) if event_id else None
        if kept is None:
            log.warning("an outbox entry names no intake event", tenant=tenant, entry=entry.id)
            await self._publish(tenant, entry)
            return []
        event = event_of(kept)
        if event is None:
            # Not an event of the catalogue: kept as an intake, which a person may complete.
            await self._publish(tenant, entry)
            return []
        found = await self._reactions.find(FindReactions(tenant=tenant, event=event))
        for reason in found.passed_over:
            log.info("an event does not start a process", kind=event.kind, reason=reason)
        if not found.started:
            await self._publish(tenant, entry)
            return []
        ready: list[Reaction] = []
        waiting = False
        for reaction in found.started:
            run_id = run_id_of(tenant, reaction.version.process_id, event.id)
            async with self._work.transaction(tenant):
                exists = await self._runs.get(tenant, run_id) is not None
            if exists:
                continue  # started by an earlier pass
            why = await self._waits(reaction)
            if why is not None:
                waiting = True
                log.info(
                    "an event reaction waits for its condition",
                    tenant=tenant,
                    process=reaction.version.ref,
                    kind=event.kind,
                    condition=reaction.trigger.condition,
                    reason=why,
                )
                continue
            ready.append(reaction)
        started: list[str] = []
        if ready:
            try:
                command = await self._intake.command_of(
                    CompleteIntake(tenant=tenant, event_id=event.id)
                )
            except (UnknownSender, UnknownIntakeEvent) as error:
                log.warning(
                    "an event starts nothing: its sender is not placed any more",
                    tenant=tenant,
                    reason=str(error),
                )
                await self._publish(tenant, entry)
                return []
            for reaction in ready:
                run_id = run_id_of(tenant, reaction.version.process_id, event.id)
                try:
                    await self._start(tenant, command, reaction, event, run_id)
                except RunExists:
                    continue
                except RunError as error:
                    await self._refused(tenant, reaction, event, command.identity, str(error))
                    continue
                started.append(run_id)
                log.info(
                    "an event started a run",
                    tenant=tenant,
                    process=reaction.version.ref,
                    kind=event.kind,
                    run=run_id,
                )
        if not waiting:
            await self._publish(tenant, entry)
        return started

    async def _waits(self, reaction: Reaction) -> str | None:
        condition = reaction.trigger.condition
        if condition is None:
            return None
        if condition == Condition.CAPACITY_AVAILABLE.value:
            return None if self._capacity is None else await self._capacity(reaction.version)
        return f"the condition {condition!r} is not one this instance evaluates"

    async def _start(
        self, tenant: Tenant, command: Command, reaction: Reaction, event: Event, run_id: str
    ) -> None:
        version = reaction.version
        if version.limits is None:
            raise RunError(f"{version.ref} names no `limits`; a run needs a budget")
        try:
            budget = Limits.model_validate(dict(version.limits))
        except ValueError as error:
            raise RunError(f"{version.ref}: `limits`: {error}") from error
        plan = await self._commission.execute(
            CommissionPlan(
                command=command,
                tenant=tenant,
                goal=f"run process {version.name} ({version.ref}) on the event {event.kind} "
                f"{event.id}",
                autonomy_level=version.autonomy_level,
                steps=version.ordered(),
            )
        )
        await self._engine.submit(
            StartRun(
                plan=plan,
                work=version.work,
                budget=budget,
                process_version=version.ref,
                actor=command.identity,
                tenant=tenant,
                inputs=reaction.inputs,
                run_id=run_id,
                trigger=triggered(reaction, event),
                actions=version.autonomy.action_levels,
            )
        )

    async def _refused(
        self, tenant: Tenant, reaction: Reaction, event: Event, identity: str, reason: str
    ) -> None:
        log.error(
            "an event started a run and the run was refused",
            tenant=tenant,
            process=reaction.version.ref,
            kind=event.kind,
            reason=reason,
        )
        canonical = json.dumps(triggered(reaction, event), ensure_ascii=False, sort_keys=True)
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=REFUSED,
                    refs=LedgerRefs(
                        tenant=tenant, process_version=reaction.version.ref, actor=identity
                    ),
                    outcome="refused",
                    content_digest="sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
                ),
            )
