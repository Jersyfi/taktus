"""Time triggers: what the scheduler does on every tick while it leads (ADR-0035).

For every tenant the instance serves, the process component answers which schedule triggers are
due. Each due firing becomes runs through the one path every channel takes
(control-plane.md §1): a command on the channel `channel.schedule`, a commissioned plan, a run
submitted to the queue with a job, in one transaction. A runner executes it like any other.

**Once per slot.** Three things keep a firing from starting a run twice. Only the elected
scheduler fires. The run's identifier is derived from the trigger, the slot and the item, so
that a second firing of the same slot names the same run, and the run engine refuses to create
a run that exists. The firing is recorded as fired only once its runs exist, so that a leader
that dies in between leaves the slot to the next leader, which starts what is missing and
nothing twice.

**Who acts.** Nothing executes without an identity (control-plane.md §2). A scheduled run acts
as the identity the identity port places in the tenant for the schedule channel: today the
provisional operator identity (`TAKTUS_PROVISIONAL_IDENTITY`, DEC-0013). Without one the
trigger does not fire, and every tick says so until one is configured.

This is wiring, because a firing crosses three components — process, command and run — and only
the composition root may hold them all (`composition/README.md`).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any

import structlog

from taktus.components.command.application.service import CommissionPlan, CommissionPlanHandler
from taktus.components.process.application.service.triggers import (
    FindDueFirings,
    RecordFiring,
    TriggersHandler,
)
from taktus.components.process.domain.model import Firing
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import RunError, RunExists, select
from taktus.components.run.ports import ConnectorPool
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.connector import CallContext, CallFailed, ConnectorError, idempotency_key
from taktus.ports.identity import IdentityResolver
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Tenant, UnitOfWork
from taktus.ports.worker import Limits
from taktus.shared.v1 import Command, Intent, LedgerRefs, ReplyTo

CHANNEL = "channel.schedule"
ACCOUNT = "scheduler"
REFUSED = "trigger.refused"

log = structlog.get_logger("taktusd")


class TriggerFailed(Exception):
    """The firing could not learn what to start: its `each` list could not be read. Nothing
    was started; the next tick tries again."""


class Triggers:
    """The scheduler's tick for time triggers. `tick()` never raises: a firing that fails is
    logged and left due, so that watching the clock never stops the scheduler."""

    def __init__(
        self,
        *,
        tenants: Sequence[Tenant],
        triggers: TriggersHandler,
        commission: CommissionPlanHandler,
        engine: RunEngine,
        connectors: ConnectorPool,
        identities: IdentityResolver | None,
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
        ids: Identifiers,
    ) -> None:
        self._tenants = tuple(tenants)
        self._triggers = triggers
        self._commission = commission
        self._engine = engine
        self._connectors = connectors
        self._identities = identities
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._ids = ids

    async def tick(self) -> list[str]:
        """The runs this tick started, by identifier."""
        started: list[str] = []
        for tenant in self._tenants:
            try:
                firings = await self._triggers.due(FindDueFirings(tenant, self._clock.now()))
                for firing in firings:
                    started.extend(await self._fire(tenant, firing))
            except Exception as error:  # a tick must never take the scheduler down
                log.error(
                    "time triggers failed; the next tick tries again",
                    tenant=tenant,
                    error=f"{type(error).__name__}: {error}",
                )
        return started

    async def _fire(self, tenant: Tenant, firing: Firing) -> list[str]:
        identity = await self._identity(tenant)
        if identity is None:
            log.warning(
                "a time trigger is due and nothing executes without an identity; set "
                "TAKTUS_PROVISIONAL_IDENTITY for the tenant (DEC-0013)",
                tenant=tenant,
                trigger=firing.state.id,
            )
            return []
        try:
            items = await self._items(tenant, firing, identity)
        except TriggerFailed as error:
            log.error(
                "a time trigger could not read what to start",
                trigger=firing.state.id,
                reason=str(error),
            )
            return []
        started: list[str] = []
        runs: list[str] = []
        for item in items:
            run_id = firing.run_id(tenant, item)
            try:
                await self._start(tenant, firing, item, run_id, identity)
            except RunExists:
                runs.append(run_id)  # started by an earlier firing of the same slot
                continue
            except RunError as error:
                # The version cannot run as it is — no budget, work it cannot execute. Firing
                # again would refuse again: the slot is recorded, and the refusal is in the
                # ledger and the log.
                await self._refused(tenant, firing, item, identity, str(error))
                continue
            runs.append(run_id)
            started.append(run_id)
            log.info(
                "time trigger started a run",
                tenant=tenant,
                trigger=firing.state.id,
                slot=firing.slot.isoformat(),
                run=run_id,
            )
        await self._triggers.record(
            RecordFiring(tenant=tenant, firing=firing, runs=tuple(runs), at=self._clock.now())
        )
        return started

    async def _identity(self, tenant: Tenant) -> str | None:
        if self._identities is None:
            return None
        resolution = await self._identities.resolve(CHANNEL, ACCOUNT, tenant=tenant)
        return None if resolution is None else resolution.identity

    async def _items(self, tenant: Tenant, firing: Firing, identity: str) -> list[Any]:
        """[None] without `each`; otherwise the items the declared read answers."""
        each = firing.trigger.each
        if each is None:
            return [None]
        resolved = await self._connectors.resolve(each.capability)
        if resolved is None:
            raise TriggerFailed(f"no configured connector serves {each.capability!r}")
        operation = resolved.declaration.operation(each.operation)
        if operation is None:
            raise TriggerFailed(f"{resolved.adapter} does not declare {each.operation}")
        if operation.outward:
            raise TriggerFailed(
                f"{each.operation} is declared {operation.effect}; a trigger only reads"
            )
        # The read is keyed like a step of a run: the firing stands for the run.
        firing_id = firing.run_id(tenant, "each")
        context = CallContext(
            tenant=tenant,
            identity=identity,
            run_id=firing_id,
            step_id="each",
            attempt=1,
            idempotency_key=idempotency_key(firing_id, "each", 1),
            credentials=(),
        )
        try:
            result = await resolved.connector.call(each.operation, context, {})
            listed = select(result.output, each.select)
        except (CallFailed, ConnectorError, KeyError) as error:
            raise TriggerFailed(f"{each.operation}: {type(error).__name__}: {error}") from error
        if not isinstance(listed, list):
            raise TriggerFailed(f"{each.operation} answered no list at {each.select!r}")
        try:
            return [select(item, each.field) for item in listed]
        except KeyError as error:
            raise TriggerFailed(f"an item of {each.operation} has no {each.field!r}") from error

    def _inputs(self, firing: Firing, item: Any) -> dict[str, Any]:
        inputs = dict(firing.trigger.inputs or {})
        if firing.trigger.each is not None:
            inputs[firing.trigger.each.input] = item
        return inputs

    async def _start(
        self, tenant: Tenant, firing: Firing, item: Any, run_id: str, identity: str
    ) -> None:
        version = firing.version
        if version.limits is None:
            raise RunError(f"{version.ref} names no `limits`; a run needs a budget")
        try:
            budget = Limits.model_validate(dict(version.limits))
        except ValueError as error:
            raise RunError(f"{version.ref}: `limits`: {error}") from error
        inputs = self._inputs(firing, item)
        triggered = firing.triggered(item)
        command = Command(
            id=self._ids.new("cmd"),
            channel=CHANNEL,
            identity=identity,
            org_path=(tenant,),
            intent=Intent(raw=f"run {version.ref} on schedule", recognised="process.run"),
            context={"inputs": inputs, "trigger": triggered} if inputs else {"trigger": triggered},
            reply_to=ReplyTo(channel=CHANNEL, address="ledger"),
            received_at=self._clock.now(),
        )
        plan = await self._commission.execute(
            CommissionPlan(
                command=command,
                tenant=tenant,
                goal=f"run process {version.name} ({version.ref}) for the slot "
                f"{firing.slot.isoformat()} of {firing.state.schedule!r}",
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
                actor=identity,
                tenant=tenant,
                inputs=inputs,
                run_id=run_id,
                trigger=triggered,
            )
        )

    async def _refused(
        self, tenant: Tenant, firing: Firing, item: Any, identity: str, reason: str
    ) -> None:
        log.error(
            "a time trigger fired and its run was refused",
            tenant=tenant,
            trigger=firing.state.id,
            slot=firing.slot.isoformat(),
            reason=reason,
        )
        # Content-free, as `run.triggered` is: the digest of the trigger, slot and item.
        canonical = json.dumps(firing.triggered(item), ensure_ascii=False, sort_keys=True)
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=REFUSED,
                    refs=LedgerRefs(
                        tenant=tenant, process_version=firing.version.ref, actor=identity
                    ),
                    outcome="refused",
                    content_digest="sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
                ),
            )
