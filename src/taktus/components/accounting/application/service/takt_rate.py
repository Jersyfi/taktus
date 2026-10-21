"""The Takt rate of a tenant: Takte per hour over the window of the table in force (ADR-0010).

What every step of the tenant finished inside the window used, each run's steps weighed at the
weighting table its budget statement names — the table in force when that run started — with
the model classes recorded beside it, summed, and divided by the window's hours. The window is
the table in force's `rate_window_days`: thirty days for version 0 (DEC-0131). A run that
started without a weighting table, or whose table cannot be read, is named, and so is every
quantity a table does not weigh; nothing is counted as zero (UC-8.5).

The read costs what it returns (ADR-0105 §9): the `step.finished` entries recorded inside the
window, read by kind and time, and the `budget.set` entries of the runs they belong to.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Literal

from taktus.components.accounting.domain.service import (
    TAKT,
    Meter,
    calibration,
    combine,
    meter,
    weigh,
)
from taktus.components.accounting.domain.service.takt_window import RETAIN_DAYS
from taktus.ports.clock import Clock
from taktus.ports.ledger import Ledger
from taktus.ports.model import WeightingTable
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Tenant, UnitOfWork
from taktus.shared.v1 import LedgerEntry, Value


class TaktRate(Value):
    """A tenant's Takt consumption over the window, and the rate it makes."""

    tenant: str
    window_days: int
    since: datetime
    until: datetime
    takte: float
    """The Takte of every step finished inside the window, each at its run's table."""
    per_hour: float
    runs: int
    """How many runs had a step finish inside the window."""
    tables: tuple[str, ...] = ()
    """Each table the Takte were computed at, as `<version> (<calibration>)`."""
    calibrated: bool
    """True only when every table the Takte were computed at is calibrated."""
    calibration: Literal["calibrated", "uncalibrated"]
    """The word beside every figure."""
    unweighed: tuple[str, ...] = ()
    """What the Takte leave out, and why, per run."""


FINISHED = "step.finished"
BUDGET = "budget.set"


@dataclass(frozen=True)
class TaktRateOf:
    tenant: Tenant


class TaktRateHandler:
    def __init__(
        self,
        ledger: Ledger,
        objects: ObjectStore,
        work: UnitOfWork,
        clock: Clock,
        weights: WeightingTable,
    ) -> None:
        self._ledger = ledger
        self._objects = objects
        self._work = work
        self._clock = clock
        self._weights = weights

    async def execute(self, query: TaktRateOf) -> TaktRate:
        until = self._clock.now()
        days = self._weights.rate_window_days
        since = until - timedelta(days=days)
        async with self._work.transaction(query.tenant):
            used, budgets = await self._used(query.tenant, since, until, days)
        references: dict[str | None, dict[str, Any]] = {}
        for digest in set(budgets.values()):
            references[digest] = await self._reference(digest)
        takte, runs = 0.0, 0
        tables: set[tuple[str, bool]] = set()
        unweighed: list[str] = []
        for run_id, inside in sorted(used.items()):
            runs += 1
            reference = references[budgets[run_id]]
            table = await self._table(reference)
            if table is None:
                why = (
                    "started without a weighting table in force"
                    if not reference
                    else f"its weighting table {reference['version']} cannot be read"
                )
                unweighed.append(f"run {run_id}: {why}")
                continue
            takt = weigh(inside, table, reference.get("model_classes") or {})
            takte += takt.takte
            tables.add((table.version, table.calibrated))
            unweighed.extend(f"run {run_id}: {item}" for item in takt.unweighed)
        takte = round(takte, 9)
        every = bool(tables) and all(calibrated for _, calibrated in tables)
        return TaktRate(
            tenant=query.tenant,
            window_days=days,
            since=since,
            until=until,
            takte=takte,
            per_hour=takte / (days * 24),
            runs=runs,
            tables=tuple(
                f"{version} ({calibration(calibrated)})" for version, calibrated in sorted(tables)
            ),
            calibrated=every,
            calibration=calibration(every),
            unweighed=tuple(unweighed),
        )

    async def _used(
        self, tenant: Tenant, since: datetime, until: datetime, days: int
    ) -> tuple[dict[str, Meter], dict[str, str | None]]:
        """What each run's steps finished inside the window used, and the digest of the budget
        statement each run names. The whole days of the window come from the projection, the
        partial days at its ends from the entries; a window longer than the projection keeps is
        read from the entries (`takt_window.RETAIN_DAYS`)."""
        midnight = datetime.combine(since.date(), time.min, since.tzinfo)
        first = since.date() if since == midnight else since.date() + timedelta(days=1)
        last = until.date() - timedelta(days=1)
        used: dict[str, Meter] = {}
        known: dict[str, str | None] = {}
        state = None
        edges: list[tuple[datetime, datetime]]
        if days + 2 <= RETAIN_DAYS and first <= last:
            state = await self._ledger.project(tenant, TAKT)
            if state.newest and first < date.fromisoformat(state.newest) - timedelta(RETAIN_DAYS):
                state = None  # the ledger runs ahead of the clock: the days are not kept
        if state is not None:
            used = state.of_days(first, last)
            known = {run: held[0] for run, held in state.budgets.items()}
            before = datetime.combine(first, time.min, since.tzinfo) - timedelta(microseconds=1)
            edges = [
                (since, before),
                (datetime.combine(until.date(), time.min, until.tzinfo), until),
            ]
        else:
            edges = [(since, until)]
        for low, high in edges:
            by_run: dict[str, list[LedgerEntry]] = defaultdict(list)
            for entry in await self._ledger.of_kinds(tenant, {FINISHED}, since=low, until=high):
                if entry.refs.run_id is not None:
                    by_run[entry.refs.run_id].append(entry)
            for run_id, inside in by_run.items():
                at_edge = meter(inside)
                used[run_id] = combine(used[run_id], at_edge) if run_id in used else at_edge
        budgets = {run: known[run] for run in used if run in known}
        unknown = {run_id for run_id in used if run_id not in budgets}
        latest: dict[str, str | None] = {run_id: None for run_id in unknown}
        for entry in await self._ledger.of_runs(tenant, unknown, {BUDGET}):
            if entry.refs.run_id is not None and entry.content_digest is not None:
                latest[entry.refs.run_id] = entry.content_digest
        return used, {**budgets, **latest}

    async def _reference(self, digest: str | None) -> dict[str, Any]:
        """The weighting table the run's latest budget statement names; empty when none."""
        if digest is None:
            return {}
        content = await self._objects.get(digest)
        if content is None:
            return {}
        reference: dict[str, Any] = json.loads(content).get("weighting_table") or {}
        return reference

    async def _table(self, reference: dict[str, Any]) -> WeightingTable | None:
        if not reference:
            return None
        document = await self._objects.get(reference["digest"])
        if document is None:
            return None
        return WeightingTable.model_validate(json.loads(document))
