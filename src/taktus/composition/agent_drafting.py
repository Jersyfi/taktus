"""An agent drafted in the plan dialogue, registered when its plan is commissioned (ADR-0292,
UC-8.7, UC-1.2).

A plan draft with an agent part is worked out like any other: in the guided mode, which asks for
what the agent lacks, or in the expert mode. Commissioning it is two acts in order:

1. **Checked before anything is written.** The draft lacks no part and every step can be
   estimated (ADR-0237); the agent's tools grant every tool action its flow uses (ADR-0261 §4);
   no tool, source or connector is named after a product (ADR-0287); the core version does not
   exist yet (ADR-0163). Each refusal names what it found.
2. **The plan commissioned, then the core proposed.** The plan dialogue commissions the version
   and records `plan.commissioned`; the catalogue proposes the core by the identity that
   commissioned, recording `agent.core_proposed` with the plan in `refs.plan_id`. The
   catalogue's own checks run again there; nothing here stands in for them.

Sharing is not part of it: a person shares the agent afterwards, by its own act (ADR-0246).

This is wiring: a draft of the `command` component becomes a core of the `catalog` component.
"""

from __future__ import annotations

from collections.abc import Sequence

from taktus.components.catalog.application.service import AgentCatalog
from taktus.components.catalog.domain.model import AgentCore, AgentError, Grants
from taktus.components.command.application.service import (
    CommissionDraft,
    PlanDialogue,
    PlanIncomplete,
    PlanningError,
    Unestimable,
)
from taktus.components.command.domain.model import AgentPart, PlanDraft
from taktus.components.process.domain.model import ProcessVersion
from taktus.composition.agents import beyond, tool_actions
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Plan


class AgentDraftRefused(PlanningError):
    """An agent draft the catalogue would refuse, refused before anything is written."""

    def __init__(self, reason: str, message: str, findings: Sequence[str] = ()) -> None:
        self.reason = reason
        self.findings = tuple(findings)
        super().__init__(message if not findings else f"{message}: {'; '.join(findings)}")


def grants_of(agent: AgentPart) -> Grants:
    return Grants(
        sources=tuple(agent.sources or ()),
        connectors=tuple(agent.connectors),
        tools=tuple(agent.tools or ()),
        formats=tuple(agent.formats),
        approval_limit=agent.approval_limit,
    )


class AgentDrafts:
    def __init__(
        self,
        catalog: AgentCatalog,
        dialogue: PlanDialogue,
        versions: Repository[ProcessVersion],
        work: UnitOfWork,
    ) -> None:
        self._catalog = catalog
        self._dialogue = dialogue
        self._versions = versions
        self._work = work

    async def proposed_tools(self, tenant: Tenant, process_version: str) -> tuple[str, ...]:
        """The tool actions the flow uses, and nothing more: what Taktus proposes as an agent's
        tools when its flow is chosen (ADR-0292 §2)."""
        version = await self._version(tenant, process_version)
        return tuple(sorted(tool_actions(version)))

    async def commission(
        self, tenant: Tenant, identity: str, draft: PlanDraft
    ) -> tuple[Plan, AgentCore]:
        """The draft's plan commissioned by `identity`, and the agent's core proposed through
        the catalogue; refused, writing nothing, where either would be."""
        agent = draft.agent
        missing = draft.missing()
        if (
            missing
            or agent is None
            or agent.name is None
            or agent.instructions is None
            or draft.goal is None
            or draft.autonomy_level is None
            or draft.process_version is None
        ):
            raise PlanIncomplete(missing or ("the agent's name",))
        unestimable = draft.unestimable()
        if unestimable:
            raise Unestimable(unestimable)
        version = await self._version(tenant, draft.process_version)
        grants = grants_of(agent)
        ungranted = beyond(version, grants.tools)
        if ungranted:
            raise AgentDraftRefused(
                "beyond_tools",
                f"the agent's flow {version.ref} uses tools its draft does not grant",
                ungranted,
            )
        core_id = f"{agent.name}@{agent.version}"
        try:
            self._catalog.check_named(core_id, grants)
        except AgentError as error:
            raise AgentDraftRefused(error.reason, str(error)) from error
        if any(c.id == core_id for c in await self._catalog.cores(tenant, agent.name)):
            raise AgentDraftRefused(
                "exists", f"{core_id} exists, and a core version never changes; name another"
            )
        plan = await self._dialogue.commission(
            CommissionDraft(draft_id=draft.id, tenant=tenant, by=identity)
        )
        try:
            core = await self._catalog.propose_core(
                tenant,
                agent=agent.name,
                version=agent.version,
                purpose=draft.goal,
                instructions=agent.instructions,
                flow=version.process_id,
                autonomy_level=draft.autonomy_level,
                autonomy_reason=draft.autonomy_reason,
                grants=grants,
                model=agent.model,
                by=identity,
                plan_id=plan.id,
            )
        except AgentError as error:
            raise AgentDraftRefused(
                error.reason,
                f"{plan.id} was commissioned, but the catalogue refused the agent; revise the "
                f"draft and commission it again ({error})",
            ) from error
        return plan, core

    async def _version(self, tenant: Tenant, ref: str) -> ProcessVersion:
        async with self._work.transaction(tenant):
            version = await self._versions.get(tenant, ref)
        if version is None:
            raise PlanningError(f"no process version {ref!r}")
        return version
