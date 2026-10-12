"""A person's proposal rehearsed and commissioned, and a process rolled back (UC-4.15, ADR-0091
§3 to §5).

- **Rehearse.** The proposed version runs as a rehearsal (ADR-0030) through the one path every
  run takes: a command, a commissioned plan, a run submitted to the queue. The run names the
  proposal, `<process>@proposal-<id>`, which no trigger fires and no level counts as a version.
  Its inputs are the ones the person gives, or those of the active version's last run.
- **Commission.** A proposal whose rehearsal finished is handed to registration, acting for the
  person who commissions it. Every check registration applies holds. The ledger records
  `process.commissioned`. A proposal made against a version that is no longer active is not
  commissioned.
- **Roll back.** An earlier version's bundle is registered again as a new version, through the
  same registration, and the ledger records `process.rolled_back`; the new version's reason names
  the version it restores. Nothing is deleted.

This is wiring, because each act crosses components — process, command and run — and only the
composition root may hold them all (`composition/README.md`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from taktus.components.command.application.service import CommissionPlan, CommissionPlanHandler
from taktus.components.process.application.service.proposals import ProposalError, Proposals
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
    parse_bundle,
)
from taktus.components.process.domain.model import (
    Process,
    ProcessVersion,
    Proposal,
    ProposalState,
)
from taktus.components.process.domain.service.bundle import bundle_of, next_version
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.identity import IdentityResolver
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.ports.worker import Limits
from taktus.shared.v1 import Command, Intent, LedgerRefs, ReplyTo

CHANNEL = "channel.web"
"""The channel a change in dialogue arrives on; the chat's acts arrive on their own (ADR-0069)."""


