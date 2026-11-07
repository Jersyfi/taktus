"""Use case: a plan worked out in dialogue, and commissioned as an act of its own (ADR-0237).

`open` starts a draft for a command; `revise` changes it, making a new version each time;
`commission` takes the current version into a commissioned `Plan`. Commissioning refuses a
draft that lacks one of the four parts and names what is missing, and refuses a draft with a
step that cannot be estimated before it starts, naming the step (ADR-0005). It records
`plan.commissioned` in the ledger, naming the plan's version and the identity that
commissioned it, in the same transaction as the plan.

Nothing here runs anything. The engine refuses a plan that was not commissioned
(`RunEngine.start`), so a draft, or a version changed after commissioning, cannot run.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from taktus.components.command.domain.model.planning import (
    AgentPart,
    DomainPart,
    Estimate,
    PlanDraft,
)
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import (
    AutonomyLevel,
    Command,
    Commissioned,
    LedgerRefs,
    Plan,
    PlanResult,
    PlanStatus,
    Step,
)

PLAN_COMMISSIONED = "plan.commissioned"
PLAN_REVISED = "plan.revised"

REVISABLE = frozenset(
    {
        "goal",
        "steps",
        "process_version",
        "due",
        "autonomy_level",
        "autonomy_reason",
        "estimates",
        "results_in",
        "agent",
        "domain",
        "describes",
    }
)


class PlanningError(Exception):
    pass


class UnknownDraft(PlanningError):
    def __init__(self, draft_id: str) -> None:
        super().__init__(f"no plan draft {draft_id!r}")


class PlanIncomplete(PlanningError):
    """A draft lacking one of the four parts cannot be commissioned; the refusal names them."""

    def __init__(self, missing: Sequence[str]) -> None:
        self.missing = tuple(missing)
        super().__init__("the plan cannot be commissioned; it lacks " + "; ".join(self.missing))


class Unestimable(PlanningError):
    """A step that cannot be estimated before it starts refuses the plan before anything runs."""

    def __init__(self, steps: Sequence[str]) -> None:
        self.steps = tuple(steps)
        super().__init__(
            "the plan cannot be commissioned; these steps cannot be estimated before they "
            f"start: {', '.join(self.steps)}. Break them into steps that can (ADR-0005)"
        )


@dataclass(frozen=True)
class OpenDraft:
    command: Command
    tenant: Tenant
    goal: str | None = None
    steps: Sequence[Step] = ()
    process_version: str | None = None
    due: datetime | None = None
    autonomy_level: AutonomyLevel | None = None
    autonomy_reason: str | None = None
    estimates: Sequence[Estimate] = ()
    results_in: PlanResult = PlanResult.RUN
    agent: AgentPart | None = None
    """An agent draft's agent part, as far as it is known (ADR-0292)."""
    domain: DomainPart | None = None
    """A domain draft's instance and its open questions (ADR-0289)."""
    describes: str | None = None
    """The process the goal describes (ADR-0290)."""


@dataclass(frozen=True)
class ReviseDraft:
    draft_id: str
    tenant: Tenant
    by: str
    changes: Mapping[str, Any] = field(default_factory=dict)
    """The fields that change, by name; only those of `REVISABLE`."""


@dataclass(frozen=True)
class CommissionDraft:
    draft_id: str
    tenant: Tenant
    by: str
    """The identity that commissions: the act is theirs."""


