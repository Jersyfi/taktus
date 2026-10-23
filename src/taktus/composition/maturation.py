"""Method maturation on the instance: its handlers wired, and the loopback's `Maturation`
(ADR-0084, ADR-0086).

The run component measures every step, records a person's correction of a result, and proposes
moving a step from a language model to a trained model on evidence. Those three are
`StepMeasures`, `CorrectResultHandler` and `ProposeMovesHandler`. This module builds them once
over the instance's own stores and engine, so that `taktusctl` and the daemon hand them the
same things: the price table the instance is configured with (`TAKTUS_PRICE_TABLE`) and its
decision port. Without a price table every cost is named unpriced, and nothing is proposed.

S-06 of `blueprints/self-operation/` runs maturation on the schedule its trigger names. It asks
for the measures and the proposals through the loopback connector, which `InstanceMaturation`
answers; a weekly run measures the moves already made as well (ADR-0114). It is wiring:
nothing here decides what maturation requires.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from taktus.components.governance.domain.model import WatchConfiguration
from taktus.components.governance.domain.model.incident import shipped_watch
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.process.domain.model.evaluation import (
    Evaluation,
    EvaluationState,
    Side,
)
from taktus.components.process.domain.service import scoring
from taktus.components.run.application.query import StepMeasures
from taktus.components.run.application.service import (
    CorrectResultHandler,
    ProposeMoves,
    ProposeMovesHandler,
    ReviewMovesHandler,
    RunEngine,
)
from taktus.components.run.domain.model import Run
from taktus.components.run.domain.service.maturation import StepScore
from taktus.components.run.ports import Decisions, EvaluationScores
from taktus.ports.clock import Clock
from taktus.ports.ledger import Ledger
from taktus.ports.model import PriceTable
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.ports.worker import Limits


@dataclass(frozen=True)
class Maturation:
    """The handlers of method maturation, over one instance."""

    measures: StepMeasures
    correct: CorrectResultHandler
    propose: ProposeMovesHandler
    review: ReviewMovesHandler
    """Every move to a trained model, measured over its first cases (ADR-0114)."""


def maturation_wiring(
    *,
    engine: RunEngine,
    runs: Repository[Run],
    ledger: Ledger,
    objects: ObjectStore,
    work: UnitOfWork,
    clock: Clock,
    decisions: Decisions | None,
    prices: PriceTable | None,
    scores: EvaluationScores | None = None,
) -> Maturation:
    """`scores`: a step's score on its process's evaluation cases, as evidence (ADR-0141);
    None, where the instance keeps no evaluations."""
    measures = StepMeasures(runs, ledger, objects, work, prices)
    return Maturation(
        measures=measures,
        correct=CorrectResultHandler(runs, work, objects, ledger),
        propose=ProposeMovesHandler(
            engine, measures, objects, ledger, work, clock, decisions, prices, scores=scores
        ),
        review=ReviewMovesHandler(
            measures, objects, ledger, work, clock, decisions, prices, scores=scores
        ),
    )


class RepositoryScores:
    """The `EvaluationScores` of maturation, over the process component's versions and
    evaluations and the tenant's watch configuration (ADR-0141 §1).

    A step is scored where a scorer of its version scores it. Its score is the newest scored
    evaluation that ran the version — a drift evaluation, or the active side of a change — and
    gave the step a score (`scoring.step_score`). Nothing here names a person."""

    def __init__(
        self,
        versions: Repository[ProcessVersion],
        evaluations: Repository[Evaluation],
        watches: Repository[WatchConfiguration],
        work: UnitOfWork,
    ) -> None:
        self._versions = versions
        self._evaluations = evaluations
        self._watches = watches
        self._work = work

    async def scores(self, tenant: Tenant) -> tuple[StepScore, ...]:
        async with self._work.transaction(tenant):
            versions = list(await self._versions.list(tenant))
            evaluations = [
                e
                for e in await self._evaluations.list(tenant)
                if e.state is EvaluationState.SCORED and e.scored_at is not None
            ]
        newest_first = sorted(evaluations, key=lambda e: (e.scored_at, e.id), reverse=True)
        found: list[StepScore] = []
        for version in sorted(versions, key=lambda v: v.ref):
            declared = version.evaluation
            if declared is None:
                continue
            for step_id in sorted(declared.scored_steps):
                score = StepScore(
                    process_version=version.ref,
                    step_id=step_id,
                    scheduled=declared.schedule is not None,
                )
                for evaluation in newest_first:
                    if evaluation.version != version.ref:
                        continue
                    value = scoring.step_score(evaluation, step_id)
                    if value is None:
                        continue
                    ran = evaluation.side(Side.ACTIVE)
                    score = score.model_copy(
                        update={
                            "score": value,
                            "cases": 0 if ran is None else ran.cases,
                            "evaluation": evaluation.id,
                        }
                    )
                    break
                found.append(score)
        return tuple(found)

    async def tolerance(self, tenant: Tenant) -> float:
        async with self._work.transaction(tenant):
            found = await self._watches.get(tenant, tenant)
        return (found or shipped_watch(tenant)).evaluation_tolerance


class InstanceMaturation:
    """The `Maturation` of the loopback connector, over the run component's maturation."""

    def __init__(self, maturation: Maturation) -> None:
        self._maturation = maturation

    async def measures(self, tenant: str) -> dict[str, Any]:
        found = await self._maturation.measures.measures(tenant)
        return {
            "steps": [m.document() for m in found],
            "count": len(found),
            "unpriced": sum(1 for m in found if m.unpriced),
        }

    async def propose(
        self, tenant: str, *, identity: str, budget: dict[str, Any], scope: dict[str, Any]
    ) -> dict[str, Any]:
        """Raises `ValueError` when the budget is not limits or the scope names something
        other than a process version and a step."""
        limits = Limits.model_validate(budget)
        unknown = set(scope) - {"process_version", "step_id"}
        if unknown:
            raise ValueError(
                f"the scope names {sorted(unknown)}; it names a process version and a step"
            )
        outcomes = await self._maturation.propose.execute(
            ProposeMoves(
                tenant=tenant,
                actor=identity,
                budget=limits,
                process_version=_text(scope, "process_version"),
                step_id=_text(scope, "step_id"),
            )
        )
        # The moves already made are measured on the same schedule (ADR-0114 §6).
        moves = await self._maturation.review.execute(tenant)
        return {
            "outcomes": [o.document() for o in outcomes],
            "looked_at": len(outcomes),
            "proposed": sum(1 for o in outcomes if o.proposed),
            "applied": sum(1 for o in outcomes if o.applied),
            "moves": [m.document() for m in moves],
        }


def _text(scope: dict[str, Any], name: str) -> str | None:
    value = scope.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"`scope.{name}` is a text")
    return value
