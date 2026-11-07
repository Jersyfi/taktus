"""The plan dialogue as the surfaces present it: opened, answered in the guided mode, set in the
expert mode, and commissioned (ADR-0237, ADR-0238, ADR-0279).

A surface — the web app, a command line, a chat — says what the person wants and in which mode;
this module turns it into the one plan draft's revisions. The guided mode's answer to "which
template or process should do it" names a process version, whose steps and estimates the draft
takes from the process component: that crosses components, so it is the composition root's.

What a surface shows of a draft is `view`: the draft's parts, what it lacks, every estimate as a
person reads it, every setting with its value and why, and — in the guided mode — the one
question asked next. The mode is a value the surface passes; nothing here reads it to decide
what a person may do.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from taktus.components.command.application.service import (
    CommissionDraft,
    OpenDraft,
    PlanDialogue,
    PlanningError,
    ReviseDraft,
)
from taktus.components.command.domain.model import Estimate, PlanDraft
from taktus.components.command.domain.service.guided import (
    SAFE_LEVELS,
    Mode,
    next_question,
    settings,
)
from taktus.components.process.domain.model import ProcessVersion
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Capability, Command, Intent, Plan, PlanResult, ReplyTo, Step


class PlanActs:
    def __init__(
        self,
        dialogue: PlanDialogue,
        drafts: Repository[PlanDraft],
        commands: Repository[Command],
        versions: Repository[ProcessVersion],
        work: UnitOfWork,
        clock: Clock,
        ids: Identifiers,
    ) -> None:
        self._dialogue = dialogue
        self._drafts = drafts
        self._commands = commands
        self._versions = versions
        self._work = work
        self._clock = clock
        self._ids = ids

    async def open(
        self,
        tenant: Tenant,
        identity: str,
        org_path: tuple[str, ...],
        said: str,
        channel: Capability = "channel.web",
    ) -> PlanDraft:
        """A new draft for what the person said; its goal is what they said, where they said
        anything."""
        now = self._clock.now()
        command = Command(
            id=self._ids.new("cmd"),
            channel=channel,
            identity=identity,
            org_path=org_path,
            intent=Intent(raw=said or "a plan"),
            reply_to=ReplyTo(channel=channel, address=f"plan:{identity}"),
            received_at=now,
        )
        goal = said.strip() or None
        return await self._dialogue.open(OpenDraft(command=command, tenant=tenant, goal=goal))

    async def mine(self, tenant: Tenant, identity: str) -> list[PlanDraft]:
        """The drafts of the person's own commands, newest change first."""
        async with self._work.transaction(tenant):
            drafts = list(await self._drafts.list(tenant))
            own = {c.id for c in await self._commands.list(tenant) if c.identity == identity}
        return sorted(
            (d for d in drafts if d.command_id in own), key=lambda d: d.changed_at, reverse=True
        )

    async def get(self, tenant: Tenant, identity: str, draft_id: str) -> PlanDraft:
        draft = await self._dialogue.get(tenant, draft_id)
        if draft.id not in {d.id for d in await self.mine(tenant, identity)}:
            raise PlanningError(f"no plan draft {draft_id!r} of yours")
        return draft

    async def answer(
        self,
        tenant: Tenant,
        identity: str,
        draft_id: str,
        field: str,
        value: Any,
        *,
        step_id: str | None = None,
        mode: Mode = Mode.GUIDED,
    ) -> PlanDraft:
        """One answer, or one field set, as a revision of the draft."""
        draft = await self.get(tenant, identity, draft_id)
        changes = await self._changes(tenant, draft, field, value, step_id, mode)
        return await self._dialogue.revise(
            ReviseDraft(draft_id=draft.id, tenant=tenant, by=identity, changes=changes)
        )

    async def set(
        self, tenant: Tenant, identity: str, draft_id: str, fields: Mapping[str, Any]
    ) -> PlanDraft:
        """The expert mode: every field given, at once, as one revision."""
        draft = await self.get(tenant, identity, draft_id)
        changes: dict[str, Any] = {}
        for name, value in fields.items():
            changes.update(await self._changes(tenant, draft, name, value, None, Mode.EXPERT))
        return await self._dialogue.revise(
            ReviseDraft(draft_id=draft.id, tenant=tenant, by=identity, changes=changes)
        )

    async def commission(self, tenant: Tenant, identity: str, draft_id: str) -> Plan:
        await self.get(tenant, identity, draft_id)
        return await self._dialogue.commission(
            CommissionDraft(draft_id=draft_id, tenant=tenant, by=identity)
        )

    async def templates(self, tenant: Tenant) -> list[dict[str, Any]]:
        """The process versions a guided answer may choose from, by name, with their level."""
        async with self._work.transaction(tenant):
            versions = await self._versions.list(tenant)
        return [
            {
                "ref": v.ref,
                "name": v.name,
                "level": v.autonomy_level,
                "steps": [s.id for s in v.steps],
            }
            for v in sorted(versions, key=lambda v: v.ref)
        ]

    def view(self, draft: PlanDraft, mode: Mode) -> dict[str, Any]:
        """What a surface shows of the draft in the mode."""
        question = next_question(draft)
        return {
            "draft": draft.document(),
            "mode": str(mode),
            "plan_version": draft.plan_id,
            "commissioned": draft.is_commissioned,
            "missing": list(draft.missing()),
            "unestimable": list(draft.unestimable()),
            "estimates": [e.shown() for e in draft.estimates],
            "settings": [
                {"field": s.field, "value": s.value, "why": s.why, "asked": s.asked}
                for s in settings(draft)
            ],
            "question": None
            if question is None or mode is Mode.EXPERT
            else {
                "field": question.field,
                "asks": question.asks,
                "explains": question.explains,
                "step_id": question.step_id,
            },
        }

    async def _changes(
        self,
        tenant: Tenant,
        draft: PlanDraft,
        field: str,
        value: Any,
        step_id: str | None,
        mode: Mode,
    ) -> dict[str, Any]:
        if field == "goal" or field == "autonomy_reason":
            text = str(value).strip()
            if not text:
                raise PlanningError(f"{field} is said in words")
            return {field: text}
        if field == "due":
            try:
                due = datetime.fromisoformat(str(value))
            except ValueError as error:
                raise PlanningError("the date it is due is a date, as 2026-12-01") from error
            if due.tzinfo is None:
                due = due.replace(tzinfo=self._clock.now().tzinfo)
            return {"due": due}
        if field == "autonomy_level":
            level = int(value)
            if mode is Mode.GUIDED and level not in SAFE_LEVELS:
                raise PlanningError("the guided start offers level 1 or 2 (ADR-0026)")
            return {"autonomy_level": level}
        if field == "steps":
            return await self._steps(tenant, value)
        if field == "estimates":
            return {"estimates": self._estimates(draft, value, step_id)}
        if field == "results_in":
            return {"results_in": PlanResult(str(value))}
        raise PlanningError(f"a plan draft has no field {field!r}")

    async def _steps(self, tenant: Tenant, value: Any) -> dict[str, Any]:
        """A chosen process version: its steps, the version and, for every step its measures
        do not estimate yet, nothing — the guided mode asks for those next."""
        ref = value.get("process_version") if isinstance(value, Mapping) else value
        if isinstance(ref, str):
            async with self._work.transaction(tenant):
                version = await self._versions.get(tenant, ref)
            if version is None:
                raise PlanningError(f"no process version {ref!r}")
            return {"steps": version.steps, "process_version": version.ref}
        if isinstance(value, list):
            return {"steps": tuple(Step.model_validate(s) for s in value)}
        raise PlanningError("steps are a process version to choose, or the steps themselves")

    @staticmethod
    def _estimates(draft: PlanDraft, value: Any, step_id: str | None) -> tuple[Estimate, ...]:
        given = value if isinstance(value, list) else [value]
        found = {e.step_id: e for e in draft.estimates}
        for one in given:
            if not isinstance(one, Mapping):
                one = {"figure": one}
            estimate = Estimate.model_validate({"step_id": step_id, **one})
            found[estimate.step_id] = estimate
        return tuple(found.values())
