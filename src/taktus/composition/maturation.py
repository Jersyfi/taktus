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
answers. It is wiring: nothing here decides what maturation requires.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from taktus.components.run.application.query import StepMeasures
from taktus.components.run.application.service import (
    CorrectResultHandler,
    ProposeMoves,
    ProposeMovesHandler,
    RunEngine,
)
from taktus.components.run.domain.model import Run
from taktus.components.run.ports import Decisions
from taktus.ports.clock import Clock
from taktus.ports.ledger import Ledger
from taktus.ports.model import PriceTable
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Repository, UnitOfWork
from taktus.ports.worker import Limits


@dataclass(frozen=True)
class Maturation:
    """The three handlers of method maturation, over one instance."""

    measures: StepMeasures
    correct: CorrectResultHandler
    propose: ProposeMovesHandler


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
) -> Maturation:
    measures = StepMeasures(runs, ledger, objects, work, prices)
    return Maturation(
        measures=measures,
        correct=CorrectResultHandler(runs, work, objects, ledger),
        propose=ProposeMovesHandler(
            engine, measures, objects, ledger, work, clock, decisions, prices
        ),
    )


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
        return {
            "outcomes": [o.document() for o in outcomes],
            "looked_at": len(outcomes),
            "proposed": sum(1 for o in outcomes if o.proposed),
        }


def _text(scope: dict[str, Any], name: str) -> str | None:
    value = scope.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"`scope.{name}` is a text")
    return value
