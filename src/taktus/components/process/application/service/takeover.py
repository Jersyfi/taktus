"""Use case: a process's takeover instructions are read, and a trial of them is recorded
(UC-6.3 §2, ADR-0180 §3).

A person who ran the process by hand from the instructions alone records the trial: the role
that ran it, whether they could, and what was missing. The record names the version that was
active then, and is the ledger entry `takeover.trial`, outcome `passed` or `failed`, with the
person as its actor for the audit only. A trial names a role, never a person; nothing here
counts trials by person (principle 14).

The instructions read are the active version's, with each step's skills as `skills` gives them:
the composition answers that from the catalog, at their version in production (ADR-0180 §1).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from taktus.components.process.domain.model import (
    InvalidProcess,
    Process,
    ProcessVersion,
    TakeoverTrial,
)
from taktus.components.process.domain.service import takeover as instructed
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

TRIAL = "takeover.trial"
"""A person recorded a trial of a version's takeover instructions (ADR-0180 §3)."""

type Skills = Callable[
    [Tenant, ProcessVersion], Awaitable[Mapping[str, Sequence[Mapping[str, Any]]]]
]
"""Per step, the skills it uses at their version in production."""


@dataclass(frozen=True)
class RecordTrial:
    tenant: Tenant
    process_id: str
    role: str
    passed: bool
    missing: tuple[str, ...] = ()
    by: str | None = None
    """The person who records it: the ledger entry's actor, never a field of the trial."""


class TakeoverTrials:
    def __init__(
        self,
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
        trials: Repository[TakeoverTrial],
        *,
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
        identifiers: Identifiers,
        skills: Skills | None = None,
    ) -> None:
        self._processes = processes
        self._versions = versions
        self._trials = trials
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._identifiers = identifiers
        self._skills = skills

    async def active(self, tenant: Tenant, process_id: str) -> ProcessVersion | None:
        async with self._work.transaction(tenant):
            return await self._active(tenant, process_id)

    async def _active(self, tenant: Tenant, process_id: str) -> ProcessVersion | None:
        process = await self._processes.get(tenant, process_id)
        if process is None or process.active_version is None:
            return None
        return await self._versions.get(tenant, f"{process_id}@{process.active_version}")

    async def record(self, command: RecordTrial) -> TakeoverTrial:
        """The trial, stored with the active version and recorded; `InvalidProcess` where the
        process has no active version or its version carries no instructions."""
        tenant = command.tenant
        async with self._work.transaction(tenant):
            version = await self._active(tenant, command.process_id)
            if version is None:
                raise InvalidProcess((f"the process {command.process_id!r} has no active version",))
            if version.takeover is None:
                raise InvalidProcess(
                    (
                        f"{version.ref} carries no takeover instructions to try; register a "
                        "version that does",
                    )
                )
            trial = TakeoverTrial(
                id=self._identifiers.new("tkt"),
                process_id=version.process_id,
                process_version=version.ref,
                role=command.role,
                passed=command.passed,
                missing=tuple(m.strip() for m in command.missing if m.strip()),
                at=self._clock.now(),
            )
            await self._trials.put(tenant, trial)
            await self._ledger.record(
                tenant,
                Fact(
                    kind=TRIAL,
                    refs=LedgerRefs(tenant=tenant, process_version=version.ref, actor=command.by),
                    outcome="passed" if trial.passed else "failed",
                ),
            )
        return trial

    async def trials(self, tenant: Tenant, process_id: str) -> list[TakeoverTrial]:
        async with self._work.transaction(tenant):
            return [t for t in await self._trials.list(tenant) if t.process_id == process_id]

    async def untried(self, tenant: Tenant, version: ProcessVersion) -> bool:
        """Whether the version runs at level 3 or 4 without a passed trial on it."""
        if version.autonomy.level < 3:
            return False
        async with self._work.transaction(tenant):
            trials = await self._trials.list(tenant)
        return instructed.untried(version.autonomy.level, trials, version.ref)

    async def read(self, tenant: Tenant, process_id: str) -> dict[str, Any] | None:
        """The active version's instructions as a person reads them, its trials and whether it
        is untried; None where the process has no active version."""
        version = await self.active(tenant, process_id)
        if version is None:
            return None
        trials = await self.trials(tenant, process_id)
        skills = {} if self._skills is None else await self._skills(tenant, version)
        return {
            "process_version": version.ref,
            "level": version.autonomy.level,
            "instructions": None
            if version.takeover is None
            else instructed.rendered(version.takeover, version.ordered(), skills),
            "trials": [t.document() for t in trials],
            "untried": instructed.untried(version.autonomy.level, trials, version.ref),
        }

    async def of_step(
        self, tenant: Tenant, process_version: str, step_id: str
    ) -> dict[str, Any] | None:
        """One step's entry of a version's instructions, with its skills, as a person who
        takes the step over reads it (ADR-0180 §4); None where the version carries none."""
        async with self._work.transaction(tenant):
            version = await self._versions.get(tenant, process_version)
        if version is None or version.takeover is None or step_id not in version.takeover.steps:
            return None
        skills = {} if self._skills is None else await self._skills(tenant, version)
        return instructed.step_document(
            step_id, version.takeover.steps[step_id], skills.get(step_id, ())
        )
