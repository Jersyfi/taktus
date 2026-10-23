"""Use cases of a stop scoped to an adapter (ADR-0138, UC-7.2): request it, confirm it once it
holds, show it, and lift it.

A request writes the stop and `stop.requested` in one transaction, by the person as actor, and
asks for no reason. While the stop is held, the run engine hands no step to the adapter, and
every runner asks a step inside it to stop at its boundary (`RunEngine.stops_held`). Nothing
here touches a run: the runs are their runners'.

`confirm` is the elected scheduler's on every tick, and the requesting surface's while it waits.
A stop holds once no run of the tenant is inside a step on the adapter. Its confirmation names
the runs it halted, and is recorded once: `stop.confirmed` is written first, which takes the
tenant's ledger lock, and the stop is read again under it, so that a second confirmation
meanwhile rolls this one back (as for a deadline, ADR-0133 §3).
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
    StopState,
)
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
    """The adapter named is not one a stop halts steps at: not a configured worker."""


class _Settled(Exception):
    """The stop was confirmed or lifted meanwhile: this transaction writes nothing."""


@dataclass(frozen=True)
class Holding:
    """Where a stop stands: the stop, and the runs still inside a step on its adapter."""

    stop: AdapterStop
    inside: tuple[str, ...]


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
    ) -> None:
        self._stops = stops
        self._runs = runs
        self._ledger = ledger
        self._objects = objects
        self._work = work
        self._clock = clock
        self._ids = ids
        self._stoppable = stoppable
        """The adapters a stop halts steps at: the configured workers (ADR-0138, where the
        promise ends). None: any adapter named, as a test wires it."""

    async def request(self, tenant: Tenant, adapter: str, actor: str) -> AdapterStop:
        """Stop every step the adapter serves. A stop of the same adapter already held is
        returned as it is: a second request by anyone adds nothing. Refused with
        `NotStoppable` for an adapter no step would be halted at."""
        if self._stoppable is not None and adapter not in self._stoppable:
            known = ", ".join(sorted(self._stoppable)) or "none"
            raise NotStoppable(
                f"{adapter!r} is not a configured worker; a stop halts steps at these: {known}"
            )
        now = self._clock.now()
        try:
            async with self._work.transaction(tenant):
                # The entry first: writing it takes the tenant's ledger lock, and the stops are
                # read under it, so that two requests at once make one stop.
                await self._ledger.record(
                    tenant,
                    Fact(
                        kind=REQUESTED,
                        refs=LedgerRefs(tenant=tenant, actor=actor),
                        adapter=adapter,
                        outcome="adapter",
                    ),
                )
                for held in await self._stops.list(tenant):
                    if held.held and held.adapter == adapter:
                        raise _Held(held)
                stop = AdapterStop(
                    id=self._ids.new("stp"),
                    tenant=tenant,
                    adapter=adapter,
                    requested_by=actor,
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
            return frozenset(s.adapter for s in await self._stops.list(tenant) if s.held)

    async def show(self, tenant: Tenant, stop_id: str) -> Holding:
        """The stop, confirmed first if it holds now, and the runs still inside its adapter."""
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
        """Steps are handed to the adapter again. The runs the stop halted stay halted: each
        is resumed by a person (UC-7.2 §3)."""
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

    async def _standing(self, tenant: Tenant, stop_id: str) -> Holding:
        stop = await self._get(tenant, stop_id)
        async with self._work.transaction(tenant):
            running = await self._runs.having(tenant, "state", RunState.RUNNING.value)
        inside = tuple(
            run.id
            for run in running
            if any(sr.adapter == stop.adapter and sr.state in INSIDE for sr in run.step_runs)
        )
        return Holding(stop, inside)

    async def _stopped(self, tenant: Tenant, stop: AdapterStop) -> tuple[str, ...]:
        """The runs the stop halted: halted with cause `stop`, at a step on its adapter that
        stopped at or after the request."""
        async with self._work.transaction(tenant):
            halted = await self._runs.having(tenant, "cause", Cause.STOP.value)
        return tuple(
            sorted(
                run.id
                for run in halted
                if run.state is RunState.HALTED
                and any(
                    sr.adapter == stop.adapter
                    and sr.state is StepState.STOPPED
                    and sr.finished_at is not None
                    and sr.finished_at >= stop.requested_at
                    for sr in run.step_runs
                )
            )
        )

    async def _confirm(self, tenant: Tenant, stop: AdapterStop) -> AdapterStop | None:
        stopped = await self._stopped(tenant, stop)
        now = self._clock.now()
        confirmation = {
            "kind": "stop.confirmation",
            "stop": stop.id,
            "adapter": stop.adapter,
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
                        refs=LedgerRefs(tenant=tenant, actor=stop.requested_by),
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
        return confirmed

    async def _get(self, tenant: Tenant, stop_id: str) -> AdapterStop:
        async with self._work.transaction(tenant):
            stop = await self._stops.get(tenant, stop_id)
        if stop is None:
            raise UnknownStop(stop_id)
        return stop


class _Held(Exception):
    def __init__(self, stop: AdapterStop) -> None:
        self.stop = stop
