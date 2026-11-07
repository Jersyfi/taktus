"""Use case: Taktus changes a process within the frame its owner declares (UC-4.3, ADR-0255).

A changed bundle and the observation that led to it come in. The rule of
`domain/service/change.py` compares it with the active version. Within the frame, the bundle is
registered through the one registration a person's version goes through — its takeover
instructions included — acting for the identity that activated the version it replaces, with
`author: taktus`, the reason, and the record of the change: the observation, the predecessor,
every change in words. The ledger records `process.changed`. The replaced version stays
registered and unchanged; a person rolls back in one act (ADR-0091 §5).

Outside the frame, or where registration refuses the version, the bundle is a proposal that
carries the observation and every reason it is not a version, and nothing of it runs before a
person commissions it; the ledger records `process.change_proposed`. A bundle whose shape
cannot be read is refused with its findings, as registration refuses it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from taktus.components.process.application.service.proposals import Proposals, Propose
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
    read_bundle,
)
from taktus.components.process.domain.model import (
    ChangeRecord,
    InvalidProcess,
    Process,
    ProcessVersion,
    Proposal,
    RaiseRefused,
)
from taktus.components.process.domain.service import change
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

TAKTUS = "taktus"
"""Who made a change within the frame: Taktus itself, never a person."""
CHANGED = "process.changed"
PROPOSED = "process.change_proposed"


@dataclass(frozen=True)
class Observation:
    observed: Literal["failure", "interface", "run"]
    on: str
    """The run or the operation it was observed on."""
    said: str
    """What was observed, in words."""


@dataclass(frozen=True)
class ChangeProcess:
    tenant: Tenant
    process_id: str
    bundle: Mapping[str, Any]
    reason: str
    observation: Observation


@dataclass(frozen=True)
class Changed:
    version: ProcessVersion | None
    """The version registered within the frame; None where the change is a proposal."""
    proposal: Proposal | None
    """The proposal the change became; None where it is a version."""


class ChangeWithinFrame:
    def __init__(
        self,
        *,
        versions: Repository[ProcessVersion],
        processes: Repository[Process],
        work: UnitOfWork,
        register: RegisterProcessVersionHandler,
        proposals: Proposals,
        ledger: Ledger,
    ) -> None:
        self._versions = versions
        self._processes = processes
        self._work = work
        self._register = register
        self._proposals = proposals
        self._ledger = ledger

    async def execute(self, command: ChangeProcess) -> Changed:
        tenant = command.tenant
        async with self._work.transaction(tenant):
            process = await self._processes.get(tenant, command.process_id)
            active = (
                None
                if process is None or process.active_version is None
                else await self._versions.get(tenant, f"{process.id}@{process.active_version}")
            )
        if process is None or active is None:
            raise InvalidProcess(
                (f"{command.process_id} has no active version: a change needs one to change",)
            )
        after, refused = read_bundle(command.bundle)
        judged = change.verdict(active, after)
        record = ChangeRecord(
            observed=command.observation.observed,
            on=command.observation.on,
            said=command.observation.said,
            predecessor=active.ref,
            changes=judged.changes or ("nothing",),
        )
        reasons = [*judged.outside, *refused]
        if not reasons:
            bundle = {
                **command.bundle,
                "author": TAKTUS,
                "reason": command.reason,
                "change": record.model_dump(mode="json"),
            }
            try:
                version = await self._register.execute(
                    RegisterProcessVersion(bundle, tenant=tenant, by=process.activated_by)
                )
            except (InvalidProcess, RaiseRefused) as refusal:
                reasons.extend(refusal.findings)
            else:
                await self._record(tenant, CHANGED, version.ref, "within_frame")
                return Changed(version=version, proposal=None)
        proposal = await self._proposals.propose(
            Propose(
                tenant=tenant,
                process_id=command.process_id,
                bundle=command.bundle,
                by=TAKTUS,
                request=command.reason,
                change=record,
                findings=tuple(reasons),
            )
        )
        outcome = "outside_frame" if judged.outside else "not_registered"
        await self._record(tenant, PROPOSED, f"{command.process_id}@{proposal.version}", outcome)
        return Changed(version=None, proposal=proposal)

    async def _record(self, tenant: Tenant, kind: str, ref: str, outcome: str) -> None:
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=kind,
                    refs=LedgerRefs(tenant=tenant, process_version=ref),
                    outcome=outcome,
                ),
            )
