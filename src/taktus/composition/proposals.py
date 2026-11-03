"""A person's proposal rehearsed and commissioned, and a process rolled back (UC-4.15, ADR-0091
§3 to §5).

- **Rehearse.** The proposed version runs as a rehearsal (ADR-0030) through the one path every
  run takes: a command, a commissioned plan, a run submitted to the queue. The run names the
  proposal, `<process>@proposal-<id>`, which no trigger fires and no level counts as a version.
  Its inputs are the ones the person gives, or those of the active version's last run.
- **Commission.** A proposal whose rehearsal finished is handed to registration, acting for the
  person who commissions it. Every check registration applies holds. The ledger records
  `process.commissioned`. A proposal made against a version that is no longer active is not
  commissioned. A proposal made against no version is a process's first version (ADR-0136 §4),
  and is stale once the process has an active version.
- **Evaluate.** A proposal that changes a step, of a process with evaluation cases, is run on
  them beside the active version when it is rehearsed, and commissioned only once that
  evaluation passed, or against its verdict with a person's reason (ADR-0134 §4).
- **Roll back.** An earlier version's bundle is registered again as a new version, through the
  same registration, and the ledger records `process.rolled_back`; the new version's reason names
  the version it restores. Nothing is deleted.

This is wiring, because each act crosses components — process, command and run — and only the
composition root may hold them all (`composition/README.md`).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from taktus.components.command.application.service import CommissionPlan, CommissionPlanHandler
from taktus.components.process.application.service.proposals import (
    ProposalError,
    Proposals,
    Propose,
)
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
    parse_bundle,
)
from taktus.components.process.domain.model import (
    InvalidProcess,
    Process,
    ProcessVersion,
    Proposal,
    ProposalState,
)
from taktus.components.process.domain.service.bundle import bundle_of, next_version
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState
from taktus.composition.evaluations import Evaluations
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
        change_process: str | None = None,
        evaluations: Evaluations | None = None,
    ) -> None:
        """`change_process` is the process that turns a request in words into a proposal, as
        the operator names it (`TAKTUS_CHANGE_PROCESS`); None, the default: no request in words
        is taken, and a changed bundle is handed over instead. Which process does it is a
        tenant's bundle, never the product's default (ADR-0092). `evaluations` holds a change
        to the process's evaluation cases (ADR-0134); None holds it to none."""
        self._proposals = proposals
        self._evaluations = evaluations
        self._change_process = change_process
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

    async def ask(self, tenant: Tenant, process_id: str, request: str, by: str) -> Run:
        """A change asked for in words: a run of the configured change process for the process
        (ADR-0091 §2), which keeps a proposal once the model's bundle passes validation. The run
        acts for whoever asked."""
        changing = self._change_process
        async with self._work.transaction(tenant):
            target = await self._processes.get(tenant, process_id)
            change = None if changing is None else await self._processes.get(tenant, changing)
            version = (
                None
                if change is None or change.active_version is None
                else await self._versions.get(tenant, f"{change.id}@{change.active_version}")
            )
        if target is None or target.active_version is None:
            raise ProposalError("unknown", f"no process {process_id!r}")
        if changing is None:
            raise ProposalError(
                "unavailable",
                "no process turns a request in words into a proposal on this instance "
                "(TAKTUS_CHANGE_PROCESS): hand over the changed bundle instead",
            )
        if version is None or version.limits is None:
            raise ProposalError(
                "unavailable",
                f"{changing} is not registered on this instance: hand over the changed bundle "
                "instead",
            )
        placed = await self._identities.identity(tenant, by)
        if placed is None:
            raise ProposalError("unknown", f"the identity {by!r} is not known to {tenant!r}")
        inputs = {"process": process_id, "request": request}
        command = Command(
            id=self._ids.new("cmd"),
            channel=CHANNEL,
            identity=placed.identity,
            org_path=placed.org_path,
            intent=Intent(raw=request, recognised="process.change"),
            context={"inputs": inputs},
            reply_to=ReplyTo(channel=CHANNEL, address="ledger"),
            received_at=self._clock.now(),
        )
        plan = await self._commission.execute(
            CommissionPlan(
                command=command,
                tenant=tenant,
                goal=f"propose a change to {process_id}",
                autonomy_level=version.autonomy_level,
                steps=version.ordered(),
            )
        )
        return await self._engine.submit(
            StartRun(
                org_unit=command.org_unit,
                plan=plan,
                work=version.work,
                budget=Limits.model_validate(dict(version.limits)),
                process_version=version.ref,
                actor=placed.identity,
                tenant=tenant,
                inputs=inputs,
                actions=version.autonomy.action_levels,
            )
        )

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
                org_unit=command.org_unit,
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
        evaluation = (
            None
            if self._evaluations is None
            else await self._evaluations.start_change(tenant, proposal, placed.identity)
        )
        rehearsed = await self._proposals.rehearsed(
            tenant,
            process_id,
            proposal_id,
            run.id,
            evaluation=None if evaluation is None else evaluation.id,
        )
        return rehearsed, run

    async def commission(
        self,
        tenant: Tenant,
        process_id: str,
        proposal_id: str,
        by: str,
        approved_by: str | None = None,
        override: str | None = None,
    ) -> ProcessVersion:
        """The proposal registered as the active version, once its rehearsal finished and, where
        it is held to the process's evaluation cases, once its evaluation passed. `override` is
        a person's reason for commissioning it against the evaluation's verdict (ADR-0134 §4)."""
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
        active = None if process is None else process.active_version
        if active != proposal.base_version:
            against = proposal.base_version or "no version"
            raise ProposalError(
                "stale",
                f"the proposal was made against {against}, and the active version is "
                f"{active}: ask again",
            )
        if self._evaluations is not None:
            await self._evaluations.hold(tenant, proposal, by, override)
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
        """The inputs of the active version's last run that was not a rehearsal; none if none.
        A proposal made against no version has no run before it: it takes what its schedule
        trigger gives, and every other declared input's example (ADR-0136 §4)."""
        if proposal.base_ref is None:
            return first_inputs(parse_bundle(proposal.bundle))
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


