"""A shared agent as the instance runs it: one core, role profiles that narrow it (ADR-0163,
UC-8.11).

- **A call.** The caller's roles resolve the profile (`AgentCatalog.resolve`). The core's flow
  — a process with an active version — runs as the caller through the one path every run takes:
  a command, a commissioned plan, a run submitted to the queue, carrying the profile
  (`Run.profile`). A flow whose steps use a tool action the profile does not grant — a
  capability a step requires, or a connector operation a step calls, granted by itself or by its
  capability — is refused before it starts (ADR-0261 §4). `agent.called` records the call by
  profile. A call for a message in a rollout channel names that channel, the message's reply
  address and a run identifier derived from the message (`composition/assistants.py`).
- **A core change.** Each active profile is evaluated on the flow's cases (purpose `profile`):
  the active side serves the profile under the active core, the proposed side under the held
  one. Each verdict is recorded on the held core, which becomes active only when all passed.
- **Use and cost by profile.** The calls and what their runs cost, read from the ledger and
  accounting — never by caller (principle 14).

This is wiring: a call crosses the catalogue, the process, command and run components.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from typing import Any

from taktus.components.accounting.application.service import CostOfRun, CostOfRunHandler
from taktus.components.catalog.application.service import AgentCatalog, CatalogueShares
from taktus.components.catalog.application.service.agents import CALLED
from taktus.components.catalog.domain.model import AgentCore, AgentError, CoreState, ShareKind
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
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.ports.worker import Limits
from taktus.shared.v1 import Command, Intent, LedgerRefs, ReplyTo

CHANNEL = "channel.agent"
REFUSED = "agent.refused"


def _token(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text)


def tool_actions(version: ProcessVersion) -> set[str]:
    """The tool actions a version's steps use: each capability a step requires, and each
    connector operation a step calls or waits on."""
    used: set[str] = set()
    for step in version.steps:
        used.update(step.required_capabilities or ())
        work = version.work.get(step.id) or {}
        until = work.get("until")
        for operation in (
            work.get("operation"),
            until.get("operation") if isinstance(until, Mapping) else None,
        ):
            if isinstance(operation, str) and "." in operation:
                used.add(operation)
    return used


def beyond(version: ProcessVersion, granted: Collection[str]) -> list[str]:
    """The tool actions of the version that the grants do not cover, sorted (ADR-0261 §4): a
    capability is covered by itself, an operation by itself or by its capability."""
    tools = set(granted)
    return sorted(
        action
        for action in tool_actions(version)
        if action not in tools and action.rsplit(".", 1)[0] not in tools
    )


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
        shares: CatalogueShares | None = None,
    ) -> None:
        self._shares = shares
        """Who the agent is shared with (ADR-0246). None: every identity of the tenant."""
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

    async def flow(self, tenant: Tenant, agent: str) -> tuple[AgentCore, ProcessVersion]:
        """The agent's active core and the active version of its flow, or `AgentError`: an
        agent without an active core is `unknown`, a flow switched off is `no_flow`."""
        core = await self._catalog.active_core(tenant, agent)
        if core is None:
            raise AgentError("unknown", f"the agent {agent!r} has no active core")
        return core, await self._flow(tenant, core.flow)

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
        channel: str = CHANNEL,
        reply_to: ReplyTo | None = None,
        run_id: str | None = None,
        trigger: Mapping[str, Any] | None = None,
    ) -> Run:
        """The agent's flow, run as the caller, serving the profile their roles resolve to.
        `channel`, `reply_to`, `run_id` and `trigger` name where the call came from: the agent
        surface by default, a rollout channel for an assistant's message (ADR-0261 §3)."""
        placed = await self._identities.identity(tenant, identity)
        if placed is None:
            raise AgentError("unknown", f"the identity {identity!r} is not known to {tenant!r}")
        if self._shares is not None and not await self._shares.admits(
            tenant, ShareKind.AGENT, agent, placed.identity, placed.org_path
        ):
            async with self._work.transaction(tenant):
                await self._ledger.record(
                    tenant,
                    Fact(
                        kind=REFUSED,
                        refs=LedgerRefs(tenant=tenant, agent_id=agent, actor=placed.identity),
                        outcome="outside_circle",
                    ),
                )
            raise AgentError(
                "outside_circle",
                f"the agent {agent!r} is not shared with a circle {placed.identity} is inside",
            )
        core, profile, found = await self._catalog.resolve(tenant, agent, placed.roles, role)
        version = await self._flow(tenant, core.flow)
        ungranted = beyond(version, profile.grants.tools)
        if ungranted:
            raise AgentError(
                "beyond_profile",
                f"the flow {version.ref} uses {', '.join(ungranted)}, which {profile.id} does "
                "not grant",
            )
        if version.limits is None:
            raise AgentError("no_limits", f"{version.ref} names no `limits`")
        goal = f"call {core.id} as {profile.role}"
        command = Command(
            id=self._ids.new("cmd"),
            channel=channel,
            identity=placed.identity,
            org_path=placed.org_path,
            intent=Intent(raw=goal, recognised="agent.call"),
            context={"inputs": dict(inputs or {}), "agent": core.id},
            reply_to=reply_to or ReplyTo(channel=CHANNEL, address="ledger"),
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
                org_unit=command.org_unit,
                plan=plan,
                work=version.work,
                budget=Limits.model_validate(dict(version.limits)),
                process_version=version.ref,
                actor=placed.identity,
                tenant=tenant,
                inputs=dict(inputs or {}),
                actions=dict(version.autonomy.action_levels),
                profile=profile.id,
                run_id=run_id,
                trigger=None if trigger is None else dict(trigger),
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
