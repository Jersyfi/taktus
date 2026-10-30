"""Use case: a skill version moves through its lifecycle, and every stage is in the ledger
(ADR-0162, UC-14.2).

Each act opens one unit of work: the record changes and its ledger entry is written in the same
transaction, with the skill version in `refs.skill_id`. An act the order or the policy refuses
writes `skill.refused`, with the reason as outcome, commits it, and raises `SkillError`; the
record does not change.

What a round ran and how it scored, the lowest level of the processes using a skill and whether
an `exact` step uses it are read outside this component and handed in: they belong to the
process and run components, and the composition root meets them here.
"""

from __future__ import annotations

from collections.abc import Sequence

from taktus.components.catalog.domain.model.skill import (
    Measurement,
    OriginKind,
    Round,
    RoundState,
    SkillError,
    SkillFile,
    SkillOrigin,
    SkillOwnership,
    SkillPolicy,
    SkillStage,
    SkillVersion,
    StageChange,
)
from taktus.components.catalog.domain.service import skills
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

DRAFTED = "skill.drafted"
SHARED = "skill.shared"
EVALUATED = "skill.evaluated"
APPROVED = "skill.approved"
INSTRUCTED = "skill.instructed"
PRODUCED = "skill.produced"
RETIRED = "skill.retired"
REFUSED = "skill.refused"
CONFIGURED = "skills.configured"

KIND_OF: dict[SkillStage, str] = {
    SkillStage.EVALUATED: EVALUATED,
    SkillStage.APPROVED: APPROVED,
    SkillStage.PRODUCTION: PRODUCED,
    SkillStage.RETIRED: RETIRED,
}
DRAFT_REASON: dict[OriginKind, str] = {
    OriginKind.BUNDLE: "registered",
    OriginKind.RECURRING: "recurring",
    OriginKind.OWN_USE: "owner",
}


