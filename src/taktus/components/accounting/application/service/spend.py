"""Where a process spends: per step, for one run, over a window, and two runs side by side.

Issue #449, DEC-0200 answer 3. A person sees from the records where a process spends — money,
tokens by price kind, turns, and what a compression saved — per step. Everything is read from
the ledger's `step.finished` entries and priced at each run's own price table, the table its
budget statement names (`cost_of_run`), never at today's. What cannot be priced is named, never
counted as free (ADR-0005, ADR-0010).

Two runs of the same task — with and without a change such as a compression or another model —
are compared step by step: each side's figures and each step's outcome and result digest, so
that a change is adopted only when it is shown to be better. No figure here names a person
(principle 14): a run, a step and a process are what is measured.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import Field

from taktus.components.accounting.application.service.cost_of_run import CostOfRunHandler
from taktus.components.accounting.domain.service import Meter, combine, weigh
from taktus.components.accounting.domain.service.metering import meter_by_step
from taktus.ports.ledger import Ledger
from taktus.ports.model import PriceTable, WeightingTable, price, price_compute
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Tenant, UnitOfWork
from taktus.shared.v1 import LedgerEntry, Value


class StepSpend(Value):
    """What one step used, and its money at the run's table."""

    step_id: str
    method: str | None = None
    finished: int
    """How often the step finished: a step that ran again is counted each time."""
    meter: Meter
    amount: float | None = None
    """Money at the run's price table; None when there is none."""
    unpriced: tuple[str, ...] = ()
    takte: float | None = None
    """Its Takte at the run's weighting table; None when the run started without one."""
    outcome: str | None = None
    """The outcome of its last finish."""
    result: str | None = None
    """The digest of its last finish's result, where it recorded one."""


class RunSpend(Value):
    run_id: str
    process_version: str | None = None
    currency: str | None = None
    table: str | None = None
    """The price table's version the money is computed at."""
    steps: tuple[StepSpend, ...] = ()
    amount: float | None = None
    """The steps' money together; None when no step could be priced."""
    unpriced: tuple[str, ...] = ()
    takte: float | None = None
    """The steps' Takte together, at the run's weighting table; None without one."""
    calibration: str | None = None
    """`calibrated` or `uncalibrated`: the word beside every Takt figure (DEC-0132)."""


class StepDifference(Value):
    """One step of two runs: right less left, where both have the figure."""

    step_id: str
    amount: float | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    turns: int | None = None
    same_result: bool | None = None
    """True when both recorded the same result digest; None when either recorded none."""


class RunComparison(Value):
    left: RunSpend
    right: RunSpend
    steps: tuple[StepDifference, ...] = ()
    amount: float | None = None
    """Right less left, when both are priced in one currency."""
    comparable: tuple[str, ...] = ()
    """Why the figures may not compare, where they may not: another process, another table."""


class ProcessSpend(Value):
    """A process's spend over a window, per step: each run's money summed per currency."""

    process_id: str
    since: datetime | None = None
    until: datetime | None = None
    runs: int
    steps: tuple[StepSpend, ...] = ()
    amounts: dict[str, float] = Field(default_factory=dict)
    unpriced: tuple[str, ...] = ()


@dataclass(frozen=True)
class SpendOfRun:
    run_id: str
    tenant: Tenant
    table: PriceTable | None = None
    """A table to price at instead of the run's own: to compare, never to rewrite."""


@dataclass(frozen=True)
class CompareRuns:
    left: str
    right: str
    tenant: Tenant


@dataclass(frozen=True)
class SpendOfProcess:
    process_id: str
    tenant: Tenant
    since: datetime | None = None
    until: datetime | None = None


def tokens_in(used: Meter) -> int:
    return sum(kinds.tokens_in for kinds in used.tokens.values())


def tokens_out(used: Meter) -> int:
    return sum(kinds.output or 0 for kinds in used.tokens.values())


