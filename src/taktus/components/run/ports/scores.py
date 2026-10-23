"""A step's score on its process's evaluation cases, seen from maturation (ADR-0141).

The process component owns the evaluation cases and their scores (ADR-0134). Maturation reads
a step's score as evidence: what a move is proposed beside and measured against afterwards.
The composition root answers from the process component, because components never import each
other.
"""

from __future__ import annotations

from typing import Protocol

from taktus.components.run.domain.service.maturation import StepScore
from taktus.ports.persistence import Tenant


class EvaluationScores(Protocol):
    async def scores(self, tenant: Tenant) -> tuple[StepScore, ...]:
        """Every step a scorer of its version scores, with the score of the newest evaluation
        that ran the version and scored it; a score of None where none did yet."""
        ...

    async def tolerance(self, tenant: Tenant) -> float:
        """How far a score may fall before it is a regression: the tenant's tolerance."""
        ...