class SkillCatalog:
    def __init__(
        self,
        versions: Repository[SkillVersion],
        policies: Repository[SkillPolicy],
        owners: Repository[SkillOwnership],
        work: UnitOfWork,
        ledger: Ledger,
        clock: Clock,
    ) -> None:
        self._owners = owners
        self._versions = versions
        self._policies = policies
        self._work = work
        self._ledger = ledger
        self._clock = clock

    # --- reading ----------------------------------------------------------------------------

    async def get(self, tenant: Tenant, skill_id: str) -> SkillVersion | None:
        async with self._work.transaction(tenant):
            return await self._versions.get(tenant, skill_id)

    async def of_tenant(self, tenant: Tenant, viewer: str | None = None) -> list[SkillVersion]:
        """Every version the viewer may see: a private draft only by its owner."""
        async with self._work.transaction(tenant):
            found = await self._versions.list(tenant)
            mine = {o.id for o in await self._owners.list(tenant) if o.owner == viewer}
        return sorted((v for v in found if not v.private or v.id in mine), key=lambda v: v.id)

    async def production(self, tenant: Tenant, name: str) -> SkillVersion | None:
        """The version of the skill in production; None while none is."""
        async with self._work.transaction(tenant):
            found = await self._versions.list(tenant)
        return next((v for v in found if v.name == name and v.stage is SkillStage.PRODUCTION), None)

    async def policy(self, tenant: Tenant) -> SkillPolicy:
        async with self._work.transaction(tenant):
            stored = await self._policies.get(tenant, "skills")
        return stored or SkillPolicy(tenant=tenant)

    # --- registering ------------------------------------------------------------------------

    async def register(
        self,
        tenant: Tenant,
        file: SkillFile,
        version: str,
        origin: SkillOrigin,
        *,
        owner: str | None = None,
        by: str | None = None,
    ) -> SkillVersion:
        """A draft of the skill, or the version as it was stored when its content is the same.
        Another content under a stored version is refused: a registered version never
        changes."""
        skill_id = f"{file.name}@{version}"
        async with self._work.transaction(tenant):
            stored = await self._versions.get(tenant, skill_id)
            if stored is not None:
                if stored.file.digest == file.digest:
                    return stored
                raise SkillError(
                    "changed",
                    f"{skill_id} is registered with another content, and a registered version "
                    "never changes: give the skill a new version",
                )
            current = next(
                (
                    v
                    for v in await self._versions.list(tenant)
                    if v.name == file.name and v.stage is SkillStage.PRODUCTION
                ),
                None,
            )
            now = self._clock.now()
            reason = DRAFT_REASON[origin.kind]
            drafted = SkillVersion(
                id=skill_id,
                tenant=tenant,
                name=file.name,
                version=version,
                file=file,
                origin=origin,
                owned=owner is not None,
                stage=SkillStage.DRAFT,
                history=(StageChange(stage=SkillStage.DRAFT, at=now, reason=reason),),
                predecessor=None if current is None else current.id,
                registered_at=now,
            )
            await self._versions.put(tenant, drafted)
            if owner is not None:
                await self._owners.put(
                    tenant, SkillOwnership(id=skill_id, tenant=tenant, owner=owner)
                )
            # A person's own draft is recorded without naming the person (principle 14).
            await self._record(tenant, DRAFTED, drafted, reason, actor=None if owner else by)
        return drafted

    async def share(self, tenant: Tenant, skill_id: str, by: str) -> SkillVersion:
        """The owner's act that makes a draft drawn from their own use the tenant's."""
        version = await self._known(tenant, skill_id)
        if not version.owned or version.shared:
            return version
        async with self._work.transaction(tenant):
            ownership = await self._owners.get(tenant, skill_id)
        if ownership is None or by != ownership.owner:
            await self.refused(tenant, version, "owner")
            raise SkillError("owner", f"only the owner of {skill_id} shares it")
        shared = version.model_copy(update={"shared": True})
        async with self._work.transaction(tenant):
            await self._versions.put(tenant, shared)
            await self._record(tenant, SHARED, shared, "owner")
        return shared

    # --- rounds -----------------------------------------------------------------------------

    async def round_started(self, tenant: Tenant, skill_id: str, started: Round) -> SkillVersion:
        version = await self._known(tenant, skill_id)
        if version.private:
            await self.refused(tenant, version, "private")
            raise SkillError("private", f"{skill_id} is private until its owner shares it")
        if any(r.id == started.id for r in version.rounds):
            return version
        changed = version.model_copy(update={"rounds": (*version.rounds, started)})
        async with self._work.transaction(tenant):
            await self._versions.put(tenant, changed)
        return changed

    async def round_scored(
        self,
        tenant: Tenant,
        skill_id: str,
        round_id: str,
        *,
        passed: bool,
        score: float | None,
        dry_run: bool,
    ) -> SkillVersion:
        """The round's verdict on the record, and its score as a measurement. A draft whose first
        passed round completed its dry run becomes `evaluated` in the same transaction."""
        version = await self._known(tenant, skill_id)
        now = self._clock.now()
        rounds = tuple(
            r.model_copy(
                update={
                    "state": RoundState.PASSED if passed else RoundState.FAILED,
                    "score": score,
                    "dry_run": dry_run,
                    "scored_at": now,
                }
            )
            if r.id == round_id and r.state is RoundState.RUNNING
            else r
            for r in version.rounds
        )
        measurements = version.measurements
        if score is not None:
            measurements = (
                *measurements,
                Measurement(source="round", evaluation=round_id, score=score, at=now),
            )
        changed = version.model_copy(update={"rounds": rounds, "measurements": measurements})
        async with self._work.transaction(tenant):
            if changed.stage is SkillStage.DRAFT and skills.passed_round(changed) is not None:
                changed = skills.advanced(changed, SkillStage.EVALUATED, now, "round")
                await self._record(tenant, EVALUATED, changed, "round")
            await self._versions.put(tenant, changed)
        return changed

    async def measured(
        self, tenant: Tenant, skill_id: str, measurement: Measurement
    ) -> SkillVersion:
        version = await self._known(tenant, skill_id)
        if any(m.evaluation == measurement.evaluation for m in version.measurements):
            return version
        changed = version.model_copy(update={"measurements": (*version.measurements, measurement)})
        async with self._work.transaction(tenant):
            await self._versions.put(tenant, changed)
        return changed

    # --- the stages -------------------------------------------------------------------------

    async def evaluate(self, tenant: Tenant, skill_id: str) -> SkillVersion:
        """Moves a draft on when it has a passed round with a completed dry run; refuses one
        without: a draft without an evaluation is never approved."""
        return await self._advance(tenant, skill_id, SkillStage.EVALUATED, "round", None)

    async def approve(
        self, tenant: Tenant, skill_id: str, *, level: int, exact: bool, by: str | None
    ) -> SkillVersion:
        """A person's approval at any level; the rule's at level 4 once n rounds in a row passed
        (`by` None). Refused otherwise, with the reason as outcome."""
        version = await self._known(tenant, skill_id)
        if by is None:
            decided = skills.approval(version, level, await self.policy(tenant), exact=exact)
            if not decided.by_rule:
                await self.refused(tenant, version, "person")
                raise SkillError(
                    "person",
                    f"{skill_id} is used at autonomy level {level}; a person approves it",
                )
            if not decided.due:
                await self.refused(tenant, version, "floor")
                raise SkillError(
                    "floor",
                    f"{skill_id} passed {decided.passed} round(s) in a row; the rule approves "
                    f"it after {decided.required}",
                )
        return await self._advance(
            tenant, skill_id, SkillStage.APPROVED, "person" if by else "rule", by
        )

    async def produce(
        self, tenant: Tenant, skill_id: str, processes: Sequence[str], by: str | None = None
    ) -> SkillVersion:
        """Into production: first the takeover instructions of every process using it name it
        (`skill.instructed` per process version), then the version in production before it
        retires, then this one is produced — one transaction."""
        version = await self._known(tenant, skill_id)
        now = self._clock.now()
        try:
            produced = skills.advanced(version, SkillStage.PRODUCTION, now, "approved")
        except SkillError as error:
            await self.refused(tenant, version, error.reason)
            raise
        async with self._work.transaction(tenant):
            for process_version in sorted(set(processes)):
                await self._ledger.record(
                    tenant,
                    Fact(
                        kind=INSTRUCTED,
                        refs=LedgerRefs(
                            tenant=tenant,
                            skill_id=skill_id,
                            process_version=process_version,
                            actor=by,
                        ),
                        outcome="named",
                    ),
                )
            for other in await self._versions.list(tenant):
                if (
                    other.name == version.name
                    and other.id != skill_id
                    and other.stage is SkillStage.PRODUCTION
                ):
                    retired = skills.advanced(other, SkillStage.RETIRED, now, "successor")
                    await self._versions.put(tenant, retired)
                    await self._record(tenant, RETIRED, retired, "successor")
            await self._versions.put(tenant, produced)
            await self._record(tenant, PRODUCED, produced, "approved", actor=by)
        return produced

    async def fall_back(self, tenant: Tenant, skill_id: str, tolerance: float) -> bool:
        """The rule over the measurements: a version in production worse than its predecessor
        beyond the tolerance retires, and the predecessor returns to production."""
        version = await self._known(tenant, skill_id)
        if version.stage is not SkillStage.PRODUCTION or version.predecessor is None:
            return False
        predecessor = await self.get(tenant, version.predecessor)
        if not skills.falls_back(version, predecessor, tolerance) or predecessor is None:
            return False
        now = self._clock.now()
        retired = skills.advanced(version, SkillStage.RETIRED, now, "fallback")
        restored = skills.advanced(predecessor, SkillStage.PRODUCTION, now, "fallback")
        async with self._work.transaction(tenant):
            await self._versions.put(tenant, retired)
            await self._record(tenant, RETIRED, retired, "fallback")
            await self._versions.put(tenant, restored)
            await self._record(tenant, PRODUCED, restored, "fallback")
        return True

    async def retire(self, tenant: Tenant, skill_id: str, by: str) -> SkillVersion:
        return await self._advance(tenant, skill_id, SkillStage.RETIRED, "person", by)

    # --- the policy -------------------------------------------------------------------------

    async def configure(
        self,
        tenant: Tenant,
        *,
        floor: int | None = None,
        exact_factor: int | None = None,
        n: int | None = None,
        by: str,
    ) -> SkillPolicy:
        """The tenant's policy. A value below the shipped floor or factor, or an n below the
        floor, is refused (DEC-0028)."""
        current = await self.policy(tenant)
        try:
            policy = SkillPolicy(
                tenant=tenant,
                floor=current.floor if floor is None else floor,
                exact_factor=current.exact_factor if exact_factor is None else exact_factor,
                n=current.n if n is None else n,
            )
        except ValueError as error:
            async with self._work.transaction(tenant):
                await self._ledger.record(
                    tenant,
                    Fact(
                        kind=REFUSED,
                        refs=LedgerRefs(tenant=tenant, actor=by),
                        outcome="below_floor",
                    ),
                )
            raise SkillError("below_floor", _first(error)) from error
        async with self._work.transaction(tenant):
            await self._policies.put(tenant, policy)
            await self._ledger.record(
                tenant,
                Fact(
                    kind=CONFIGURED, refs=LedgerRefs(tenant=tenant, actor=by), outcome="configured"
                ),
            )
        return policy

    # --- helpers ----------------------------------------------------------------------------

    async def _known(self, tenant: Tenant, skill_id: str) -> SkillVersion:
        found = await self.get(tenant, skill_id)
        if found is None:
            raise SkillError("unknown", f"no skill version {skill_id!r}")
        return found

    async def _advance(
        self, tenant: Tenant, skill_id: str, to: SkillStage, reason: str, by: str | None
    ) -> SkillVersion:
        version = await self._known(tenant, skill_id)
        try:
            changed = skills.advanced(version, to, self._clock.now(), reason)
        except SkillError as error:
            await self.refused(tenant, version, error.reason)
            raise
        async with self._work.transaction(tenant):
            await self._versions.put(tenant, changed)
            await self._record(tenant, KIND_OF[to], changed, reason, actor=by)
        return changed

    async def refused(self, tenant: Tenant, version: SkillVersion, reason: str) -> None:
        """An act refused, recorded as `skill.refused` with the reason as outcome."""
        async with self._work.transaction(tenant):
            await self._record(tenant, REFUSED, version, reason)

    async def _record(
        self,
        tenant: Tenant,
        kind: str,
        version: SkillVersion,
        outcome: str,
        *,
        actor: str | None = None,
    ) -> None:
        await self._ledger.record(
            tenant,
            Fact(
                kind=kind,
                refs=LedgerRefs(tenant=tenant, skill_id=version.id, actor=actor),
                outcome=outcome,
                content_digest=version.file.digest,
            ),
        )


def _first(error: ValueError) -> str:
    """The first reason of a refused policy, without the validator's frame."""
    errors = getattr(error, "errors", None)
    if callable(errors):
        found = errors()
        if found:
            return str(found[0]["msg"]).removeprefix("Value error, ")
    return str(error)