class SpendHandler:
    """The three questions of #449, from one reading of the ledger each."""

    def __init__(self, ledger: Ledger, objects: ObjectStore, work: UnitOfWork) -> None:
        self._ledger = ledger
        self._work = work
        self._cost = CostOfRunHandler(ledger, objects, work)

    async def of_run(self, query: SpendOfRun) -> RunSpend:
        async with self._work.transaction(query.tenant):
            entries = list(await self._ledger.entries(query.tenant, query.run_id))
        return await self._spend(query.run_id, entries, query.table)

    async def compare(self, query: CompareRuns) -> RunComparison:
        left = await self.of_run(SpendOfRun(query.left, query.tenant))
        right = await self.of_run(SpendOfRun(query.right, query.tenant))
        caveats: list[str] = []
        if _process(left.process_version) != _process(right.process_version):
            caveats.append(
                f"the runs are of different processes: {left.process_version} and "
                f"{right.process_version}"
            )
        if left.table != right.table:
            caveats.append(f"priced at different tables: {left.table} and {right.table}")
        before = {s.step_id: s for s in left.steps}
        after = {s.step_id: s for s in right.steps}
        order = [*before, *(s for s in after if s not in before)]
        differences = tuple(_difference(step, before.get(step), after.get(step)) for step in order)
        amount = None
        if left.amount is not None and right.amount is not None and left.currency == right.currency:
            amount = round(right.amount - left.amount, 9)
        return RunComparison(
            left=left, right=right, steps=differences, amount=amount, comparable=tuple(caveats)
        )

    async def of_process(self, query: SpendOfProcess) -> ProcessSpend:
        async with self._work.transaction(query.tenant):
            finished = await self._ledger.of_kinds(query.tenant, {"step.finished"})
        by_run: dict[str, list[LedgerEntry]] = {}
        for entry in finished:
            if _process(entry.refs.process_version) != query.process_id:
                continue
            if query.since is not None and entry.ts < query.since:
                continue
            if query.until is not None and entry.ts >= query.until:
                continue
            if entry.refs.run_id is not None:
                by_run.setdefault(entry.refs.run_id, []).append(entry)
        meters: dict[str, Meter] = {}
        counts: dict[str, int] = {}
        methods: dict[str, str | None] = {}
        amounts: dict[str, dict[str, float]] = {}
        totals: dict[str, float] = {}
        takte: dict[str, float] = {}
        unpriced: set[str] = set()
        for run_id, entries in by_run.items():
            # The run's own table: its budget statement is among its entries, not among these.
            async with self._work.transaction(query.tenant):
                whole = list(await self._ledger.entries(query.tenant, run_id))
            spent = await self._spend(run_id, whole, None, only=entries)
            unpriced.update(spent.unpriced)
            for step in spent.steps:
                held = meters.get(step.step_id)
                meters[step.step_id] = step.meter if held is None else combine(held, step.meter)
                counts[step.step_id] = counts.get(step.step_id, 0) + step.finished
                methods.setdefault(step.step_id, step.method)
                if step.takte is not None:
                    takte[step.step_id] = takte.get(step.step_id, 0.0) + step.takte
                if step.amount is not None and spent.currency is not None:
                    per = amounts.setdefault(step.step_id, {})
                    per[spent.currency] = per.get(spent.currency, 0.0) + step.amount
                    totals[spent.currency] = totals.get(spent.currency, 0.0) + step.amount
        steps = tuple(
            StepSpend(
                step_id=step,
                method=methods.get(step),
                finished=counts[step],
                meter=used,
                amount=_single(amounts.get(step)),
                unpriced=_currencies(amounts.get(step)),
                takte=None if step not in takte else round(takte[step], 9),
            )
            for step, used in meters.items()
        )
        return ProcessSpend(
            process_id=query.process_id,
            since=query.since,
            until=query.until,
            runs=len(by_run),
            steps=steps,
            amounts={c: round(a, 9) for c, a in totals.items()},
            unpriced=tuple(sorted(unpriced)),
        )

    async def _spend(
        self,
        run_id: str,
        entries: Sequence[LedgerEntry],
        table: PriceTable | None,
        *,
        only: Sequence[LedgerEntry] | None = None,
    ) -> RunSpend:
        version = next(
            (e.refs.process_version for e in entries if e.refs.process_version is not None), None
        )
        statement = await self._cost._statement_of(list(entries))
        if table is None:
            table, _ = await self._cost._table_of(statement)
        weights, classes = await self._weights_of(statement)
        counted = list(only if only is not None else entries)
        per_step = meter_by_step(counted)
        last = {e.refs.step_id: e for e in counted if e.kind == "step.finished"}
        steps: list[StepSpend] = []
        total = 0.0
        priced_any = False
        missing: set[str] = set()
        for step_id, used in per_step.items():
            amount, why = _priced(used, table)
            missing.update(why)
            if amount is not None:
                total += amount
                priced_any = True
            finish = last.get(step_id)
            takte = None if weights is None else weigh(used, weights, classes).takte
            steps.append(
                StepSpend(
                    step_id=step_id,
                    method=None if finish is None or finish.method is None else str(finish.method),
                    finished=sum(used.steps.values()),
                    meter=used,
                    amount=amount,
                    unpriced=why,
                    takte=takte,
                    outcome=None if finish is None else finish.outcome,
                    result=None
                    if finish is None or finish.content_digest is None
                    else str(finish.content_digest),
                )
            )
        if table is None and any(s.meter.tokens or s.meter.compute_seconds for s in steps):
            missing.add("the run was held without a price table")
        return RunSpend(
            run_id=run_id,
            process_version=version,
            currency=None if table is None else table.currency,
            table=None if table is None else table.version,
            steps=tuple(steps),
            amount=round(total, 9) if priced_any else None,
            unpriced=tuple(sorted(missing)),
            takte=None if weights is None else round(sum(s.takte or 0.0 for s in steps), 9),
            calibration=None
            if weights is None
            else ("calibrated" if weights.calibrated else "uncalibrated"),
        )

    async def _weights_of(
        self, statement: Mapping[str, Any]
    ) -> tuple[WeightingTable | None, Mapping[str, str]]:
        """The weighting table the run's statement names, and the model classes recorded beside
        it; None where the run started without one, or it cannot be read."""
        reference = statement.get("weighting_table") or {}
        if not reference:
            return None, {}
        document = await self._cost._objects.get(reference["digest"])
        if document is None:
            return None, {}
        table = WeightingTable.model_validate(json.loads(document))
        return table, dict(reference.get("model_classes") or {})