class ProposalActs:
    def __init__(
        self,
        *,
        proposals: Proposals,
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
        runs: Repository[Run],
        register: RegisterProcessVersionHandler,
        commission: CommissionPlanHandler,
        engine: RunEngine,
        identities: IdentityResolver,
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
        ids: Identifiers,
    ) -> None:
        self._proposals = proposals
        self._processes = processes
        self._versions = versions
        self._runs = runs
        self._register = register
        self._commission = commission
        self._engine = engine
        self._identities = identities
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._ids = ids

    async def rehearse(
        self,
        tenant: Tenant,
        process_id: str,
        proposal_id: str,
        by: str,
        inputs: Mapping[str, Any] | None = None,
    ) -> tuple[Proposal, Run]:
        """The proposal rehearsed: its rehearsal run submitted, and the proposal naming it."""
        proposal = await self._proposals.get(tenant, process_id, proposal_id)
        if proposal.state not in (ProposalState.PROPOSED, ProposalState.REHEARSED):
            raise ProposalError("closed", f"the proposal {proposal_id} is {proposal.state}")
        version = parse_bundle(proposal.bundle)
        if version.limits is None:
            raise ProposalError(
                "unrehearsable", f"{version.ref} names no `limits`; a rehearsal needs a budget"
            )
        try:
            budget = Limits.model_validate(dict(version.limits))
        except ValueError as error:
            raise ProposalError("unrehearsable", f"{version.ref}: `limits`: {error}") from error
        placed = await self._identities.identity(tenant, by)
        if placed is None:
            raise ProposalError("unknown", f"the identity {by!r} is not known to {tenant!r}")
        given = dict(inputs) if inputs is not None else await self._last_inputs(tenant, proposal)
        reference = f"{process_id}@proposal-{proposal.id}"
        command = Command(
            id=self._ids.new("cmd"),
            channel=CHANNEL,
            identity=placed.identity,
            org_path=placed.org_path,
            intent=Intent(raw=f"rehearse {reference}", recognised="process.rehearse"),
            context={"inputs": given, "proposal": proposal.id},
            reply_to=ReplyTo(channel=CHANNEL, address="ledger"),
            received_at=self._clock.now(),
        )
        plan = await self._commission.execute(
            CommissionPlan(
                command=command,
                tenant=tenant,
                goal=f"rehearse the proposal {proposal.id} for {process_id}",
                autonomy_level=version.autonomy_level,
                steps=version.ordered(),
            )
        )
        run = await self._engine.submit(
            StartRun(
                plan=plan,
                work=version.work,
                budget=budget,
                process_version=reference,
                actor=placed.identity,
                tenant=tenant,
                inputs=given,
                rehearsal=True,
                actions=version.autonomy.action_levels,
            )
        )
        return await self._proposals.rehearsed(tenant, process_id, proposal_id, run.id), run

    async def commission(
        self,
        tenant: Tenant,
        process_id: str,
        proposal_id: str,
        by: str,
        approved_by: str | None = None,
    ) -> ProcessVersion:
        """The proposal registered as the active version, once its rehearsal finished."""
        proposal = await self._proposals.get(tenant, process_id, proposal_id)
        if proposal.state is not ProposalState.REHEARSED or proposal.rehearsal_run is None:
            raise ProposalError(
                "unrehearsed", f"the proposal {proposal_id} is commissioned only once rehearsed"
            )
        async with self._work.transaction(tenant):
            rehearsal = await self._runs.get(tenant, proposal.rehearsal_run)
            process = await self._processes.get(tenant, process_id)
        if rehearsal is None or rehearsal.state is not RunState.FINISHED:
            state = "missing" if rehearsal is None else str(rehearsal.state)
            raise ProposalError(
                "unrehearsed",
                f"the rehearsal {proposal.rehearsal_run} has not finished ({state}); "
                "the proposal is commissioned once it has",
            )
        if process is None or process.active_version != proposal.base_version:
            raise ProposalError(
                "stale",
                f"the proposal was made against {proposal.base_version}, and the active "
                f"version is {None if process is None else process.active_version}: ask again",
            )
        version = await self._register.execute(
            RegisterProcessVersion(proposal.bundle, tenant=tenant, by=by, approved_by=approved_by)
        )
        await self._proposals.commissioned(tenant, process_id, proposal_id)
        await self._record(tenant, version, "process.commissioned", proposal.id, by)
        return version

    async def rollback(
        self,
        tenant: Tenant,
        process_id: str,
        to_version: str,
        by: str,
        as_version: str | None = None,
        approved_by: str | None = None,
    ) -> ProcessVersion:
        """An earlier version made current again, as a new version; nothing deleted."""
        async with self._work.transaction(tenant):
            earlier = await self._versions.get(tenant, f"{process_id}@{to_version}")
            registered = [
                v.version for v in await self._versions.list(tenant) if v.process_id == process_id
            ]
        if earlier is None:
            raise ProposalError("unknown", f"no version {to_version!r} of {process_id!r}")
        label = as_version or next_version(registered)
        if label in registered:
            raise ProposalError(
                "taken", f"the version {label!r} is registered already and is never written over"
            )
        bundle = bundle_of(
            earlier, as_version=label, author=by, reason=f"rolled back to {to_version}"
        )
        version = await self._register.execute(
            RegisterProcessVersion(bundle, tenant=tenant, by=by, approved_by=approved_by)
        )
        await self._record(tenant, version, "process.rolled_back", "restored", by)
        return version

    async def _last_inputs(self, tenant: Tenant, proposal: Proposal) -> dict[str, Any]:
        """The inputs of the active version's last run that was not a rehearsal; none if none."""
        async with self._work.transaction(tenant):
            runs = [
                r
                for r in await self._runs.list(tenant)
                if r.process_version == proposal.base_ref and not r.rehearsal
            ]
        if not runs:
            return {}
        return dict(max(runs, key=lambda r: r.created_at).inputs)

    async def _record(
        self, tenant: Tenant, version: ProcessVersion, kind: str, outcome: str, by: str
    ) -> None:
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=kind,
                    refs=LedgerRefs(tenant=tenant, process_version=version.ref, actor=by),
                    outcome=outcome,
                ),
            )
