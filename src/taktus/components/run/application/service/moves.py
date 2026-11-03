"""Use case: a step moved to a trained model is measured over its first cases, and a move that
did not make it cheaper is proposed for rolling back (ADR-0114, issue #218, DEC-0164
provisionally Option A).

A move is the ledger entry `method.moved`: a new process version, registered on a person's
acceptance of a proposal, in which the step runs on the trained model. This handler reads every
move of the tenant and measures it by a rule (`domain.service.maturation.review`):

- the first 100 cases of the step on the new version, in the order they started: their cost per
  case at the price table, and the share that fell back to the language model;
- the cases of the step on the version it replaced: their cost per case at the same table;
- where the process's evaluation cases score the step, its score in each version (ADR-0141).

Until 100 cases ran, the move is `measuring`, and nothing is recorded; so it is while the
replaced version was scored on the cases and the moved version, whose cases run on a schedule,
was not yet. Then the verdict is recorded once, as `method.measured`, with the measures by
digest: `worse` where the score fell by more than the tenant's tolerance, else `cheaper`,
`not_cheaper`, or `unpriced` where a cost cannot be priced. A move that is `worse` or
`not_cheaper` is proposed for rolling back, as a decision request to whoever owns the
process. Nothing is rolled back here: a person decides, and the composition root applies the
decision (`composition/moves.py`).
"""

from __future__ import annotations

import json
from datetime import timedelta

from taktus.components.run.application.query.measures import StepCases, StepMeasures
from taktus.components.run.domain.service import maturation
from taktus.components.run.domain.service.maturation import Move, MoveReview, StepScore
from taktus.components.run.ports import (
    Decisions,
    Draft,
    DraftOption,
    EvaluationScores,
    NotRaised,
)
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.model import PriceTable
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Tenant, UnitOfWork
from taktus.shared.v1 import DecisionClass, LedgerRefs, Method


class MoveError(Exception):
    """A move or a rollback that cannot be made. `kind` says why: `unknown` — no such proposal,
    process or move; `undecided` — no answer took effect yet; `declined` — the answer took
    another option; `modified` — the answer modified the proposal; `stale` — the process is no
    longer at the version the proposal was made on; `refused` — registration refused the
    version, with its findings."""

    def __init__(self, kind: str, detail: str) -> None:
        self.kind = kind
        super().__init__(detail)


DECIDER = "owner"
"""Whoever owns the process, until a process names its owner (UC-15.5)."""


class ReviewMovesHandler:
    def __init__(
        self,
        cases: StepMeasures,
        objects: ObjectStore,
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
        decisions: Decisions | None,
        prices: PriceTable | None,
        decision_days: int = 3,
        scores: EvaluationScores | None = None,
    ) -> None:
        """`scores` reads a step's score on its process's evaluation cases (ADR-0141); None:
        a move is measured by its cost alone."""
        self._scores = scores
        self._cases = cases
        self._objects = objects
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._decisions = decisions
        self._prices = prices
        self._decision_days = decision_days

    async def execute(self, tenant: Tenant) -> tuple[MoveReview, ...]:
        """Every move of the tenant, measured; in the order the moves were made."""
        async with self._work.transaction(tenant):
            entries = await self._ledger.of_kinds(tenant, (maturation.MOVED, maturation.MEASURED))
        moves: list[Move] = []
        measured: dict[str, MoveReview] = {}
        for entry in entries:
            if entry.content_digest is None:
                continue
            content = await self._objects.get(entry.content_digest)
            if content is None:
                continue
            if entry.kind == maturation.MOVED:
                moves.append(Move.model_validate(json.loads(content)))
            else:
                done = MoveReview.model_validate(json.loads(content))
                measured[done.move.process_version] = done
        if not moves:
            return ()
        steps = {(s.process_version, s.step_id): s for s in await self._cases.steps(tenant)}
        currency = None if self._prices is None else self._prices.currency
        scored: dict[tuple[str, str], StepScore] = {}
        tolerance = 0.0
        if self._scores is not None:
            scored = {(s.process_version, s.step_id): s for s in await self._scores.scores(tenant)}
            tolerance = await self._scores.tolerance(tenant)
        found: list[MoveReview] = []
        for move in moves:
            recorded = measured.get(move.process_version)
            if recorded is not None:
                found.append(recorded)
                continue
            now = steps.get((move.process_version, move.step_id))
            before = steps.get((move.replaced, move.step_id))
            review = maturation.review(
                move,
                _cases(now),
                _cases(before),
                currency,
                (
                    scored.get((move.process_version, move.step_id)),
                    scored.get((move.replaced, move.step_id)),
                ),
                tolerance,
            )
            if review.verdict == "measuring":
                found.append(review)
                continue
            if review.verdict in ("worse", "not_cheaper") and now is not None:
                review = await self._propose_rollback(tenant, review, now)
            await self._record(tenant, review)
            found.append(review)
        return tuple(found)

    async def _propose_rollback(
        self, tenant: Tenant, review: MoveReview, now: StepCases
    ) -> MoveReview:
        """The proposal to roll a move back that did not make the step cheaper, raised to
        whoever owns the process. Raised again, the same request is met."""
        if self._decisions is None:
            return review
        request_id = review.rollback_request_id(tenant)
        try:
            await self._decisions.raise_request(
                tenant,
                Draft(
                    id=request_id,
                    run=now.cases[0].run_id,
                    step=review.move.step_id,
                    class_=str(DecisionClass.CONCEPTUAL),
                    situation=review.situation(),
                    question=review.question(),
                    options=tuple(
                        DraftOption(
                            id=o["id"],
                            proposal=o["proposal"],
                            consequence=o["consequence"],
                            recommended=o["recommended"],
                            reason=o.get("reason"),
                        )
                        for o in review.options()
                    ),
                    blocking=(),
                    due=self._clock.now().date() + timedelta(days=self._decision_days),
                    decider=DECIDER,
                ),
            )
        except NotRaised:
            return review
        return review.model_copy(update={"rollback_request": request_id})

    async def _record(self, tenant: Tenant, review: MoveReview) -> None:
        """The verdict, once, with the measures by digest. No actor: Taktus measured on its
        own."""
        content = json.dumps(review.document(), ensure_ascii=False, sort_keys=True)
        digest = await self._objects.put(content.encode("utf-8"))
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=maturation.MEASURED,
                    refs=LedgerRefs(
                        tenant=tenant,
                        process_version=review.move.process_version,
                        step_id=review.move.step_id,
                        decision_request_id=review.rollback_request,
                    ),
                    method=Method.ML,
                    outcome=review.verdict,
                    content_digest=digest,
                ),
            )


def _cases(step: StepCases | None) -> tuple[maturation.Case, ...]:
    return () if step is None else step.cases