def _priced(used: Meter, table: PriceTable | None) -> tuple[float | None, tuple[str, ...]]:
    if table is None:
        return None, ()
    why: list[str] = []
    if used.tokens_unattributed:
        why.append(f"{used.tokens_unattributed} token(s) recorded without the model")
    tokens = price(used.tokens, table)
    compute = price_compute(used.compute_seconds, table)
    why.extend(f"no price for {kind}" for kind in (*tokens.unpriced, *compute.unpriced))
    return round(tokens.amount + compute.amount, 9), tuple(why)


def _process(version: str | None) -> str | None:
    return None if version is None else version.partition("@")[0]


def _single(amounts: dict[str, float] | None) -> float | None:
    if not amounts or len(amounts) != 1:
        return None
    return round(next(iter(amounts.values())), 9)


def _currencies(amounts: dict[str, float] | None) -> tuple[str, ...]:
    if amounts and len(amounts) > 1:
        return (f"priced in several currencies: {', '.join(sorted(amounts))}",)
    return ()


def _difference(step: str, left: StepSpend | None, right: StepSpend | None) -> StepDifference:
    if left is None or right is None:
        return StepDifference(step_id=step)
    amount = None
    if left.amount is not None and right.amount is not None:
        amount = round(right.amount - left.amount, 9)
    same = None
    if left.result is not None and right.result is not None:
        same = left.result == right.result
    return StepDifference(
        step_id=step,
        amount=amount,
        tokens_in=tokens_in(right.meter) - tokens_in(left.meter),
        tokens_out=tokens_out(right.meter) - tokens_out(left.meter),
        turns=right.meter.turns - left.meter.turns,
        same_result=same,
    )


__all__ = [
    "CompareRuns",
    "ProcessSpend",
    "RunComparison",
    "RunSpend",
    "SpendHandler",
    "SpendOfProcess",
    "SpendOfRun",
    "StepDifference",
    "StepSpend",
]
