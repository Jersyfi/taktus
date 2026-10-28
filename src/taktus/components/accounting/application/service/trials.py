"""A model trial's report: each candidate's runs of the same cases, set side by side (#448).

ADR-0149, DEC-0200 answer 2. Before a model is introduced for a purpose, proposed by Taktus or
changed, the same fixed cases run once with each candidate. This module reads those runs back
from the ledger and reports per candidate: the cases passed, the money at each run's own price
table, the tokens in and out, the wall time, and each case's result beside the others'. It
decides nothing: choosing a model stays a person's act (M3.12, M3.14).

A case passes when its run finished and every step that finished succeeded, unless the caller
hands a verdict per case — the score of the case's evaluation (ADR-0134) — which then decides.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from pydantic import Field

from taktus.components.accounting.application.service.spend import (
    RunSpend,
    SpendHandler,
    SpendOfRun,
    tokens_in,
    tokens_out,
)
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Tenant, UnitOfWork
from taktus.shared.v1 import Value

ENDED = {"run.finished": "finished", "run.escalated": "escalated", "run.halted": "halted"}


class CaseOutcome(Value):
    case: str
    run_id: str
    state: str | None = None
    """How the run ended: finished, escalated or halted; None while it runs."""
    passed: bool
    amount: float | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    wall_seconds: float | None = None
    """From the run's first entry to its last."""
    results: dict[str, str] = Field(default_factory=dict)
    """The digest of each step's last result, by step."""


class CandidateReport(Value):
    model: str
    cases: tuple[CaseOutcome, ...] = ()
    passed: int = 0
    amount: float | None = None
    currency: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    wall_seconds: float = 0.0
    unpriced: tuple[str, ...] = ()


class TrialReport(Value):
    purpose: str
    candidates: tuple[CandidateReport, ...] = ()
    differing: tuple[str, ...] = ()
    """The cases whose results are not the same for every candidate that ran them."""


@dataclass(frozen=True)
class ReportTrial:
    purpose: str
    tenant: Tenant
    runs: Mapping[str, Mapping[str, str]]
    """Per candidate model, its run of each case: `{model: {case: run_id}}`."""
    verdicts: Mapping[str, Mapping[str, bool]] = field(default_factory=dict)
    """Per candidate model, a verdict per case that replaces the run's own ending."""


class TrialReports:
    def __init__(self, ledger: Ledger, spend: SpendHandler, work: UnitOfWork) -> None:
        self._ledger = ledger
        self._spend = spend
        self._work = work

    async def execute(self, query: ReportTrial) -> TrialReport:
        candidates: list[CandidateReport] = []
        for model, cases in query.runs.items():
            outcomes = [
                await self._case(query.tenant, case, run_id, query.verdicts.get(model, {}))
                for case, run_id in sorted(cases.items())
            ]
            candidates.append(_candidate(model, outcomes, await self._sample(query, cases)))
        return TrialReport(
            purpose=query.purpose, candidates=tuple(candidates), differing=_differing(candidates)
        )

    async def _sample(self, query: ReportTrial, cases: Mapping[str, str]) -> RunSpend | None:
        first = next(iter(cases.values()), None)
        return None if first is None else await self._spend.of_run(SpendOfRun(first, query.tenant))

    async def _case(
        self, tenant: Tenant, case: str, run_id: str, verdicts: Mapping[str, bool]
    ) -> CaseOutcome:
        async with self._work.transaction(tenant):
            entries = list(await self._ledger.entries(tenant, run_id))
        spend = await self._spend.of_run(SpendOfRun(run_id, tenant))
        ended = next((ENDED[e.kind] for e in reversed(entries) if e.kind in ENDED), None)
        steps_ok = all(s.outcome in (None, "succeeded") for s in spend.steps)
        passed = verdicts.get(case, ended == "finished" and steps_ok)
        wall = None
        if entries:
            wall = (entries[-1].ts - entries[0].ts).total_seconds()
        return CaseOutcome(
            case=case,
            run_id=run_id,
            state=ended,
            passed=passed,
            amount=spend.amount,
            tokens_in=sum(tokens_in(s.meter) for s in spend.steps),
            tokens_out=sum(tokens_out(s.meter) for s in spend.steps),
            wall_seconds=wall,
            results={s.step_id: s.result for s in spend.steps if s.result is not None},
        )


def _candidate(
    model: str, outcomes: Sequence[CaseOutcome], sample: RunSpend | None
) -> CandidateReport:
    priced = [o.amount for o in outcomes if o.amount is not None]
    unpriced = tuple(o.case for o in outcomes if o.amount is None)
    return CandidateReport(
        model=model,
        cases=tuple(outcomes),
        passed=sum(1 for o in outcomes if o.passed),
        amount=round(sum(priced), 9) if priced else None,
        currency=None if sample is None else sample.currency,
        tokens_in=sum(o.tokens_in for o in outcomes),
        tokens_out=sum(o.tokens_out for o in outcomes),
        wall_seconds=round(sum(o.wall_seconds or 0.0 for o in outcomes), 3),
        unpriced=tuple(f"case {case} has no price" for case in unpriced),
    )


def _differing(candidates: Sequence[CandidateReport]) -> tuple[str, ...]:
    by_case: dict[str, list[dict[str, str]]] = {}
    for candidate in candidates:
        for outcome in candidate.cases:
            by_case.setdefault(outcome.case, []).append(outcome.results)
    return tuple(
        sorted(case for case, results in by_case.items() if any(r != results[0] for r in results))
    )
