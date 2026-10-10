"""Use case: a process is switched off (UC-13.6 §2: nothing Taktus produces is compulsory).

A switched-off process has no active version. Its schedule triggers no longer fire and its
event triggers start nothing (ADR-0035, ADR-0048), because both read the active version and
find none. Its versions stay: nothing is deleted without asking, and registering
a version again switches it back on. A run already started is not stopped by this; it ends as
it would have.

The act is recorded in the ledger as `process.deactivated`, with the version that was active
and the identity that switched it off. Switching off a process that is off already changes
nothing and records nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

from taktus.components.process.domain.model import Process
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

DEACTIVATED = "process.deactivated"


@dataclass(frozen=True)
class DeactivateProcess:
    tenant: Tenant
    process_id: str
    by: str
    """The identity that switches it off."""


@dataclass(frozen=True)
class Deactivated:
    process: Process
    """The process as it is now: without an active version."""
    was: str | None
    """The version that was active, as `<process>@<version>`; None when it was off already."""


class UnknownProcess(LookupError):
    def __init__(self, tenant: str, process_id: str) -> None:
        super().__init__(f"tenant {tenant!r} has no process {process_id!r}")


class DeactivateProcessHandler:
    def __init__(self, processes: Repository[Process], work: UnitOfWork, ledger: Ledger) -> None:
        self._processes = processes
        self._work = work
        self._ledger = ledger

    async def execute(self, command: DeactivateProcess) -> Deactivated:
        async with self._work.transaction(command.tenant):
            process = await self._processes.get(command.tenant, command.process_id)
            if process is None:
                raise UnknownProcess(command.tenant, command.process_id)
            if process.active_version is None:
                return Deactivated(process=process, was=None)
            was = f"{process.id}@{process.active_version}"
            off = process.model_copy(
                update={"active_version": None, "activated_by": None, "activated_at": None}
            )
            await self._processes.put(command.tenant, off)
            await self._ledger.record(
                command.tenant,
                Fact(
                    kind=DEACTIVATED,
                    refs=LedgerRefs(tenant=command.tenant, process_version=was, actor=command.by),
                    outcome="deactivated",
                ),
            )
        return Deactivated(process=off, was=was)