class InstanceChanges:
    """The loopback connector's `orchestrator.changes` (ADR-0091 §2): S-07 reads a process's
    active version as a bundle, and keeps the proposal for the bundle the model proposed. What
    the model answered leaves only through the proposals' validation; a bundle that would not
    register is a `ValueError` naming every finding, and nothing is kept."""

    def __init__(
        self,
        proposals: Proposals,
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
        work: UnitOfWork,
    ) -> None:
        self._proposals = proposals
        self._processes = processes
        self._versions = versions
        self._work = work

    async def read(self, tenant: str, process: str) -> dict[str, Any]:
        async with self._work.transaction(tenant):
            found = await self._processes.get(tenant, process)
            active = (
                None
                if found is None or found.active_version is None
                else await self._versions.get(tenant, f"{process}@{found.active_version}")
            )
        if active is None:
            raise ValueError(f"no process {process!r} with an active version")
        bundle = bundle_of(
            active,
            as_version=active.version,
            author=active.author,
            reason=active.reason or "as registered",
        )
        return {"version": active.version, "bundle": bundle}

    async def propose(
        self, tenant: str, *, identity: str, process: str, bundle: str, request: str
    ) -> dict[str, Any]:
        document = _bundle_from(bundle)
        try:
            proposal = await self._proposals.propose(
                Propose(tenant, process, document, by=identity, request=request)
            )
        except InvalidProcess as error:
            raise ValueError("; ".join(error.findings)) from error
        except ProposalError as error:
            raise ValueError(str(error)) from error
        return {"proposal": proposal.id, "difference": proposal.difference.document()}


def first_inputs(version: ProcessVersion) -> dict[str, Any]:
    """What a first version's rehearsal is given without a person's inputs: each declared
    input's value from the first schedule trigger that gives it, or else its example."""
    given: dict[str, Any] = {name: spec.example for name, spec in version.inputs.items()}
    for trigger in reversed(version.triggers):
        if trigger.schedule is not None and trigger.inputs:
            given.update({k: v for k, v in trigger.inputs.items() if k in version.inputs})
    return given


FENCE = re.compile(r"^```[a-z]*\s*\n(.*)\n```\s*$", re.DOTALL)


def _bundle_from(text: str) -> dict[str, Any]:
    """The bundle a model answered, as JSON; a fence around it is taken off, nothing else."""
    stripped = text.strip()
    fenced = FENCE.match(stripped)
    if fenced is not None:
        stripped = fenced.group(1).strip()
    try:
        document = json.loads(stripped)
    except json.JSONDecodeError as error:
        raise ValueError(f"the proposed bundle is no JSON document: {error}") from error
    if not isinstance(document, dict):
        raise ValueError("the proposed bundle is no JSON object")
    return document
