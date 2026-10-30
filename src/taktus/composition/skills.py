"""The skill lifecycle as the instance runs it (ADR-0162, UC-14.2, UC-4.4).

The catalogue keeps the records and their rules (`SkillCatalog`); what a stage needs from the
process and run components is read here, because only the composition root may hold them all:

- **The processes that use a skill**: every process whose active version has a step naming it
  in `work.skills`; the lowest of their levels decides who approves, and whether an `exact` step
  uses it decides the floor.
- **A round**: one guided evaluation per using process with cases (`Evaluations.start_guided`,
  purpose `skill`): the active side under the version in production, the proposed side with the
  evaluated version pinned. Its identifier is derived, so a second look starts nothing twice.
- **The takeover instructions' skill part**: for each step of a process, the skills it uses at
  their version in production, with their instructions (UC-6.3).
- **The look**, once a minute while the scheduler leads: drafts from recurring corrections;
  rounds advanced and scored; at level 4 the next round once a day, and approval by rule once
  n passed; an approved version put into production; a version in production measured on the
  drift evaluations whose runs pinned it, and fallen back by rule when it is worse.

`CatalogGuidance` answers the run's `Guidance` port from the catalogue: the version of a skill
in production, its instructions, and a shared agent's profile brief (ADR-0163).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection, Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import structlog
import yaml

from taktus.components.catalog.application.service import AgentCatalog, SkillCatalog
from taktus.components.catalog.domain.model import (
    InvalidSkill,
    Measurement,
    OriginKind,
    Round,
    RoundState,
    SkillError,
    SkillFile,
    SkillOrigin,
    SkillStage,
    SkillVersion,
)
from taktus.components.catalog.domain.service import skills as rules
from taktus.components.governance.application.service import Drifts
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.process.domain.model.evaluation import (
    Evaluation,
    EvaluationState,
    Purpose,
    Side,
    Verdict,
)
from taktus.components.run.domain.model import Run, RunState
from taktus.composition.evaluations import INTERVAL_SECONDS, Evaluations, Guide
from taktus.composition.tenancy import this_round
from taktus.ports.clock import Clock
from taktus.ports.identity import ServedTenants
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork

log = structlog.get_logger("taktus.skills")

CORRECTIONS = ("step.corrected", "proposal.decided")
ROUND_EVERY_SECONDS = 86400
"""At level 4 the next round of a version starts once a day (ADR-0162 §4)."""


# --- reading skills from a bundle ----------------------------------------------------------------


def skill_on_disk(directory: Path) -> SkillFile:
    """The skill a directory holds: its `SKILL.md` and every other file below it, parsed by
    the catalogue's rule. InvalidSkill where it does not hold to the open format."""
    path = directory / rules.FILE
    if not path.is_file():
        raise InvalidSkill((f"{directory} holds no {rules.FILE}",))
    files = {
        str(p.relative_to(directory)): p.read_bytes()
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }
    front_text, body = rules.split(files[rules.FILE].decode("utf-8"))
    try:
        front = yaml.safe_load(front_text)
    except yaml.YAMLError as error:
        raise InvalidSkill((f"{rules.FILE}: the front matter is not YAML: {error}",)) from error
    return rules.parse(directory.name, front, body, files)


def skills_below(root: Path) -> list[tuple[Path, SkillFile | InvalidSkill]]:
    """Every skill directory under a `skills/` directory below `root`, parsed or with why
    not."""
    found: list[tuple[Path, SkillFile | InvalidSkill]] = []
    for marker in sorted(root.rglob(rules.FILE)):
        directory = marker.parent
        if directory.parent.name != "skills":
            continue
        try:
            found.append((directory, skill_on_disk(directory)))
        except InvalidSkill as error:
            found.append((directory, error))
    return found


# --- the run's port ------------------------------------------------------------------------------


class CatalogGuidance:
    """The run's `Guidance`, answered from the catalogue."""

    def __init__(self, skills: SkillCatalog, agents: AgentCatalog | None = None) -> None:
        self._skills = skills
        self._agents = agents

    async def production(self, tenant: Tenant, names: Collection[str]) -> Mapping[str, str]:
        found: dict[str, str] = {}
        for name in names:
            version = await self._skills.production(tenant, name)
            if version is not None:
                found[name] = version.version
        return found

    async def skill(self, tenant: Tenant, name: str, version: str) -> str | None:
        found = await self._skills.get(tenant, f"{name}@{version}")
        if found is None or found.private:
            return None
        return found.file.instructions

    async def profile(self, tenant: Tenant, profile: str) -> str | None:
        if self._agents is None:
            return None
        return await self._agents.brief(tenant, profile)


