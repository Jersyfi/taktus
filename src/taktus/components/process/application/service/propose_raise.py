"""Use case: Taktus proposes raising a process's autonomy level, with the evidence.

A proposal reads the quality history of the process's active version from the ledger and says
whether it meets what the version names (`autonomy.history`). It records `autonomy.proposed`,
with no actor, since Taktus acted on its own. It never stores a version and never changes a
level: a raise is a new version registered with a person's approval (`register_version.py`,
ADR-0026, ADR-0039). Which conditions of `toward_next` beyond the history are met is not
judged here.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import Field

from taktus.components.process.domain.model import InvalidProcess, Process, ProcessVersion
from taktus.components.process.domain.service.autonomy import QualityHistory, history
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Autonomy, LedgerRefs, Value


@dataclass(frozen=True)
class ProposeRaise:
    tenant: Tenant
    process_id: str


class RaiseProposal(Value):
    """What a person reads before approving a raise: the version, its statement, the history
    it needs and the history it has."""

    process_version: str = Field(min_length=1)
    autonomy: Autonomy
    quality: QualityHistory
    required: int | None = None
    """How many clean runs in a row the version names for a raise; None when it names none."""
    evidenced: bool
    """Whether the history meets what the version names. A raise still needs a person's
    approval either way."""


class ProposeRaiseHandler:
    def __init__(
        self,
        versions: Repository[ProcessVersion],
        processes: Repository[Process],
        work: UnitOfWork,
        ledger: Ledger,
    ) -> None:
        self._versions = versions
        self._processes = processes
        self._work = work
        self._ledger = ledger

    async def execute(self, command: ProposeRaise) -> RaiseProposal:
        async with self._work.transaction(command.tenant):
            process = await self._processes.get(command.tenant, command.process_id)
            active = (
                None
                if process is None or process.active_version is None
                else await self._versions.get(
                    command.tenant, f"{process.id}@{process.active_version}"
                )
            )
            if active is None:
                raise InvalidProcess(
                    (f"no active version of {command.process_id!r} is registered",)
                )
            quality = history(await self._ledger.entries(command.tenant), active.process_id)
            required = active.autonomy.history
            evidenced = required is not None and quality.clean >= required
            await self._ledger.record(
                command.tenant,
                Fact(
                    kind="autonomy.proposed",
                    refs=LedgerRefs(tenant=command.tenant, process_version=active.ref),
                    outcome="evidenced" if evidenced else "not_evidenced",
                ),
            )
        return RaiseProposal(
            process_version=active.ref,
            autonomy=active.autonomy,
            quality=quality,
            required=required,
            evidenced=evidenced,
        )
