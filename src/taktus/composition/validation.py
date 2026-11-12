"""Whether the quality held with a model, per process, and which models a step may reach in a
real run (ADR-0249).

A **validation** is what a trial of a purpose (ADR-0149) says about one model and one process:
the model's score on each step of the purpose, by the process's rules, beside the score the
process's active version had in its newest scored evaluation, scored by the same rules. The
quality **held** where no step fell by more than its tolerance (ADR-0250); it **fell** where one
did; it is **pending** while a case run of the trial has not settled. A process that has no
scored evaluation yet is held to its targets: a step holds where its score reaches 1 less its
tolerance.

`Validations` answers the run's port `Evaluated`. A step whose process evaluates it on at least
one case may reach, in a real run, only a model whose newest settled validation for that
process held. A rehearsal is not held to it, and neither is a trial's own case run.

This is wiring: a validation reads the trials in the ledger, the process's versions, its runs
and its evaluations, and only the composition root may hold them all.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping

from taktus.components.accounting.application.service import Held, Trial, Validation
from taktus.components.process.domain.model import EvaluationCase, ProcessVersion
from taktus.components.process.domain.model.evaluation import Side
from taktus.components.process.domain.service import scoring
from taktus.components.run.domain.model import Run
from taktus.composition.evaluations import Evaluations, settled
from taktus.composition.trials import step_purposes
from taktus.ports.ledger import Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Repository, Tenant, UnitOfWork

STARTED = "trial.started"


class Validations:
    def __init__(
        self,
        *,
        versions: Repository[ProcessVersion],
        runs: Repository[Run],
        ledger: Ledger,
        objects: ObjectStore,
        work: UnitOfWork,
    ) -> None:
        self._versions = versions
        self._runs = runs
        self._ledger = ledger
        self._objects = objects
        self._work = work
        self._evaluations: Evaluations | None = None

    def attach(self, evaluations: Evaluations) -> None:
        """The evaluations, built after the engine that asks this (the engine runs their
        cases)."""
        self._evaluations = evaluations

    # --- the port of the run ----------------------------------------------------------------

    async def unevaluated(
        self,
        tenant: Tenant,
        process_version: str,
        step_id: str,
        purpose: str,
        adapters: Collection[str],
    ) -> frozenset[str]:
        if self._evaluations is None:
            return frozenset()
        async with self._work.transaction(tenant):
            version = await self._versions.get(tenant, process_version)
        if (
            version is None
            or version.evaluation is None
            or step_id not in version.evaluation.scored_steps
        ):
            return frozenset()
        cases, _ = await self._evaluations.evaluation_set(tenant, version)
        if not any(step_id in case.targets for case in cases):
            return frozenset()
        standing = await self.standing(tenant, purpose, version.process_id)
        return frozenset(a for a in adapters if standing.get(a) != "held")

    # --- reading ----------------------------------------------------------------------------

    async def standing(self, tenant: Tenant, purpose: str, process_id: str) -> dict[str, Held]:
        """Per model, its newest settled validation for the process; a model whose every
        validation is pending stands as pending, and one never tried is not named."""
        found: dict[str, Held] = {}
        for trial in await self._trials(tenant, purpose):
            for validation in await self.of_trial(tenant, trial):
                if validation.process != process_id:
                    continue
                known = found.get(validation.model)
                if known is None or (known == "pending" and validation.verdict != "pending"):
                    found[validation.model] = validation.verdict
        return found

    async def of_trial(self, tenant: Tenant, trial: Trial) -> list[Validation]:
        """Every model and process the trial ran cases of, with whether the quality held."""
        if self._evaluations is None:
            return []
        by_process: dict[str, list[tuple[str, str, str]]] = {}
        for case in trial.cases:
            if case.named:
                continue  # a named case has no target: it says nothing about quality
            process_id = case.key.split("/", 1)[0]
            by_process.setdefault(process_id, []).append(
                (case.key, case.process_version, case.case)
            )
        found: list[Validation] = []
        for process_id, cases in sorted(by_process.items()):
            async with self._work.transaction(tenant):
                version = await self._versions.get(tenant, cases[0][1])
            if version is None or version.evaluation is None:
                continue
            steps = _steps_of(version, trial.purpose)
            evaluated, _ = await self._evaluations.evaluation_set(tenant, version)
            by_id = {c.id: c for c in evaluated}
            baseline = await self._baseline(tenant, version, by_id, steps)
            tenant_tolerance = await self._evaluations.tenant_tolerance(tenant)
            declared, ceilings = version.tolerance_bounds()
            tolerances = {
                step: tolerance
                for step, tolerance in scoring.step_tolerances(
                    declared, ceilings, tenant_tolerance
                ).items()
                if step in steps
            }
            for model, runs in sorted(trial.runs.items()):
                found.append(
                    await self._judged(
                        tenant,
                        trial,
                        process_id,
                        model,
                        runs,
                        cases,
                        by_id,
                        version,
                        steps,
                        baseline,
                        tolerances,
                    )
                )
        return found

    async def _judged(
        self,
        tenant: Tenant,
        trial: Trial,
        process_id: str,
        model: str,
        runs: Mapping[str, str],
        cases: list[tuple[str, str, str]],
        by_id: Mapping[str, EvaluationCase],
        version: ProcessVersion,
        steps: frozenset[str],
        baseline: dict[str, float | None],
        tolerances: dict[str, float],
    ) -> Validation:
        assert self._evaluations is not None  # noqa: S101 — of_trial returned before otherwise
        per_step: dict[str, list[float | None]] = {}
        pending = False
        for key, _, case_id in cases:
            case = by_id.get(case_id)
            run_id = runs.get(key)
            if case is None or run_id is None:
                continue
            async with self._work.transaction(tenant):
                run = await self._runs.get(tenant, run_id)
            if not settled(run) or run is None:
                pending = pending or run is not None
                continue
            for step, value in (await self._evaluations.rule_scored(version, case, run)).items():
                if step in steps:
                    per_step.setdefault(step, []).append(value)
        scores = {step: scoring.mean(values) for step, values in sorted(per_step.items())}
        fell = scoring.regressed(baseline, scores, tolerances)
        verdict: Held = "pending" if pending or not scores else ("fell" if fell else "held")
        return Validation(
            trial=trial.id,
            process=process_id,
            model=model,
            verdict=verdict,
            scores=scores,
            baseline=baseline,
            tolerances=tolerances,
            fell=fell,
        )

    async def _baseline(
        self,
        tenant: Tenant,
        version: ProcessVersion,
        by_id: Mapping[str, EvaluationCase],
        steps: frozenset[str],
    ) -> dict[str, float | None]:
        """What the active version scored on each step of the purpose in the process's newest
        scored evaluation, by the rules a trial scores by; 1 for each where none was scored."""
        assert self._evaluations is not None  # noqa: S101 — the callers checked
        latest = await self._evaluations.latest_scored(tenant, version.process_id)
        per_step: dict[str, list[float | None]] = {}
        if latest is not None:
            for case_run in latest.runs:
                case = by_id.get(case_run.case)
                if case_run.side is not Side.ACTIVE or case is None or case_run.run_id is None:
                    continue
                async with self._work.transaction(tenant):
                    run = await self._runs.get(tenant, case_run.run_id)
                if run is None:
                    continue
                for step, value in (
                    await self._evaluations.rule_scored(version, case, run)
                ).items():
                    if step in steps:
                        per_step.setdefault(step, []).append(value)
        scored = {step: scoring.mean(values) for step, values in sorted(per_step.items())}
        return {step: scored.get(step, 1.0) for step in sorted(steps)}

    async def _trials(self, tenant: Tenant, purpose: str) -> list[Trial]:
        """The trials of the purpose, newest first."""
        async with self._work.transaction(tenant):
            started = await self._ledger.of_kinds(tenant, {STARTED})
        trials: list[Trial] = []
        for entry in started:
            if entry.content_digest is None:
                continue
            content = await self._objects.get(entry.content_digest)
            if content is None:
                continue
            trial = Trial.model_validate(json.loads(content))
            if trial.purpose == purpose:
                trials.append(trial)
        return sorted(trials, key=lambda t: (t.started_at, t.id), reverse=True)


def _steps_of(version: ProcessVersion, purpose: str) -> frozenset[str]:
    """The scored steps of the version that ask a model of the purpose."""
    scored = version.evaluation.scored_steps if version.evaluation is not None else frozenset()
    return frozenset(
        step
        for step, asked in step_purposes(version).items()
        if asked == purpose and step in scored
    )
