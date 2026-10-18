"""Use case: when a run of each process is expected (ADR-0107 §1).

The watcher of expected runs asks it on every look. For every process with an active version,
it answers the slots a run was expected at — the latest of each expected schedule at or before
the moment asked about, when it lies after the version was activated — and the version's gap and
bound. Whether the run happened is not this component's: the governance component reads the
ledger (`composition/expected_runs.py`).

A switched-off process has no active version and expects nothing (UC-13.6). A version activated
before activation times were recorded (ADR-0048 §6) is left out: when it was activated is not
known, so no slot can be said to lie after it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.process.domain.service import schedule
from taktus.ports.persistence import Repository, Tenant, UnitOfWork


@dataclass(frozen=True)
class Expected:
    process_id: str
    process_version: str
    activated_at: datetime
    slots: tuple[tuple[str, datetime], ...]
    """Each expected schedule with its latest slot at or before the moment asked about, after
    the activation."""
    gap: timedelta | None
    bound: timedelta | None


class ExpectationsHandler:
    def __init__(
        self,
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
        work: UnitOfWork,
    ) -> None:
        self._processes = processes
        self._versions = versions
        self._work = work

    async def expected(self, tenant: Tenant, slots_at: datetime) -> list[Expected]:
        """`slots_at` is the moment the latest slot is looked for: the watcher's now less the
        tenant's grace period."""
        found: list[Expected] = []
        async with self._work.transaction(tenant):
            for process in await self._processes.list(tenant):
                if process.active_version is None or process.activated_at is None:
                    continue
                version = await self._versions.get(tenant, f"{process.id}@{process.active_version}")
                if version is None:
                    continue
                expect = version.expect
                gap = None if expect is None else expect.gap
                bound = None if expect is None else expect.bound
                slots: list[tuple[str, datetime]] = []
                for expression in version.expected_schedules:
                    slot = schedule.parse(expression).latest(slots_at)
                    if slot is not None and slot > process.activated_at:
                        slots.append((expression, slot))
                if not version.expected_schedules and gap is None and bound is None:
                    continue  # nothing is expected of it
                found.append(
                    Expected(
                        process_id=process.id,
                        process_version=version.ref,
                        activated_at=process.activated_at,
                        slots=tuple(slots),
                        gap=gap,
                        bound=bound,
                    )
                )
        return found
