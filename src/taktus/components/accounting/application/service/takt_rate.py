"""The Takt rate of a tenant: Takte per hour over the window of the table in force (ADR-0010).

What every step of the tenant finished inside the window used, each run's steps weighed at the
weighting table its budget statement names — the table in force when that run started — with
the model classes recorded beside it, summed, and divided by the window's hours. The window is
the table in force's `rate_window_days`: thirty days for version 0 (DEC-0131). A run that
started without a weighting table, or whose table cannot be read, is named, and so is every
quantity a table does not weigh; nothing is counted as zero (UC-8.5).
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from taktus.components.accounting.domain.service import calibration, meter, weigh
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
            entries = list(await self._ledger.entries(query.tenant))
        by_run: dict[str, list[LedgerEntry]] = defaultdict(list)
        for entry in entries:
            if entry.refs.run_id is not None:
                by_run[entry.refs.run_id].append(entry)
        takte, runs = 0.0, 0
        tables: set[tuple[str, bool]] = set()
        unweighed: list[str] = []
        for run_id, of_run in sorted(by_run.items()):
            inside = [e for e in of_run if e.kind == "step.finished" and since <= e.ts <= until]
            if not inside:
                continue
            runs += 1
            reference = await self._reference(of_run)
            table = await self._table(reference)
            if table is None:
                why = (
                    "started without a weighting table in force"
                    if not reference
                    else f"its weighting table {reference['version']} cannot be read"
                )
                unweighed.append(f"run {run_id}: {why}")
                continue
            takt = weigh(meter(inside), table, reference.get("model_classes") or {})
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

    async def _reference(self, entries: list[LedgerEntry]) -> dict[str, Any]:
        """The weighting table the run's latest budget statement names; empty when none."""
        digests = [e.content_digest for e in entries if e.kind == "budget.set"]
        latest = next((d for d in reversed(digests) if d is not None), None)
        if latest is None:
            return {}
        content = await self._objects.get(latest)
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
