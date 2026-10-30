"""A shared agent as the instance runs it: one core, role profiles that narrow it (ADR-0163,
UC-8.11).

- **A call.** The caller's roles resolve the profile (`AgentCatalog.resolve`). The core's flow
  — a process with an active version — runs as the caller through the one path every run takes:
  a command, a commissioned plan, a run submitted to the queue, carrying the profile
  (`Run.profile`). A flow whose steps require a capability the profile does not grant is
  refused before it starts. `agent.called` records the call by profile.
- **A core change.** Each active profile is evaluated on the flow's cases (purpose `profile`):
  the active side serves the profile under the active core, the proposed side under the held
  one. Each verdict is recorded on the held core, which becomes active only when all passed.
- **Use and cost by profile.** The calls and what their runs cost, read from the ledger and
  accounting — never by caller (principle 14).

This is wiring: a call crosses the catalogue, the process, command and run components.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from taktus.components.accounting.application.service import CostOfRun, CostOfRunHandler
from taktus.components.catalog.application.service import AgentCatalog
from taktus.components.catalog.application.service.agents import CALLED
from taktus.components.catalog.domain.model import AgentError, CoreState
from taktus.components.command.application.service import CommissionPlan, CommissionPlanHandler
from taktus.components.process.application.service.proposals import ProposalError
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.process.domain.model.evaluation import (
    Evaluation,
    EvaluationState,
    Purpose,
)
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Run
from taktus.composition.evaluations import Evaluations, Guide
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.identity import IdentityResolver
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.ports.worker import Limits
from taktus.shared.v1 import Command, Intent, ReplyTo

CHANNEL = "channel.agent"


def _token(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text)


class SharedAgents:
    def __init__(
        self,
        *,
        catalog: AgentCatalog,
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
        evaluations: Evaluations,
        commission: CommissionPlanHandler,
        engine: RunEngine,
        identities: IdentityResolver,
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
        ids: Identifiers,
        costs: CostOfRunHandler | None = None,
    ) -> None:
        self._catalog = catalog
        self._processes = processes
        self._versions = versions
        self._evaluations = evaluations
        self._commission = commission
        self._engine = engine
        self._identities = identities
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._ids = ids
        self._costs = costs

    @property
    def catalog(self) -> AgentCatalog:
        return self._catalog

    async def _flow(self, tenant: Tenant, flow: str) -> ProcessVersion:
        async with self._work.transaction(tenant):
            process = await self._processes.get(tenant, flow)
            version = (
                None
                if process is None or process.active_version is None
                else await self._versions.get(tenant, f"{flow}@{process.active_version}")
            )
        if version is None:
            raise AgentError("no_flow", f"the agent's flow {flow!r} has no active version")
        return version

    # --- a call -----------------------------------------------------------------------------

    async def call(
        self,
        tenant: Tenant,
        agent: str,
        *,
        identity: str,
        inputs: Mapping[str, Any] | None = None,
        role: str | None = None,
    ) -> Run:
        """The agent's flow, run as the caller, serving the profile their roles resolve to."""
        placed = await self._identities.identity(tenant, identity)
        if placed is None:
            raise AgentError("unknown", f"the identity {identity!r} is not known to {tenant!r}")
        core, profile, found = await self._catalog.resolve(tenant, agent, placed.roles, role)
        version = await self._flow(tenant, core.flow)
        granted = set(profile.grants.tools)
        beyond = sorted(
            {c for step in version.steps for c in (step.required_capabilities or ())} - granted
        )
        if beyond:
            raise AgentError(
                "beyond_profile",
                f"the flow {version.ref} requires {', '.join(beyond)}, which {profile.id} does "
                "not grant",
            )
        if version.limits is None:
            raise AgentError("no_limits", f"{version.ref} names no `limits`")
        goal = f"call {core.id} as {profile.role}"
        command = Command(
            id=self._ids.new("cmd"),
            channel=CHANNEL,
            identity=placed.identity,
            org_path=placed.org_path,
            intent=Intent(raw=goal, recognised="agent.call"),
            context={"inputs": dict(inputs or {}), "agent": core.id},
            reply_to=ReplyTo(channel=CHANNEL, address="ledger"),
            received_at=self._clock.now(),
        )
        plan = await self._commission.execute(
            CommissionPlan(
                command=command,
                tenant=tenant,
                goal=goal,
                autonomy_level=min(version.autonomy_level, core.autonomy_level),
                steps=version.ordered(),
            )
        )
        run = await self._engine.submit(
            StartRun(
                plan=plan,
                work=version.work,
                budget=Limits.model_validate(dict(version.limits)),
                process_version=version.ref,
                actor=placed.identity,
                tenant=tenant,
                inputs=dict(inputs or {}),
                actions=dict(version.autonomy.action_levels),
                profile=profile.id,
            )
        )
        await self._catalog.called(tenant, profile, found, run_id=run.id, by=placed.identity)
        return run

    # --- a core change ----------------------------------------------------------------------

    def _evaluation_id(self, core_id: str, profile_id: str) -> str:
        return f"evl_{_token(core_id)}_{_token(profile_id)}"

    async def evaluate_core(self, tenant: Tenant, core_id: str) -> list[Evaluation]:
        """Every active profile evaluated on the flow's cases under the held core."""
        cores = {c.id: c for c in await self._catalog.cores(tenant, core_id.split("@", 1)[0])}
        core = cores.get(core_id)
        if core is None:
            raise AgentError("unknown", f"no core {core_id!r}")
        if core.state is not CoreState.HELD:
            return []
        started: list[Evaluation] = []
        for profile in await self._catalog.profiles(tenant, core.agent):
            evaluation = await self._evaluations.start_guided(
                tenant,
                core.flow,
                purpose=Purpose.PROFILE,
                subject=f"{core_id}/{profile.id}",
                active=Guide(profile=profile.id),
                proposed=Guide(profile=f"{core_id}/{profile.id}"),
                evaluation_id=self._evaluation_id(core_id, profile.id),
            )
            if evaluation is not None:
                started.append(evaluation)
        return started

    async def advance_core(self, tenant: Tenant, core_id: str) -> list[str]:
        """Each profile's evaluation moved on; a scored one's verdict recorded on the core. What
        still holds the core, as findings."""
        agent = core_id.split("@", 1)[0]
        for profile in await self._catalog.profiles(tenant, agent):
            evaluation_id = self._evaluation_id(core_id, profile.id)
            try:
                evaluation = await self._evaluations.advance(tenant, evaluation_id)
            except ProposalError:  # not started: the flow has no cases, nothing to record
                continue
            if evaluation.state is EvaluationState.SCORED and evaluation.verdict is not None:
                await self._catalog.record_verdict(
                    tenant, core_id, profile.id, evaluation.verdict.value
                )
        return await self._catalog.held_because(tenant, core_id)

    # --- use and cost -----------------------------------------------------------------------

    async def usage(self, tenant: Tenant, agent: str) -> list[dict[str, Any]]:
        """Per profile: its calls and what their runs cost, by currency. A profile is a role."""
        async with self._work.transaction(tenant):
            entries = await self._ledger.of_kinds(tenant, (CALLED,))
        runs: dict[str, list[str]] = {}
        for entry in entries:
            ref = entry.refs.agent_id
            if ref is None or not ref.startswith(f"{agent}:") or entry.refs.run_id is None:
                continue
            runs.setdefault(ref, []).append(entry.refs.run_id)
        report: list[dict[str, Any]] = []
        for profile, called in sorted(runs.items()):
            money: dict[str, float] = {}
            if self._costs is not None:
                for run_id in called:
                    cost = await self._costs.execute(CostOfRun(run_id=run_id, tenant=tenant))
                    if cost.priced is not None:
                        money[cost.priced.currency] = (
                            money.get(cost.priced.currency, 0.0) + cost.priced.amount
                        )
            report.append({"profile": profile, "calls": len(called), "money": money})
        return report
