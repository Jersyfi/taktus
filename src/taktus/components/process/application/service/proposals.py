"""Use case: a changed bundle becomes a proposal, never a version (UC-4.15, ADR-0091 §1).

A proposal is offered only once its bundle passes the validation registration applies: the
bundle's own rules, the graph's, the exactness statement's, and the refusal of a credential that
would administer the instance's platform. Otherwise the request is answered with the findings
registration would give, and nothing is kept. The proposal names a version the process has not
registered, because a registered version is never written over. It is made against the active
version, and carries its difference against it, computed by a rule. A process with no active
version — one the tenant does not have yet — gets a proposal made against none, its first
version (ADR-0136 §4).

Nothing here registers anything: the active version, its triggers and its runs are unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from taktus.components.process.application.service.register_version import (
    credentials_named,
    parse_bundle,
)
from taktus.components.process.domain.model import InvalidProcess, Process, ProcessVersion
from taktus.components.process.domain.model.proposal import OPEN, Proposal, ProposalState
from taktus.components.process.domain.service.difference import difference
from taktus.ports.administration import Administration
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.persistence import Repository, Tenant, UnitOfWork

type Document = Mapping[str, Any]


class ProposalError(Exception):
    """A proposal that cannot be made, read or acted on. `kind` says which: `unknown` — no such
    process or proposal; `closed` — the proposal is no longer open."""

    def __init__(self, kind: str, detail: str) -> None:
        self.kind = kind
        super().__init__(detail)


@dataclass(frozen=True)
class Propose:
    tenant: Tenant
    process_id: str
    bundle: Document
    by: str
    """The identity that asks for the change."""
    request: str | None = None
    """The person's words, where the change was asked for in words (ADR-0091 §2)."""


class Proposals:
    def __init__(
        self,
        versions: Repository[ProcessVersion],
        processes: Repository[Process],
        proposals: Repository[Proposal],
        work: UnitOfWork,
        clock: Clock,
        identifiers: Identifiers,
        administration: Administration | None = None,
    ) -> None:
        self._versions = versions
        self._processes = processes
        self._proposals = proposals
        self._work = work
        self._clock = clock
        self._ids = identifiers
        self._administration = administration or Administration()

    async def propose(self, command: Propose) -> Proposal:
        """The proposal for a changed bundle, stored; or InvalidProcess with every finding."""
        version = parse_bundle(command.bundle)
        findings: list[str] = []
        if version.process_id != command.process_id:
            findings.append(
                f"the bundle is for the process {version.process_id!r}, not {command.process_id!r}"
            )
        findings.extend(
            refusal
            for step_id, names in credentials_named(version).items()
            if (refusal := self._administration.refusal(step_id, names)) is not None
        )
        async with self._work.transaction(command.tenant):
            process = await self._processes.get(command.tenant, command.process_id)
            active = None if process is None else process.active_version
            base = (
                None
                if active is None
                else await self._versions.get(command.tenant, f"{command.process_id}@{active}")
            )
            if active is not None and base is None:
                raise ProposalError("unknown", f"no active version of {command.process_id!r}")
            if await self._versions.get(command.tenant, version.ref) is not None:
                findings.append(
                    f"the version {version.version!r} is registered already, and a registered "
                    "version is never written over: the proposal names a new one"
                )
            if findings:
                raise InvalidProcess(tuple(findings))
            proposal = Proposal(
                id=self._ids.new("prp"),
                tenant=command.tenant,
                process_id=command.process_id,
                base_version=None if base is None else base.version,
                version=version.version,
                bundle=dict(command.bundle),
                request=command.request,
                requested_by=command.by,
                difference=difference(base, version),
                created_at=self._clock.now(),
            )
            await self._proposals.put(command.tenant, proposal)
        return proposal

    async def get(self, tenant: Tenant, process_id: str, proposal_id: str) -> Proposal:
        async with self._work.transaction(tenant):
            found = await self._proposals.get(tenant, proposal_id)
        if found is None or found.process_id != process_id:
            raise ProposalError("unknown", f"no proposal {proposal_id!r} for {process_id!r}")
        return found

    async def find(self, tenant: Tenant, proposal_id: str) -> Proposal:
        """A proposal by its identifier alone, as the owner's conversation names it."""
        async with self._work.transaction(tenant):
            found = await self._proposals.get(tenant, proposal_id)
        if found is None:
            raise ProposalError("unknown", f"no proposal {proposal_id!r}")
        return found

    async def of_process(self, tenant: Tenant, process_id: str) -> list[Proposal]:
        """The proposals for a process, newest first."""
        async with self._work.transaction(tenant):
            found = [p for p in await self._proposals.list(tenant) if p.process_id == process_id]
        return sorted(found, key=lambda p: p.created_at, reverse=True)

    async def discard(self, tenant: Tenant, process_id: str, proposal_id: str) -> Proposal:
        """The proposal, discarded. Only an open proposal can be; nothing else changes."""
        async with self._work.transaction(tenant):
            found = await self._proposals.get(tenant, proposal_id)
            if found is None or found.process_id != process_id:
                raise ProposalError("unknown", f"no proposal {proposal_id!r} for {process_id!r}")
            if found.state not in OPEN:
                raise ProposalError("closed", f"the proposal {proposal_id} is {found.state}")
            discarded = found.model_copy(update={"state": ProposalState.DISCARDED})
            await self._proposals.put(tenant, discarded)
        return discarded

    async def rehearsed(
        self,
        tenant: Tenant,
        process_id: str,
        proposal_id: str,
        run_id: str,
        evaluation: str | None = None,
    ) -> Proposal:
        """The proposal, with the rehearsal run that was started for it (ADR-0091 §3), and the
        evaluation on the process's cases started beside it, where it needs one (ADR-0134 §4).
        A rehearsal again replaces both."""
        return await self._move(
            tenant,
            process_id,
            proposal_id,
            ProposalState.REHEARSED,
            rehearsal_run=run_id,
            evaluation=evaluation,
        )

    async def commissioned(self, tenant: Tenant, process_id: str, proposal_id: str) -> Proposal:
        """The proposal, commissioned: registration has registered its bundle (ADR-0091 §4)."""
        return await self._move(tenant, process_id, proposal_id, ProposalState.COMMISSIONED)

    async def _move(
        self,
        tenant: Tenant,
        process_id: str,
        proposal_id: str,
        state: ProposalState,
        **more: Any,
    ) -> Proposal:
        async with self._work.transaction(tenant):
            found = await self._proposals.get(tenant, proposal_id)
            if found is None or found.process_id != process_id:
                raise ProposalError("unknown", f"no proposal {proposal_id!r} for {process_id!r}")
            if found.state not in OPEN:
                raise ProposalError("closed", f"the proposal {proposal_id} is {found.state}")
            moved = found.model_copy(update={"state": state, **more})
            await self._proposals.put(tenant, moved)
        return moved
