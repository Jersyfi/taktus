"""Use case: the configuration a commissioned plan calls for, carried out in the organisation's
tools (ADR-0278, UC-1.3).

`prepare` takes the changes of a commissioned plan, in their order. `carry_out` makes them one
after another, each at its own boundary:

1. The target's connector must declare the change's operation as an outward one; otherwise the
   target cannot do what was planned, a deviation.
2. What undoing it requires is stated — the state before, read from the target, or the action
   that reverses it — and recorded, `configuration.undo_recorded`, before anything is sent. A
   change whose undoing cannot be stated is handed to a person as its instruction.
3. The change is sent with the credential of the identity the plan was commissioned for, and its
   effect is recorded as an egress entry naming the target and the digest of what changed.
4. The output is held against what the plan expects, and every record the target reports
   against the kinds the plan names. Anything else is a deviation.

A deviation halts the configuration at that change, records `configuration.deviated`, and
answers with the options; nothing is substituted. A change that was sent and whose operation
the target cannot recognise a repeat of is never sent again, also not after a restart
(ADR-0024): it is handed to a person to check.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from taktus.components.command.domain.model.configuration import (
    Action,
    ChangeState,
    ConfigurationChange,
    Halted,
    Undo,
)
from taktus.ports.clock import Clock
from taktus.ports.connector import (
    ActionConnector,
    CallContext,
    CallFailed,
    Operation,
    idempotency_key,
)
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.ports.worker import CredentialReference
from taktus.shared.v1 import LedgerRefs, Plan, PlanStatus

UNDO_RECORDED = "configuration.undo_recorded"
DEVIATED = "configuration.deviated"
HANDED = "configuration.handed"
EGRESS = "egress.write"

OPTIONS = (
    "change the plan so that the target can do it, and commission it again",
    "make this change by hand from its instruction, and let the configuration go on",
    "undo what was configured so far, from the recorded undoing",
)


class Targets(Protocol):
    def connector(self, capability: str) -> ActionConnector | None:
        """The connector serving the capability, or None where none is configured."""
        ...


class Credentials(Protocol):
    async def of(
        self, tenant: Tenant, identity: str, capability: str
    ) -> tuple[CredentialReference, ...] | None:
        """The identity's own credential for the capability, by name; None where the identity
        has none, and the change is then handed to a person."""
        ...


class ConfigurationError(Exception):
    pass


def _digest(document: Any) -> str:
    canonical = json.dumps(document, ensure_ascii=False, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class Configure:
    def __init__(
        self,
        changes: Repository[ConfigurationChange],
        plans: Repository[Plan],
        targets: Targets,
        credentials: Credentials,
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._changes = changes
        self._plans = plans
        self._targets = targets
        self._credentials = credentials
        self._ledger = ledger
        self._work = work
        self._clock = clock

    async def prepare(
        self, tenant: Tenant, plan_id: str, changes: Sequence[Mapping[str, Any]]
    ) -> list[ConfigurationChange]:
        """The plan's changes, in order. Only a commissioned plan is configured (UC-1.2)."""
        now = self._clock.now()
        async with self._work.transaction(tenant):
            plan = await self._plans.get(tenant, plan_id)
            if plan is None or plan.status is not PlanStatus.COMMISSIONED or not plan.commissioned:
                raise ConfigurationError(f"plan {plan_id!r} is not commissioned")
            made = [
                ConfigurationChange.model_validate(
                    {
                        **change,
                        "id": f"{plan_id}#{n}",
                        "tenant": tenant,
                        "plan_id": plan_id,
                        "position": n,
                        "identity": plan.commissioned.by,
                        "changed_at": now,
                    }
                )
                for n, change in enumerate(changes, start=1)
            ]
            for change in made:
                await self._changes.put(tenant, change)
        return made

    async def of_plan(self, tenant: Tenant, plan_id: str) -> list[ConfigurationChange]:
        async with self._work.transaction(tenant):
            listed = [c for c in await self._changes.list(tenant) if c.plan_id == plan_id]
        return sorted(listed, key=lambda c: c.position)

    async def carry_out(self, tenant: Tenant, plan_id: str) -> Halted | None:
        """Every change not yet applied, in order; the first halt ends the call. None when
        every change is applied."""
        for change in await self.of_plan(tenant, plan_id):
            if change.state is ChangeState.APPLIED:
                continue
            if change.state in (ChangeState.DEVIATED, ChangeState.HANDED):
                return Halted(
                    change_id=change.id,
                    state=change.state,
                    reason=change.deviation or change.instruction,
                    options=OPTIONS,
                )
            halted = await self._one(change)
            if halted is not None:
                return halted
        return None

    async def _one(self, change: ConfigurationChange) -> Halted | None:
        connector = self._targets.connector(change.capability)
        operation = None if connector is None else await self._declared(connector, change.action)
        if connector is None or operation is None or not operation.outward:
            return await self._deviate(
                change,
                f"the target behind {change.capability} cannot do {change.action.operation}",
            )
        if change.state is ChangeState.UNDO_RECORDED and not operation.repeatable:
            # It may have been sent: an operation without a recognised repeat is never sent
            # twice (ADR-0024).
            return await self._hand(
                change,
                "it may have been made before a restart, and the target cannot recognise a "
                f"repeat. Check the target, then: {change.instruction}",
            )
        credentials = await self._credentials.of(change.tenant, change.identity, change.capability)
        if credentials is None:
            return await self._hand(
                change, f"{change.identity} holds no credential for it. {change.instruction}"
            )
        if change.state is ChangeState.PLANNED:
            undo = await self._undo(connector, change, credentials)
            if undo is None:
                return await self._hand(
                    change, f"what would undo it cannot be stated. {change.instruction}"
                )
            change = change.model_copy(
                update={
                    "state": ChangeState.UNDO_RECORDED,
                    "undo": undo,
                    "changed_at": self._clock.now(),
                }
            )
            async with self._work.transaction(change.tenant):
                await self._changes.put(change.tenant, change)
                await self._fact(change, UNDO_RECORDED, "recorded", _digest(undo.document()))
        try:
            result = await connector.call(
                change.action.operation,
                self._context(change, credentials, "apply"),
                change.action.input,
            )
        except CallFailed as failed:
            return await self._deviate(change, f"the target refused it: {failed.error.detail}")
        output = dict(result.output)
        records = result.effect.records or ()
        async with self._work.transaction(change.tenant):
            await self._fact(
                change,
                EGRESS,
                "replayed" if result.effect.replayed else "acted",
                result.effect.content_digest or _digest(output),
                adapter=change.capability,
            )
            applied = change.model_copy(
                update={
                    "state": ChangeState.APPLIED,
                    "output": output,
                    "changed_at": self._clock.now(),
                }
            )
            await self._changes.put(change.tenant, applied)
        differs = sorted(k for k, v in change.expects.items() if output.get(k) != v)
        if differs:
            return await self._deviate(
                applied, f"the target holds otherwise than planned: {', '.join(differs)}"
            )
        unnamed = sorted(
            {r.kind for r in records if change.touches and r.kind not in change.touches}
        )
        if unnamed:
            return await self._deviate(
                applied, f"the target changed what the plan does not name: {', '.join(unnamed)}"
            )
        return None

    async def _declared(self, connector: ActionConnector, action: Action) -> Operation | None:
        declared = await connector.capabilities()
        return next((o for o in declared.operations if o.name == action.operation), None)

    async def _undo(
        self,
        connector: ActionConnector,
        change: ConfigurationChange,
        credentials: tuple[CredentialReference, ...],
    ) -> Undo | None:
        before = None
        if change.read_before is not None:
            read = await self._declared(connector, change.read_before)
            if read is not None and not read.outward:
                try:
                    answered = await connector.call(
                        change.read_before.operation,
                        self._context(change, credentials, "before"),
                        change.read_before.input,
                    )
                except CallFailed:
                    answered = None
                before = None if answered is None else dict(answered.output)
        if before is None and change.reverse is None:
            return None
        return Undo(before=before, reverse=change.reverse)

    def _context(
        self, change: ConfigurationChange, credentials: tuple[CredentialReference, ...], what: str
    ) -> CallContext:
        run = "cfg_" + change.plan_id.replace("@", "_")
        step = f"change-{change.position}-{what}"
        return CallContext(
            tenant=change.tenant,
            identity=change.identity,
            run_id=run,
            step_id=step,
            attempt=1,
            idempotency_key=idempotency_key(run, step, 1),
            credentials=credentials,
        )

    async def _deviate(self, change: ConfigurationChange, reason: str) -> Halted:
        return await self._halt(change, ChangeState.DEVIATED, DEVIATED, reason)

    async def _hand(self, change: ConfigurationChange, reason: str) -> Halted:
        return await self._halt(change, ChangeState.HANDED, HANDED, reason)

    async def _halt(
        self, change: ConfigurationChange, state: ChangeState, kind: str, reason: str
    ) -> Halted:
        halted = change.model_copy(
            update={"state": state, "deviation": reason, "changed_at": self._clock.now()}
        )
        async with self._work.transaction(change.tenant):
            await self._changes.put(change.tenant, halted)
            await self._fact(halted, kind, str(state), _digest({"reason": reason}))
        return Halted(change_id=change.id, state=state, reason=reason, options=OPTIONS)

    async def _fact(
        self,
        change: ConfigurationChange,
        kind: str,
        outcome: str,
        digest: str,
        adapter: str | None = None,
    ) -> None:
        await self._ledger.record(
            change.tenant,
            Fact(
                kind=kind,
                refs=LedgerRefs(
                    tenant=change.tenant,
                    plan_id=change.plan_id,
                    step_id=f"change-{change.position}",
                    actor=change.identity,
                ),
                adapter=adapter,
                outcome=outcome,
                content_digest=digest,
            ),
        )
