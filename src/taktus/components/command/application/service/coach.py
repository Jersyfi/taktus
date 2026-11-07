"""Use case: the automation coach of one person (ADR-0240, UC-13.3).

Every call names the identity that asks, and reads and changes only what belongs to it: its
settings, its hints, its share. There is no call that reads another person's. The share across
people is `share_by_role`, which takes the roles and returns figures per role, never per person.

Whether an accepted hint's automation still runs is read from the ledger: a run of its process
version created within the tenant's period before the check (`check_lasting`).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import timedelta

from taktus.components.command.domain.model.coach import (
    CoachHint,
    CoachPolicy,
    CoachSettings,
    HintState,
    ProcedureDraft,
)
from taktus.components.command.domain.service import coach as rules
from taktus.ports.clock import Clock
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Command


class CoachError(Exception):
    pass


class Coach:
    def __init__(
        self,
        settings: Repository[CoachSettings],
        hints: Repository[CoachHint],
        policies: Repository[CoachPolicy],
        commands: Repository[Command],
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._settings = settings
        self._hints = hints
        self._policies = policies
        self._commands = commands
        self._ledger = ledger
        self._work = work
        self._clock = clock

    async def settings(self, tenant: Tenant, identity: str) -> CoachSettings:
        """The person's settings; a person who never set them has the coach on since the first
        time they were read, with the default number of hints."""
        async with self._work.transaction(tenant):
            found = await self._settings.get(tenant, identity)
            if found is None:
                found = CoachSettings(id=identity, tenant=tenant, observed_since=self._clock.now())
                await self._settings.put(tenant, found)
        return found

    async def set(
        self, tenant: Tenant, identity: str, *, on: bool, hints_per_week: int | None = None
    ) -> CoachSettings:
        """Switching the coach off is this one setting: from then on no request is read."""
        current = await self.settings(tenant, identity)
        since = current.observed_since
        if on and not current.on:
            since = self._clock.now()
        if not on:
            since = None
        changed = current.model_copy(
            update={
                "on": on,
                "observed_since": since,
                "hints_per_week": current.hints_per_week
                if hints_per_week is None
                else hints_per_week,
            }
        )
        changed = CoachSettings.model_validate(changed.model_dump())
        async with self._work.transaction(tenant):
            await self._settings.put(tenant, changed)
        return changed

    async def hints(self, tenant: Tenant, identity: str) -> list[CoachHint]:
        """The hints offered to the person and not yet answered, new ones offered first where
        due. Drawn from the person's own requests, and shown to the person only."""
        current = await self.settings(tenant, identity)
        now = self._clock.now()
        async with self._work.transaction(tenant):
            own = [h for h in await self._hints.list(tenant) if h.identity == identity]
            if current.on and current.observed_since is not None:
                found = rules.patterns(
                    await self._commands.list(tenant), identity, current.observed_since
                )
                for pattern in rules.due(current, found, own, now):
                    hint = CoachHint(
                        id=f"{identity}:{pattern.key}",
                        tenant=tenant,
                        identity=identity,
                        pattern=pattern.key,
                        says=pattern.says,
                        procedure=pattern.procedure,
                        offered_at=now,
                    )
                    await self._hints.put(tenant, hint)
                    own.append(hint)
        return [h for h in own if h.state is HintState.OFFERED]

    async def dismiss(self, tenant: Tenant, identity: str, hint_id: str) -> CoachHint:
        return await self._answer(tenant, identity, hint_id, HintState.DISMISSED, None)

    async def accept(
        self, tenant: Tenant, identity: str, hint_id: str, process_version: str
    ) -> CoachHint:
        return await self._answer(tenant, identity, hint_id, HintState.ACCEPTED, process_version)

    async def _answer(
        self,
        tenant: Tenant,
        identity: str,
        hint_id: str,
        state: HintState,
        process_version: str | None,
    ) -> CoachHint:
        async with self._work.transaction(tenant):
            hint = await self._hints.get(tenant, hint_id)
            if hint is None or hint.identity != identity:
                raise CoachError(f"no hint {hint_id!r} of yours")
            if hint.state is not HintState.OFFERED:
                raise CoachError(f"hint {hint_id!r} was {hint.state} already")
            answered = hint.model_copy(
                update={
                    "state": state,
                    "process_version": process_version,
                    "accepted_at": self._clock.now() if state is HintState.ACCEPTED else None,
                }
            )
            await self._hints.put(tenant, answered)
        return answered

    async def check_lasting(self, tenant: Tenant) -> list[CoachHint]:
        """Every accepted hint whose period has passed and was not checked, checked now: lasting
        when its process version had a run created within the period before now."""
        now = self._clock.now()
        async with self._work.transaction(tenant):
            policy = await self._policies.get(tenant, tenant) or CoachPolicy(id=tenant)
            period = timedelta(days=policy.lasting_days)
            due = [
                h
                for h in await self._hints.list(tenant)
                if h.state is HintState.ACCEPTED
                and h.lasting is None
                and h.accepted_at is not None
                and now - h.accepted_at >= period
            ]
            if not due:
                return []
            created = await self._ledger.of_kinds(tenant, ["run.created"], since=now - period)
            ran = {e.refs.process_version for e in created}
            checked = [h.model_copy(update={"lasting": h.process_version in ran}) for h in due]
            for hint in checked:
                await self._hints.put(tenant, hint)
        return checked

    async def own_share(self, tenant: Tenant, identity: str) -> tuple[int, int]:
        """Of the person's own accepted hints that were checked, how many lasted."""
        async with self._work.transaction(tenant):
            return rules.share(h for h in await self._hints.list(tenant) if h.identity == identity)

    async def share_by_role(
        self, tenant: Tenant, roles: Mapping[str, str]
    ) -> dict[str, tuple[int, int]]:
        """The share for each role, across the people `roles` places in it; never per person."""
        async with self._work.transaction(tenant):
            hints = await self._hints.list(tenant)
        grouped: dict[str, list[CoachHint]] = defaultdict(list)
        for hint in hints:
            role = roles.get(hint.identity)
            if role is not None:
                grouped[role].append(hint)
        return {role: rules.share(group) for role, group in sorted(grouped.items())}

    async def procedure(self, tenant: Tenant, identity: str, hint_id: str) -> ProcedureDraft:
        """What the coach hands to the skill lifecycle for one of the person's hints: the
        procedure, owned by the person, naming nobody."""
        async with self._work.transaction(tenant):
            hint = await self._hints.get(tenant, hint_id)
        if hint is None or hint.identity != identity:
            raise CoachError(f"no hint {hint_id!r} of yours")
        return ProcedureDraft(owner=identity, procedure=hint.procedure, pattern=hint.pattern)