# --- the lifecycle -------------------------------------------------------------------------------


class SkillLifecycle:
    def __init__(
        self,
        *,
        catalog: SkillCatalog,
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
        evaluations: Evaluations,
        evaluation_records: Repository[Evaluation],
        runs: Repository[Run],
        drifts: Drifts,
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._catalog = catalog
        self._processes = processes
        self._versions = versions
        self._evaluations = evaluations
        self._records = evaluation_records
        self._runs = runs
        self._drifts = drifts
        self._ledger = ledger
        self._work = work
        self._clock = clock

    # --- what uses a skill -----------------------------------------------------------------

    async def using(self, tenant: Tenant, name: str) -> list[ProcessVersion]:
        """The active versions whose steps name the skill."""
        async with self._work.transaction(tenant):
            processes = await self._processes.list(tenant)
            active = [
                await self._versions.get(tenant, f"{p.id}@{p.active_version}")
                for p in processes
                if p.active_version is not None
            ]
        return sorted(
            (v for v in active if v is not None and name in v.skills_used()),
            key=lambda v: v.ref,
        )

    async def standing(self, tenant: Tenant, name: str) -> tuple[int, bool]:
        """The lowest level among the processes using the skill, and whether an `exact` step
        uses it. A skill nothing uses is held at level 1: a person approves it."""
        using = await self.using(tenant, name)
        if not using:
            return 1, False
        return min(v.autonomy_level for v in using), any(v.exact_for(name) for v in using)

    # --- acts ------------------------------------------------------------------------------

    async def register_directory(
        self, tenant: Tenant, root: Path, version: str, by: str | None = None
    ) -> tuple[list[SkillVersion], list[tuple[Path, InvalidSkill]]]:
        """Every skill under a `skills/` directory below `root`, registered as a draft."""
        registered: list[SkillVersion] = []
        refused: list[tuple[Path, InvalidSkill]] = []
        for directory, parsed in skills_below(root):
            if isinstance(parsed, InvalidSkill):
                refused.append((directory, parsed))
                continue
            registered.append(
                await self._catalog.register(
                    tenant,
                    parsed,
                    version,
                    SkillOrigin(kind=OriginKind.BUNDLE, source=str(directory)),
                    by=by,
                )
            )
        return registered, refused

    async def start_round(self, tenant: Tenant, skill_id: str, key: str | None = None) -> Round:
        """A round of the version on the cases of every process that uses it. SkillError
        `unevaluable` where none of them has cases: the draft stays a draft."""
        version = await self._known(tenant, skill_id)
        if version.private:
            raise SkillError("private", f"{skill_id} is private until its owner shares it")
        round_id = f"rnd_{skill_id}_{key or len(version.rounds) + 1}"
        if any(r.id == round_id for r in version.rounds):
            return next(r for r in version.rounds if r.id == round_id)
        current = await self._catalog.production(tenant, version.name)
        in_force = None if current is None or current.id == skill_id else current.version
        started: list[str] = []
        for using in await self.using(tenant, version.name):
            evaluation = await self._evaluations.start_guided(
                tenant,
                using.process_id,
                purpose=Purpose.SKILL,
                subject=skill_id,
                active=Guide(skills={version.name: in_force}),
                proposed=Guide(skills={version.name: version.version}),
                evaluation_id=f"evl_{round_id}_{using.process_id}",
            )
            if evaluation is not None:
                started.append(evaluation.id)
        if not started:
            await self._catalog.refused(tenant, version, "unevaluable")
            raise SkillError(
                "unevaluable",
                f"no process that uses {version.name} has evaluation cases to hold {skill_id} "
                "to; a draft without an evaluation is never approved",
            )
        begun = Round(id=round_id, evaluations=tuple(started), started_at=self._clock.now())
        await self._catalog.round_started(tenant, skill_id, begun)
        return begun

    async def advance_round(self, tenant: Tenant, skill_id: str, round_id: str) -> SkillVersion:
        """The round's evaluations advanced; once all are scored, the round scored on the
        record: passed when every evaluation passed, its dry run completed when every case run
        of the proposed sides finished."""
        version = await self._known(tenant, skill_id)
        found = next((r for r in version.rounds if r.id == round_id), None)
        if found is None or found.state is not RoundState.RUNNING:
            return version
        scored = [await self._evaluations.advance(tenant, e) for e in found.evaluations]
        if any(e.state is not EvaluationState.SCORED for e in scored):
            return version
        passed = all(e.verdict is Verdict.PASSED for e in scored)
        sides = [e.side(Side.PROPOSED) for e in scored]
        scores = [s.score for s in sides if s is not None and s.score is not None]
        score = sum(scores) / len(scores) if len(scores) == len(scored) and scores else None
        dry_run = await self._dry_run_completed(tenant, scored)
        return await self._catalog.round_scored(
            tenant, skill_id, round_id, passed=passed, score=score, dry_run=dry_run
        )

    async def approve(self, tenant: Tenant, skill_id: str, by: str | None) -> SkillVersion:
        version = await self._known(tenant, skill_id)
        level, exact = await self.standing(tenant, version.name)
        return await self._catalog.approve(tenant, skill_id, level=level, exact=exact, by=by)

    async def produce(self, tenant: Tenant, skill_id: str, by: str | None = None) -> SkillVersion:
        version = await self._known(tenant, skill_id)
        using = await self.using(tenant, version.name)
        return await self._catalog.produce(tenant, skill_id, [v.ref for v in using], by)

    async def takeover(self, tenant: Tenant, process_id: str) -> list[dict[str, Any]]:
        """The skill part of a process's takeover instructions: for each step that uses skills,
        each skill at its version in production, with its instructions (UC-6.3)."""
        async with self._work.transaction(tenant):
            process = await self._processes.get(tenant, process_id)
            version = (
                None
                if process is None or process.active_version is None
                else await self._versions.get(tenant, f"{process_id}@{process.active_version}")
            )
        if version is None:
            raise SkillError("unknown", f"the process {process_id!r} has no active version")
        steps: list[dict[str, Any]] = []
        used = version.skills_used()
        for step in version.ordered():
            named = [name for name, at in used.items() if step.id in at]
            if not named:
                continue
            entries = []
            for name in named:
                current = await self._catalog.production(tenant, name)
                entries.append(
                    {"skill": name, "version": None, "instructions": None}
                    if current is None
                    else {
                        "skill": name,
                        "version": current.version,
                        "instructions": current.file.instructions,
                    }
                )
            steps.append({"step": step.id, "skills": entries})
        return steps

    # --- the look --------------------------------------------------------------------------

    async def look(self, tenant: Tenant) -> None:
        """What the scheduler does once a minute for a tenant (ADR-0162)."""
        await self.draft_from_corrections(tenant)
        tolerance = (await self._drifts.configuration(tenant)).evaluation_tolerance
        for version in await self._catalog.of_tenant(tenant, viewer=None):
            try:
                await self._look_at(tenant, version, tolerance)
            except SkillError as error:
                log.info("skill look", tenant=tenant, skill=version.id, held=error.reason)

    async def _look_at(self, tenant: Tenant, version: SkillVersion, tolerance: float) -> None:
        for running in [r for r in version.rounds if r.state is RoundState.RUNNING]:
            version = await self.advance_round(tenant, version.id, running.id)
        if version.stage is SkillStage.EVALUATED:
            level, exact = await self.standing(tenant, version.name)
            if level < 4:
                return  # a person approves
            policy = await self._catalog.policy(tenant)
            if rules.approval(version, level, policy, exact=exact).due:
                version = await self._catalog.approve(
                    tenant, version.id, level=level, exact=exact, by=None
                )
            elif not any(r.state is RoundState.RUNNING for r in version.rounds):
                await self._next_round(tenant, version)
                return
        if version.stage is SkillStage.APPROVED:
            version = await self.produce(tenant, version.id)
        if version.stage is SkillStage.PRODUCTION:
            await self._measure(tenant, version)
            await self._catalog.fall_back(tenant, version.id, tolerance)

    async def _next_round(self, tenant: Tenant, version: SkillVersion) -> None:
        last = max((r.started_at for r in version.rounds), default=None)
        now = self._clock.now()
        if last is not None and (now - last).total_seconds() < ROUND_EVERY_SECONDS:
            return
        await self.start_round(tenant, version.id, key=now.date().isoformat())

    async def _measure(self, tenant: Tenant, version: SkillVersion) -> None:
        """Every scored drift evaluation of a using process whose runs pinned the version, since
        it entered production, as a measurement in operation."""
        since = next(
            (c.at for c in reversed(version.history) if c.stage is SkillStage.PRODUCTION), None
        )
        if since is None:
            return
        processes = {v.process_id for v in await self.using(tenant, version.name)}
        async with self._work.transaction(tenant):
            drifts = [
                e
                for e in await self._records.list(tenant)
                if e.purpose is Purpose.DRIFT
                and e.process_id in processes
                and e.state is EvaluationState.SCORED
                and e.scored_at is not None
                and e.scored_at >= since
            ]
        known = {m.evaluation for m in version.measurements}
        for evaluation in sorted(drifts, key=lambda e: e.scored_at or since):
            side = evaluation.side(Side.ACTIVE)
            if evaluation.id in known or side is None or side.score is None:
                continue
            if not await self._pinned(tenant, evaluation, version):
                continue
            await self._catalog.measured(
                tenant,
                version.id,
                Measurement(
                    source="operation",
                    evaluation=evaluation.id,
                    score=side.score,
                    at=evaluation.scored_at or since,
                ),
            )

    async def _pinned(self, tenant: Tenant, evaluation: Evaluation, version: SkillVersion) -> bool:
        async with self._work.transaction(tenant):
            runs = [await self._runs.get(tenant, r.run_id) for r in evaluation.runs if r.run_id]
        return any(r is not None and r.skills.get(version.name) == version.version for r in runs)

    async def draft_from_corrections(self, tenant: Tenant) -> list[SkillVersion]:
        """Every step corrected in at least three distinct runs becomes a draft skill, once
        (UC-4.4). Read: the process, the step and the run of each correction — never who."""
        async with self._work.transaction(tenant):
            entries = await self._ledger.of_kinds(tenant, CORRECTIONS)
        corrections = [
            (e.refs.process_version.split("@", 1)[0], e.refs.step_id, e.refs.run_id)
            for e in entries
            if e.refs.process_version is not None
            and e.refs.step_id is not None
            and e.refs.run_id is not None
            and not e.rehearsal
            and (e.kind == "step.corrected" or e.outcome == "corrected")
        ]
        drafted: list[SkillVersion] = []
        known = {v.name for v in await self._catalog.of_tenant(tenant, viewer=None)}
        for recurrence in rules.recurring(corrections):
            name = rules.drafted_name(recurrence.process, recurrence.step)
            if not name or name in known:
                continue
            instructions = rules.drafted_instructions(recurrence)
            file = rules.parse(
                name,
                {
                    "name": name,
                    "description": (
                        f"How the step {recurrence.step} of the process {recurrence.process} "
                        "is done, drawn from corrections that recurred."
                    ),
                },
                instructions,
                {rules.FILE: instructions.encode("utf-8")},
            )
            drafted.append(
                await self._catalog.register(
                    tenant,
                    file,
                    "1",
                    SkillOrigin(
                        kind=OriginKind.RECURRING,
                        processes=(recurrence.process,),
                        steps=(f"{recurrence.process}/{recurrence.step}",),
                        runs=recurrence.runs,
                        corrections=len(recurrence.runs),
                    ),
                )
            )
        return drafted

    # --- helpers ---------------------------------------------------------------------------

    async def _dry_run_completed(self, tenant: Tenant, scored: list[Evaluation]) -> bool:
        async with self._work.transaction(tenant):
            runs = [
                await self._runs.get(tenant, r.run_id)
                for e in scored
                for r in e.runs
                if r.side is Side.PROPOSED and r.run_id is not None
            ]
        return bool(runs) and all(
            r is not None and r.rehearsal and r.state is RunState.FINISHED for r in runs
        )

    async def _known(self, tenant: Tenant, skill_id: str) -> SkillVersion:
        found = await self._catalog.get(tenant, skill_id)
        if found is None:
            raise SkillError("unknown", f"no skill version {skill_id!r}")
        return found


def skills_tick(
    lifecycle: SkillLifecycle,
    tenants: ServedTenants,
    clock: Clock,
    *,
    interval_seconds: int = INTERVAL_SECONDS,
) -> Callable[[], Awaitable[None]]:
    """What the scheduler calls on every tick: every tenant's skills are looked at once the
    interval has passed. A look that fails is logged and made again at the next interval."""
    last: list[datetime] = []

    async def tick() -> None:
        now = clock.now()
        if last and now - last[0] < timedelta(seconds=interval_seconds):
            return
        last[:] = [now]
        for tenant in await this_round(tenants, "scheduler"):
            try:
                await lifecycle.look(tenant)
            except Exception as error:  # a look never takes the scheduler down
                log.error(
                    "skills not looked at; the next look tries again",
                    tenant=tenant,
                    error=f"{type(error).__name__}: {error}",
                )

    return tick
