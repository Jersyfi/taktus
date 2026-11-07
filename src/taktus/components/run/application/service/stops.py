"""Use cases of a stop of a tenant's runs (ADR-0138, ADR-0256, UC-7.2): request it — of an
adapter, a process, the tenant or every tenant served — confirm it once it holds, show it, and
lift it.

A request writes the stop and `stop.requested` in one transaction, whose outcome is the scope,
and asks a person for no reason. A rule's request names the rules that fired and the incident
that carries the facts they read; the entry's actor is none, since no person acted (ADR-0256 §3).
While a stop is held, the run engine hands no step on under its scope: a stop of an adapter
keeps steps from that adapter, calls no stopped connector and asks no stopped model; a stop of
a process or the tenant halts each run it covers at its next boundary. Every runner asks a step
inside a stopped scope to stop at its boundary (`RunEngine.stops_held`). Nothing here touches a
run: the runs are their runners'.

`confirm` is the elected scheduler's on every tick, and the requesting surface's while it waits.
A stop holds once no run it covers is inside a step. Its confirmation names the runs it halted,
and is recorded once: `stop.confirmed` is written first, which takes the tenant's ledger lock,
and the stop is read again under it, so that a second confirmation meanwhile rolls this one back
(as for a deadline, ADR-0133 §3).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from taktus.components.run.domain.model import (
    AdapterStop,
    Cause,
    Run,
    RunState,
    StepState,
    StopScope,
    StopState,
)
from taktus.components.run.domain.model.stop import process_of
from taktus.components.run.ports.stop_follow_up import ConfirmedStop, StopFollowUp
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Queried, Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

REQUESTED = "stop.requested"
CONFIRMED = "stop.confirmed"
LIFTED = "stop.lifted"

INSIDE = (StepState.ADMITTED, StepState.RUNNING)
"""The states of a step that is inside its adapter, or about to be handed to it."""


class UnknownStop(LookupError):
    """No stop of the tenant has the identifier named."""


class NotStoppable(ValueError):
    """The adapter named is not one a stop halts steps at: not a configured worker, connector
    or model."""


class _Settled(Exception):
    """The stop was confirmed or lifted meanwhile: this transaction writes nothing."""


@dataclass(frozen=True)
class Holding:
    """Where a stop stands: the stop, and the runs it covers still inside a step."""

    stop: AdapterStop
    inside: tuple[str, ...]


@dataclass(frozen=True)
class _Scope:
    scope: StopScope
    adapter: str | None = None
    process: str | None = None
    rule: str | None = None
    incident: str | None = None

    def same(self, stop: AdapterStop) -> bool:
        return (stop.scope, stop.adapter, stop.process) == (self.scope, self.adapter, self.process)


class Stops:
    def __init__(
        self,
        stops: Repository[AdapterStop],
        runs: Queried[Run],
        ledger: Ledger,
        objects: ObjectStore,
        work: UnitOfWork,
        clock: Clock,
        ids: Identifiers,
        stoppable: frozenset[str] | None = None,
        followed: StopFollowUp | None = None,
    ) -> None:
        self._followed = followed
        """What follows a person's stop once it holds: its incident and situation package
        (ADR-0280 §1). None: the confirmation alone, as a test wires it."""
        self._stops = stops
        self._runs = runs
        self._ledger = ledger
        self._objects = objects
        self._work = work
        self._clock = clock
        self._ids = ids
        self._stoppable = stoppable
        """The adapters a stop halts steps at: the configured workers, connectors and models
        (ADR-0138, where the promise ends). None: any adapter named, as a test wires it."""

    async def request(self, tenant: Tenant, adapter: str, actor: str) -> AdapterStop:
        """Stop every step the adapter serves. A stop of the same adapter already held is
        returned as it is: a second request by anyone adds nothing. Refused with
        `NotStoppable` for an adapter no step would be halted at."""
        if self._stoppable is not None and adapter not in self._stoppable:
            known = ", ".join(sorted(self._stoppable)) or "none"
            raise NotStoppable(
                f"{adapter!r} is not a configured adapter; a stop halts steps at these: {known}"
            )
        return await self._request(tenant, _Scope(StopScope.ADAPTER, adapter=adapter), actor)

    async def request_process(
        self,
        tenant: Tenant,
        process: str,
        actor: str | None,
        *,
        rule: str | None = None,
        incident: str | None = None,
    ) -> AdapterStop:
        """Stop every run of the process at its next boundary (ADR-0256 §1). A person's stop
        names the person; a rule's names the rules that fired and the incident whose facts
        they read, and no actor (ADR-0256 §3). A held stop of the process is returned as it
        is."""
        scope = _Scope(StopScope.PROCESS, process=process, rule=rule, incident=incident)
        return await self._request(tenant, scope, actor)

    async def request_tenant(self, tenant: Tenant, actor: str) -> AdapterStop:
        """Stop every run of the tenant at its next boundary (ADR-0256 §1)."""
        return await self._request(tenant, _Scope(StopScope.TENANT), actor)

    async def request_everywhere(self, tenants: Sequence[Tenant], actor: str) -> list[AdapterStop]:
        """The instance's stop: a stop of each tenant it serves, requested by the same person
        (ADR-0256 §2). Each is confirmed on its own, in its tenant."""
        return [await self.request_tenant(tenant, actor) for tenant in dict.fromkeys(tenants)]

    async def _request(self, tenant: Tenant, scope: _Scope, actor: str | None) -> AdapterStop:
        if (actor is None) == (scope.rule is None):
            raise ValueError("a stop is requested by a person or by a rule, never both")
        now = self._clock.now()
        digest = None
        if scope.rule is not None or scope.process is not None:
            # What was stopped and why, where the entry's columns cannot say it: the process,
            # and for a rule's stop the rules that fired; their facts are the incident's.
            request = {
                "kind": "stop.request",
                "scope": scope.scope.value,
                "process": scope.process,
                "rule": scope.rule,
                "incident": scope.incident,
            }
            digest = await self._objects.put(
                json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
            )
        try:
            async with self._work.transaction(tenant):
                # The entry first: writing it takes the tenant's ledger lock, and the stops are
                # read under it, so that two requests at once make one stop.
                await self._ledger.record(
                    tenant,
                    Fact(
                        kind=REQUESTED,
                        refs=LedgerRefs(tenant=tenant, actor=actor, incident_id=scope.incident),
                        adapter=scope.adapter,
                        outcome=scope.scope.value,
                        content_digest=digest,
                    ),
                )
                for held in await self._stops.list(tenant):
                    if held.held and scope.same(held):
                        raise _Held(held)
                stop = AdapterStop(
                    id=self._ids.new("stp"),
                    tenant=tenant,
                    scope=scope.scope,
                    adapter=scope.adapter,
                    process=scope.process,
                    requested_by=actor if actor is not None else f"rule:{scope.rule}",
                    rule=scope.rule,
                    incident=scope.incident,
                    requested_at=now,
                    created_at=now,
                )
                await self._stops.put(tenant, stop)
        except _Held as already:
            return already.stop
        return stop

    async def held(self, tenant: Tenant) -> frozenset[str]:
        """The adapters of the tenant that no step is handed to."""
        async with self._work.transaction(tenant):
            return frozenset(
                s.adapter
                for s in await self._stops.list(tenant)
                if s.held and s.adapter is not None
            )

    async def covering(self, tenant: Tenant, process: str) -> AdapterStop | None:
        """The held stop that halts a run of the process at its next boundary — of the
        process, or of the tenant — the oldest first; None while none does."""
        async with self._work.transaction(tenant):
            stops = list(await self._stops.list(tenant))
        covering = sorted((s for s in stops if s.covers(process)), key=lambda s: s.requested_at)
        return covering[0] if covering else None

    async def show(self, tenant: Tenant, stop_id: str) -> Holding:
        """The stop, confirmed first if it holds now, and the runs still inside its scope."""
        holding = await self._standing(tenant, stop_id)
        if holding.stop.state is StopState.HOLDING and not holding.inside:
            confirmed = await self._confirm(tenant, holding.stop)
            return Holding(confirmed or await self._get(tenant, stop_id), ())
        return holding

    async def every(self, tenant: Tenant) -> Sequence[AdapterStop]:
        """Every stop of the tenant, the oldest first."""
        async with self._work.transaction(tenant):
            stops = list(await self._stops.list(tenant))
        return sorted(stops, key=lambda s: (s.requested_at, s.id))

    async def confirm(self, tenant: Tenant) -> list[AdapterStop]:
        """Confirm every stop of the tenant that holds now; the stops confirmed by this call."""
        confirmed = []
        for stop in await self.every(tenant):
            if stop.state is not StopState.HOLDING:
                continue
            if (await self._standing(tenant, stop.id)).inside:
                continue
            done = await self._confirm(tenant, stop)
            if done is not None:
                confirmed.append(done)
        return confirmed

    async def lift(self, tenant: Tenant, stop_id: str, actor: str) -> AdapterStop:
        """Steps are handed on again. The runs the stop halted stay halted: each is resumed by
        a person (UC-7.2 §3)."""
        stop = await self._get(tenant, stop_id)
        if not stop.held:
            return stop
        now = self._clock.now()
        try:
            async with self._work.transaction(tenant):
                await self._ledger.record(
                    tenant,
                    Fact(
                        kind=LIFTED,
                        refs=LedgerRefs(tenant=tenant, actor=actor),
                        adapter=stop.adapter,
                        outcome="lifted",
                    ),
                )
                current = await self._stops.get(tenant, stop_id)
                if current is None or not current.held:
                    raise _Settled
                lifted = current.model_copy(
                    update={"state": StopState.LIFTED, "lifted_by": actor, "lifted_at": now}
                )
                await self._stops.put(tenant, lifted)
        except _Settled:
            return await self._get(tenant, stop_id)
        return lifted

    # --- the stop's standing ----------------------------------------------------------------

    @staticmethod
    def _in_scope(stop: AdapterStop, run: Run) -> bool:
        if stop.scope is StopScope.ADAPTER:
            return True
        return stop.scope is StopScope.TENANT or process_of(run.process_version) == stop.process

    async def _standing(self, tenant: Tenant, stop_id: str) -> Holding:
        stop = await self._get(tenant, stop_id)
        async with self._work.transaction(tenant):
            running = await self._runs.having(tenant, "state", RunState.RUNNING.value)
        inside = tuple(
            run.id
            for run in running
            if self._in_scope(stop, run)
            and any(
                sr.state in INSIDE
                and (stop.scope is not StopScope.ADAPTER or sr.adapter == stop.adapter)
                for sr in run.step_runs
            )
        )
        return Holding(stop, inside)

    async def _stopped(self, tenant: Tenant, stop: AdapterStop) -> tuple[str, ...]:
        """The runs the stop halted: halted with cause `stop`, under its scope, at or after the
        request — at a step on its adapter that stopped then, or, for a stop of a process or
        the tenant, at the boundary the stop names or at a step that stopped then."""
        async with self._work.transaction(tenant):
            halted = await self._runs.having(tenant, "cause", Cause.STOP.value)

        def by_this(run: Run) -> bool:
            if run.state is not RunState.HALTED or not self._in_scope(stop, run):
                return False
            if stop.scope is not StopScope.ADAPTER and stop.id in (run.reason or ""):
                return True
            return any(
                (stop.scope is not StopScope.ADAPTER or sr.adapter == stop.adapter)
                and sr.state is StepState.STOPPED
                and sr.finished_at is not None
                and sr.finished_at >= stop.requested_at
                for sr in run.step_runs
            )

        return tuple(sorted(run.id for run in halted if by_this(run)))

    async def _confirm(self, tenant: Tenant, stop: AdapterStop) -> AdapterStop | None:
        stopped = await self._stopped(tenant, stop)
        now = self._clock.now()
        confirmation = {
            "kind": "stop.confirmation",
            "stop": stop.id,
            "scope": stop.scope.value,
            "adapter": stop.adapter,
            "process": stop.process,
            "rule": stop.rule,
            "incident": stop.incident,
            "to": stop.requested_by,
            "requested_at": stop.requested_at.isoformat(),
            "confirmed_at": now.isoformat(),
            "stopped": list(stopped),
        }
        digest = await self._objects.put(
            json.dumps(confirmation, sort_keys=True, separators=(",", ":")).encode()
        )
        try:
            async with self._work.transaction(tenant):
                await self._ledger.record(
                    tenant,
                    Fact(
                        kind=CONFIRMED,
                        refs=LedgerRefs(
                            tenant=tenant,
                            actor=None if stop.rule is not None else stop.requested_by,
                            incident_id=stop.incident,
                        ),
                        adapter=stop.adapter,
                        outcome="held" if stopped else "empty",
                        content_digest=digest,
                    ),
                )
                current = await self._stops.get(tenant, stop.id)
                if current is None or current.state is not StopState.HOLDING:
                    raise _Settled
                confirmed = current.model_copy(
                    update={"state": StopState.CONFIRMED, "confirmed_at": now, "stopped": stopped}
                )
                await self._stops.put(tenant, confirmed)
        except _Settled:
            return None
        if self._followed is not None and confirmed.rule is None:
            # A rule's stop is carried by the rule's own incident (ADR-0256 §3).
            await self._followed.confirmed(tenant, await self._confirmation(tenant, confirmed))
        return confirmed

    async def _confirmation(self, tenant: Tenant, stop: AdapterStop) -> ConfirmedStop:
        processes = {stop.process} if stop.process is not None else set()
        async with self._work.transaction(tenant):
            for run_id in stop.stopped:
                run = await self._runs.get(tenant, run_id)
                if run is not None:
                    processes.add(process_of(run.process_version))
        return ConfirmedStop(
            stop=stop.id,
            scope=stop.scope.value,
            target=stop.target,
            requested_at=stop.requested_at,
            confirmed_at=stop.confirmed_at or stop.requested_at,
            stopped=stop.stopped,
            processes=tuple(sorted(processes)),
        )

    async def _get(self, tenant: Tenant, stop_id: str) -> AdapterStop:
        async with self._work.transaction(tenant):
            stop = await self._stops.get(tenant, stop_id)
        if stop is None:
            raise UnknownStop(stop_id)
        return stop


class _Held(Exception):
    def __init__(self, stop: AdapterStop) -> None:
        self.stop = stop
