"""Use case: a process version leaves Taktus as one package of plain files (UC-8.9, ADR-0285).

The package is the version's definition, its prompts, its takeover instructions, what an
instance must provide for it, and the skills its steps use at their version in production. It
is written by the rule of `domain/service/package.py`; the composition answers the skills from
the catalog. The export is recorded as `process.exported` with the package's digest, by the
person who asked: what left the instance stays answerable.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable, Mapping

from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.process.domain.service import package
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

EXPORTED = "process.exported"

type SkillFiles = Callable[[Tenant, ProcessVersion], Awaitable[Mapping[str, Mapping[str, bytes]]]]
"""Per skill a step uses, its directory at its version in production, by relative path."""


class UnknownVersion(Exception):
    """No such process, or no such version of it."""


class ProcessPackages:
    def __init__(
        self,
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
        *,
        ledger: Ledger,
        work: UnitOfWork,
        skills: SkillFiles | None = None,
    ) -> None:
        self._processes = processes
        self._versions = versions
        self._ledger = ledger
        self._work = work
        self._skills = skills

    async def export(
        self, tenant: Tenant, process_id: str, version: str | None = None, *, by: str
    ) -> bytes:
        """The package of the version — the active one where none is named — as a ZIP archive."""
        async with self._work.transaction(tenant):
            if version is None:
                process = await self._processes.get(tenant, process_id)
                if process is None or process.active_version is None:
                    raise UnknownVersion(f"the process {process_id!r} has no active version")
                version = process.active_version
            found = await self._versions.get(tenant, f"{process_id}@{version}")
        if found is None:
            raise UnknownVersion(f"no version {process_id}@{version}")
        skills = {} if self._skills is None else await self._skills(tenant, found)
        written = package.archive(package.files_of(found, skills))
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=EXPORTED,
                    refs=LedgerRefs(tenant=tenant, process_version=found.ref, actor=by),
                    outcome="exported",
                    content_digest="sha256:" + hashlib.sha256(written).hexdigest(),
                ),
            )
        return written
