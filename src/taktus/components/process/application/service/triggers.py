"""Use cases of the scheduler: which schedule triggers are due, and that a firing happened
(ADR-0035).

The scheduler asks for the due firings of a tenant, starts their runs, and records each firing
once its runs exist. Starting a run is not this component's: the composition root hands the
firing to the command and run components (`composition/triggers.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from taktus.components.process.domain.model import (
    Firing,
    Process,
    ProcessVersion,
    TriggerState,
)
from taktus.ports.persistence import Repository, Tenant, UnitOfWork


@dataclass(frozen=True)
class FindDueFirings:
    tenant: Tenant
    now: datetime


@dataclass(frozen=True)
class RecordFiring:
    tenant: Tenant
    firing: Firing
    runs: tuple[str, ...]
    at: datetime


class TriggersHandler:
    """Reads the active version of every process, arms a schedule trigger the first time it is
    seen, and answers the firings that are due. Records a firing when its runs exist."""

    def __init__(
        self,
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
        states: Repository[TriggerState],
        work: UnitOfWork,
    ) -> None:
        self._processes = processes
        self._versions = versions
        self._states = states
        self._work = work

    async def due(self, query: FindDueFirings) -> list[Firing]:
        tenant = query.tenant
        firings: list[Firing] = []
        async with self._work.transaction(tenant):
            for process in await self._processes.list(tenant):
                if process.active_version is None:
                    continue
                version = await self._versions.get(tenant, f"{process.id}@{process.active_version}")
                if version is None:
                    continue
                for trigger in version.triggers:
                    if trigger.schedule is None:
                        continue  # event triggers are not the scheduler's
                    key = TriggerState.key(process.id, trigger)
                    state = await self._states.get(tenant, key)
                    if state is None:
                        await self._states.put(
                            tenant,
                            TriggerState(
                                id=key,
                                process_id=process.id,
                                schedule=trigger.schedule,
                                armed_at=query.now,
                            ),
                        )
                        continue
                    slot = state.due(query.now)
                    if slot is not None:
                        firings.append(
                            Firing(version=version, trigger=trigger, slot=slot, state=state)
                        )
        return firings

    async def record(self, command: RecordFiring) -> TriggerState:
        """The firing's slot is recorded as fired, with its runs. A slot already recorded — by
        another scheduler that fired it too — is left as it is."""
        tenant = command.tenant
        firing = command.firing
        async with self._work.transaction(tenant):
            state = await self._states.get(tenant, firing.state.id) or firing.state
            if state.fired_slot is not None and state.fired_slot >= firing.slot:
                return state
            state = state.fired(firing.slot, command.at, command.runs)
            await self._states.put(tenant, state)
        return state
