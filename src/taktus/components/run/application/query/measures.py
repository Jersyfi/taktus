"""A step's cases and measures, read from what Taktus recorded (ADR-0084, issue #217).

Every run of the tenant that is not a rehearsal is read, and every step run in it that
succeeded with a result is one case of its step. A step is its process version and its
identifier: a new version of a process starts new cases, because its step may have changed.

What a case is read from, and nothing else:

- the run and its step runs: what the step consumed, when it started and ended, its result;
- the object store: the result's content, and what the step read through `$from`;
- the ledger: a person's correction of the result (`step.corrected`), the newest one counting.
  Who corrected is in the entry; it never reaches a case or a measure (principle 14).

Money is the step's tokens and compute seconds at the price table the handler is given, one
table for every case, so that two methods are compared at the same prices. A case that cannot be
priced is named, never counted as free.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from taktus.components.run.domain.model import Run, StepRun, StepState
from taktus.components.run.domain.model.work import resolve, resolve_inputs
from taktus.components.run.domain.service import maturation
from taktus.components.run.domain.service.maturation import Case, Measures
from taktus.ports.ledger import Ledger
from taktus.ports.model import PriceTable, price, price_compute
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Consumption, Method, Value


class StepCases(Value):
    """One step's cases, as maturation reads them."""

    process_version: str
    step_id: str
    method: Method
    exactness: str | None = None
    cases: tuple[Case, ...] = ()


class StepMeasures:
    """The cases and the measures of every step of the tenant."""

    def __init__(
        self,
        runs: Repository[Run],
        ledger: Ledger,
        objects: ObjectStore,
        work: UnitOfWork,
        prices: PriceTable | None = None,
    ) -> None:
        self._runs = runs
        self._ledger = ledger
        self._objects = objects
        self._work = work
        self._prices = prices

    async def measures(self, tenant: Tenant) -> tuple[Measures, ...]:
        """Every step's measures, ordered by process version and step."""
        currency = None if self._prices is None else self._prices.currency
        return tuple(
            maturation.measure(s.process_version, s.step_id, s.method, s.cases, currency)
            for s in await self.steps(tenant)
        )

    async def steps(self, tenant: Tenant) -> tuple[StepCases, ...]:
        """Every step with its cases, ordered by process version and step; each step's cases
        ordered by run."""
        async with self._work.transaction(tenant):
            runs = list(await self._runs.list(tenant))
            entries = list(await self._ledger.entries(tenant))
        corrections: dict[tuple[str, str], str] = {}
        for entry in entries:
            refs = entry.refs
            if (
                entry.kind == maturation.CORRECTED
                and refs.run_id is not None
                and refs.step_id is not None
                and entry.content_digest is not None
            ):
                corrections[(refs.run_id, refs.step_id)] = entry.content_digest  # newest wins
        found: dict[tuple[str, str], StepCases] = {}
        for run in sorted(runs, key=lambda r: r.id):
            if run.rehearsal:
                continue
            for step_run in run.step_runs:
                case = await self._case(run, step_run, corrections)
                if case is None:
                    continue
                step = run.step(step_run.step_id)
                key = (run.process_version, step.id)
                held = found.get(key) or StepCases(
                    process_version=run.process_version,
                    step_id=step.id,
                    method=step.method,
                    exactness=None if step.exactness is None else str(step.exactness),
                )
                found[key] = held.model_copy(update={"cases": (*held.cases, case)})
        return tuple(found[key] for key in sorted(found))

    async def _case(
        self, run: Run, step_run: StepRun, corrections: Mapping[tuple[str, str], str]
    ) -> Case | None:
        checkpoint = step_run.checkpoint
        if (
            step_run.state is not StepState.SUCCEEDED
            or checkpoint is None
            or checkpoint.result_digest is None
        ):
            return None
        step = run.step(step_run.step_id)
        result = checkpoint.result_digest
        features: dict[str, float] = {}
        left_out: tuple[str, ...] = ()
        if step.method is Method.LLM:
            content = await self._objects.get(checkpoint.result_digest)
            produced = None if content is None else json.loads(content)
            if not isinstance(produced, Mapping) or not isinstance(produced.get("text"), str):
                return None
            result = produced["text"].strip()
            features, left_out = await self._read(run, step_run.step_id)
        label = result
        corrected = corrections.get((run.id, step_run.step_id))
        if corrected is not None:
            content = await self._objects.get(corrected)
            if content is not None:
                label = _label(json.loads(content))
        cost, unpriced = self._cost(step_run.consumption)
        seconds = (
            None
            if step_run.started_at is None or step_run.finished_at is None
            else max(0.0, (step_run.finished_at - step_run.started_at).total_seconds())
        )
        return Case(
            run_id=run.id,
            features=features,
            left_out=left_out,
            result=result,
            label=label,
            corrected=corrected is not None,
            cost=cost,
            unpriced=unpriced,
            seconds=seconds,
        )

    async def _read(self, run: Run, step_id: str) -> tuple[dict[str, float], tuple[str, ...]]:
        """The values an `llm` step's prompt was rendered from, resolved as the run resolved
        them: its inputs, and the results of the steps it referenced. A value that cannot be
        read back — an artifact's content, a result no longer stored — is left out."""
        work = run.work.get(step_id) or {}
        values: Any = work.get("values") or {}
        try:
            values = resolve_inputs(values, run.inputs)
            results: dict[str, Any] = {}
            for other in run.step_runs:
                checkpoint = other.checkpoint
                if other.done and checkpoint is not None and checkpoint.result_digest is not None:
                    content = await self._objects.get(checkpoint.result_digest)
                    if content is not None:
                        results[other.step_id] = json.loads(content)
            values = resolve(values, results, {})
        except (KeyError, TypeError, ValueError):
            return {}, ("values",)
        return maturation.numbers(values)

    def _cost(self, used: Consumption | None) -> tuple[float | None, tuple[str, ...]]:
        """The money a step's consumption costs at the price table, or what keeps it from being
        priced. Tokens are priced per model and kind, compute seconds per resource class; quota
        units have no price. Money a worker reported itself is not counted: it is the worker's
        figure, not the table's."""
        if used is None:
            return 0.0, ()
        if self._prices is None:
            return None, ("no price table is configured",)
        unpriced: list[str] = []
        amount = 0.0
        if used.tokens_by_model:
            priced = price(used.tokens_by_model, self._prices)
            amount += priced.amount
            unpriced.extend(f"no price for {kind}" for kind in priced.unpriced)
        elif used.tokens_in or used.tokens_out:
            unpriced.append("tokens recorded without the model that used them")
        if used.compute_seconds and used.resource_class is not None:
            priced = price_compute({used.resource_class: used.compute_seconds}, self._prices)
            amount += priced.amount
            unpriced.extend(f"no price for {kind}" for kind in priced.unpriced)
        if used.quota_units:
            unpriced.append("quota units have no price")
        return (None, tuple(unpriced)) if unpriced else (amount, ())


def _label(value: Any) -> str:
    """A corrected result as a label: its text, or its JSON where it is not text."""
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