class PlanDialogue:
    def __init__(
        self,
        commands: Repository[Command],
        drafts: Repository[PlanDraft],
        plans: Repository[Plan],
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
        ids: Identifiers,
    ) -> None:
        self._commands = commands
        self._drafts = drafts
        self._plans = plans
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._ids = ids

    async def open(self, command: OpenDraft) -> PlanDraft:
        draft = PlanDraft(
            id=self._ids.new("pld"),
            tenant=command.tenant,
            command_id=command.command.id,
            version=1,
            goal=command.goal,
            steps=tuple(command.steps),
            process_version=command.process_version,
            due=command.due,
            autonomy_level=command.autonomy_level,
            autonomy_reason=command.autonomy_reason,
            estimates=tuple(command.estimates),
            results_in=command.results_in,
            agent=command.agent,
            domain=command.domain,
            describes=command.describes,
            changed_by=command.command.identity,
            changed_at=self._clock.now(),
        )
        async with self._work.transaction(command.tenant):
            if await self._commands.get(command.tenant, command.command.id) is None:
                await self._commands.put(command.tenant, command.command)
            await self._drafts.put(command.tenant, draft)
        return draft

    async def get(self, tenant: Tenant, draft_id: str) -> PlanDraft:
        async with self._work.transaction(tenant):
            draft = await self._drafts.get(tenant, draft_id)
        if draft is None:
            raise UnknownDraft(draft_id)
        return draft

    async def revise(self, command: ReviseDraft) -> PlanDraft:
        """A new version with the changes. A commissioned version stays commissioned as it was;
        the new one is not, and runs only once it is commissioned again."""
        unknown = sorted(set(command.changes) - REVISABLE)
        if unknown:
            raise PlanningError(f"a plan draft has no field to revise named {', '.join(unknown)}")
        async with self._work.transaction(command.tenant):
            draft = await self._drafts.get(command.tenant, command.draft_id)
            if draft is None:
                raise UnknownDraft(command.draft_id)
            changes = dict(command.changes)
            for name in ("steps", "estimates"):
                if name in changes:
                    changes[name] = tuple(changes[name])
            revised = PlanDraft.model_validate(
                {
                    **draft.model_dump(),
                    **changes,
                    "version": draft.version + 1,
                    "changed_by": command.by,
                    "changed_at": self._clock.now(),
                }
            )
            await self._drafts.put(command.tenant, revised)
            await self._ledger.record(
                command.tenant,
                Fact(
                    kind=PLAN_REVISED,
                    refs=LedgerRefs(
                        tenant=command.tenant,
                        command_id=draft.command_id,
                        plan_id=revised.plan_id,
                        actor=command.by,
                    ),
                    outcome="revised",
                ),
            )
        return revised

    async def commission(self, command: CommissionDraft) -> Plan:
        """The current version, commissioned by `by`: refused, writing nothing, when the draft
        lacks a part or a step that cannot be estimated."""
        async with self._work.transaction(command.tenant):
            draft = await self._drafts.get(command.tenant, command.draft_id)
            if draft is None:
                raise UnknownDraft(command.draft_id)
            missing = draft.missing()
            if missing or draft.goal is None or draft.autonomy_level is None:
                raise PlanIncomplete(missing)
            unestimable = draft.unestimable()
            if unestimable:
                raise Unestimable(unestimable)
            act = Commissioned(by=command.by, at=self._clock.now())
            plan = Plan(
                id=draft.plan_id,
                command_id=draft.command_id,
                goal=draft.goal,
                autonomy_level=draft.autonomy_level,
                due=draft.due,
                steps=draft.steps,
                results_in=draft.results_in,
                status=PlanStatus.COMMISSIONED,
                commissioned=act,
            )
            await self._plans.put(command.tenant, plan)
            await self._drafts.put(
                command.tenant,
                draft.model_copy(
                    update={"commissioned_version": draft.version, "commissioned": act}
                ),
            )
            await self._ledger.record(
                command.tenant,
                Fact(
                    kind=PLAN_COMMISSIONED,
                    refs=LedgerRefs(
                        tenant=command.tenant,
                        command_id=draft.command_id,
                        plan_id=plan.id,
                        process_version=draft.process_version,
                        actor=command.by,
                    ),
                    outcome="commissioned",
                ),
            )
        return plan

    async def commissioned(self, tenant: Tenant, draft_id: str) -> Plan | None:
        """The plan of the version commissioned last, whatever was revised since; None when
        no version was commissioned."""
        draft = await self.get(tenant, draft_id)
        if draft.commissioned_version is None:
            return None
        async with self._work.transaction(tenant):
            return await self._plans.get(tenant, f"{draft.id}@v{draft.commissioned_version}")
