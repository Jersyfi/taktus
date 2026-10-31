"""Deadlines: what the scheduler does on every tick while it leads (ADR-0133, UC-4.17).

For every tenant the instance serves, the run component's keeper answers which actions are due
on its deadlines. A reminder and an escalation are taken by the keeper alone: kept on the
deadline, for the role it names, with its ledger entry. A start of a process crosses three
components — process, command and run — and only the composition root may hold them all
(`composition/README.md`): the started process's active version is commissioned and submitted
through the one path every channel takes, as a schedule trigger's is (ADR-0035 §4 to §6).

**Once.** The started run's identifier is derived from the deadline and the moment, so a start
repeated after a crash meets the run it started (`RunExists`). The keeper takes the action in
one transaction with its entry and reads the record again under the tenant's ledger lock, so a
second scheduler that took it meanwhile changes nothing.

**Who acts.** A started run acts for the identity that registered the started process's active
version (ADR-0040). A process without an active version, or registered by nobody the tenant
knows, starts nothing, and the action is recorded as `refused`.
"""

from __future__ import annotations

import hashlib
from typing import Any

import structlog

from taktus.components.command.application.service import CommissionPlan, CommissionPlanHandler
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.application.service.deadlines import DeadlineKeeper, Taken
from taktus.components.run.domain.model import RunError, RunExists
from taktus.components.run.domain.model.deadline import ActionKind
from taktus.components.run.domain.service.deadlines import Due
from taktus.composition.tenancy import this_round
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.identity import IdentityResolver, ServedTenants
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.ports.worker import Limits
from taktus.shared.v1 import Command, Intent, ReplyTo

CHANNEL = "channel.schedule"
"""A run a deadline starts comes from the scheduler, as a scheduled run does."""

log = structlog.get_logger("taktusd")


def started_run_id(due: Due) -> str:
    """The run a start at this moment of this deadline is: the same after a crash."""
    raw = f"{due.deadline.tenant}\x00{due.deadline.id}\x00{due.moment}"
    return "run_dl" + hashlib.sha256(raw.encode()).hexdigest()[:24]


class Deadlines:
    """The scheduler's tick for deadlines. `tick()` never raises: an action that fails is
    logged and left due, so that watching the clock never stops the scheduler."""

    def __init__(
        self,
        *,
        tenants: ServedTenants,
        keeper: DeadlineKeeper,
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
        commission: CommissionPlanHandler,
        engine: RunEngine,
        identities: IdentityResolver,
        work: UnitOfWork,
        clock: Clock,
        ids: Identifiers,
    ) -> None:
        self._tenants = tenants
        self._keeper = keeper
        self._processes = processes
        self._versions = versions
        self._commission = commission
        self._engine = engine
        self._identities = identities
        self._work = work
        self._clock = clock
        self._ids = ids

    async def tick(self) -> list[Taken]:
        """The actions this tick took."""
        done: list[Taken] = []
        for tenant in await this_round(self._tenants, "scheduler"):
            try:
                for due in await self._keeper.due(tenant):
                    taken = await self._take(tenant, due)
                    if taken is not None:
                        done.append(taken)
                        log.warning(
                            "a deadline's action was taken",
                            tenant=tenant,
                            deadline=due.deadline.id,
                            name=due.deadline.name,
                            run=due.deadline.run_id,
                            moment=due.moment,
                            action=taken.outcome,
                            role=due.action.role,
                            due_at=due.at.isoformat(),
                        )
            except Exception as error:  # a tick must never take the scheduler down
                log.error(
                    "deadlines not kept this tick; the next tick tries again",
                    tenant=tenant,
                    error=f"{type(error).__name__}: {error}",
                )
        return done

    async def _take(self, tenant: Tenant, due: Due) -> Taken | None:
        if due.action.kind is not ActionKind.START:
            return await self._keeper.take(tenant, due)
        run_id = started_run_id(due)
        try:
            await self._start(tenant, due, run_id)
        except RunExists:
            pass  # started by an earlier tick, which did not live to note it
        except RunError as error:
            log.error(
                "a deadline's start was refused",
                tenant=tenant,
                deadline=due.deadline.id,
                process=due.action.process,
                reason=str(error),
            )
            return await self._keeper.take(tenant, due, refused=str(error)[:300])
        return await self._keeper.take(tenant, due, started_run=run_id)

    async def _start(self, tenant: Tenant, due: Due, run_id: str) -> None:
        name = due.action.process or ""
        async with self._work.transaction(tenant):
            process = await self._processes.get(tenant, name)
            version = (
                None
                if process is None or process.active_version is None
                else await self._versions.get(tenant, f"{process.id}@{process.active_version}")
            )
        if process is None or version is None:
            raise RunError(f"the process {name!r} has no active version")
        placed = (
            None
            if process.activated_by is None
            else await self._identities.identity(tenant, process.activated_by)
        )
        if placed is None:
            raise RunError(
                f"the active version of {name!r} was registered by no identity the tenant "
                "knows; nothing executes without one (ADR-0040)"
            )
        if version.limits is None:
            raise RunError(f"{version.ref} names no `limits`; a run needs a budget")
        try:
            budget = Limits.model_validate(dict(version.limits))
        except ValueError as error:
            raise RunError(f"{version.ref}: `limits`: {error}") from error
        inputs: dict[str, Any] = dict(due.action.inputs)
        trigger = {
            "kind": "deadline",
            "deadline": due.deadline.id,
            "name": due.deadline.name,
            "case": due.deadline.run_id,
            "moment": due.moment,
        }
        command = Command(
            id=self._ids.new("cmd"),
            channel=CHANNEL,
            identity=placed.identity,
            org_path=placed.org_path,
            intent=Intent(raw=f"run {version.ref} at a deadline", recognised="process.run"),
            context={"inputs": inputs, "trigger": trigger} if inputs else {"trigger": trigger},
            reply_to=ReplyTo(channel=CHANNEL, address="ledger"),
            received_at=self._clock.now(),
        )
        plan = await self._commission.execute(
            CommissionPlan(
                command=command,
                tenant=tenant,
                goal=f"run process {version.name} ({version.ref}) at the {due.moment} of the "
                f"deadline {due.deadline.name} of {due.deadline.run_id}",
                autonomy_level=version.autonomy_level,
                steps=version.ordered(),
            )
        )
        await self._engine.submit(
            StartRun(
                org_unit=command.org_unit,
                plan=plan,
                work=version.work,
                budget=budget,
                process_version=version.ref,
                actor=placed.identity,
                tenant=tenant,
                inputs=inputs,
                run_id=run_id,
                trigger=trigger,
                actions=version.autonomy.action_levels,
            )
        )
