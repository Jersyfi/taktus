"""What a run cost, recomputed from the ledger at the price table it was held to.

The run's `budget.set` entry names its budget statement by digest, and the statement names the
price table by the digest of its document. Both documents are in the object store, content-
addressed, so the table read back is the table the run was held to, whatever the configuration
says today. The run's `step.finished` entries are metered (`domain.service.metering`); the
tokens are priced per model and kind, and the compute seconds per resource class, at that one
table (#230). What cannot be priced — a model or a resource class the table does not know, a
table that prices no compute, tokens recorded without a model, a run held without a table — is
named, never counted as free (ADR-0005, ADR-0010).
Where the run was held with an uncalibrated margin an operator set below the floor, the
statement says so, and so does the cost (DEC-0047).

The same breakdown is weighed in Takte at the weighting table the statement names — the table
in force when the run started — with the model classes recorded beside it, or at another table
on request (ADR-0010, UC-8.5). A quantity the table does not weigh is named, never counted as
zero; an uncalibrated table says so beside the figure.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from taktus.components.accounting.domain.service import Meter, Takt, meter, weigh
from taktus.ports.ledger import Ledger
from taktus.ports.model import Priced, PriceTable, WeightingTable, price, price_compute
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Tenant, UnitOfWork
from taktus.shared.v1 import LedgerEntry, Value


class RunCost(Value):
    run_id: str
    meter: Meter
    priced: Priced | None
    """Money at the run's price table, tokens and compute together; None when the run was held
    without one."""
    tokens_amount: float | None = None
    """The part of the money that is tokens."""
    compute_amount: float | None = None
    """The part of the money that is compute seconds."""
    table_digest: str | None
    unpriced: tuple[str, ...] = ()
    """What the amount leaves out, and why."""
    below_floor: str | None = None
    """The budget statement's word that the run was held with an uncalibrated margin set below
    the floor (DEC-0047); None when it was not."""
    takt: Takt | None = None
    """The breakdown in Takte at the run's weighting table, or at the table asked for; None
    when there is none, and `unweighed` says why."""
    weights_digest: str | None = None
    """The digest of the weighting table's document, when it is the run's own."""
    unweighed: tuple[str, ...] = ()
    """What the Takte leave out, and why."""


@dataclass(frozen=True)
class CostOfRun:
    run_id: str
    tenant: Tenant
    table: PriceTable | None = None
    """A table to price at instead of the run's own: to compare, never to rewrite."""
    weights: WeightingTable | None = None
    """A weighting table to weigh at instead of the run's own: to compare, never to rewrite."""
    model_classes: Mapping[str, str] | None = None
    """The classes of the models, instead of those recorded with the run."""


class CostOfRunHandler:
    def __init__(self, ledger: Ledger, objects: ObjectStore, work: UnitOfWork) -> None:
        self._ledger = ledger
        self._objects = objects
        self._work = work

    async def execute(self, query: CostOfRun) -> RunCost:
        async with self._work.transaction(query.tenant):
            entries = list(await self._ledger.entries(query.tenant, query.run_id))
        used = meter(entries)
        statement = await self._statement_of(entries)
        takt = await self._takt(used, statement, query)
        below_floor = (statement.get("uncalibrated_margin") or {}).get("below_floor")
        table, digest = query.table, None
        if table is None:
            table, digest = await self._table_of(statement)
        unpriced: list[str] = []
        if used.tokens_unattributed:
            unpriced.append(
                f"{used.tokens_unattributed} token(s) recorded without the model that used them"
            )
        if table is None:
            if used.tokens or used.compute_seconds:
                unpriced.append("the run was held without a price table")
            return RunCost(
                run_id=query.run_id,
                meter=used,
                priced=None,
                table_digest=None,
                unpriced=tuple(unpriced),
                below_floor=below_floor,
                **takt,
            )
        tokens = price(used.tokens, table)
        unpriced.extend(f"no price for {kind}" for kind in tokens.unpriced)
        compute = price_compute(used.compute_seconds, table)
        if table.compute is None and compute.unpriced:
            classes = ", ".join(sorted(c for c, s in used.compute_seconds.items() if s))
            unpriced.append(
                f"compute seconds were not priced: price table {table.version} prices no "
                f"compute ({classes})"
            )
        else:
            unpriced.extend(f"no price for {kind}" for kind in compute.unpriced)
        priced = Priced(
            amount=round(tokens.amount + compute.amount, 9),
            currency=table.currency,
            table=table.version,
            unpriced=tokens.unpriced + compute.unpriced,
        )
        return RunCost(
            run_id=query.run_id,
            meter=used,
            priced=priced,
            tokens_amount=tokens.amount,
            compute_amount=compute.amount,
            table_digest=digest,
            unpriced=tuple(unpriced),
            below_floor=below_floor,
            **takt,
        )

    async def _takt(
        self, used: Meter, statement: dict[str, Any], query: CostOfRun
    ) -> dict[str, Any]:
        """The fields of the cost that are the Takt: at the table asked for, or at the run's."""
        reference = statement.get("weighting_table") or {}
        classes = query.model_classes
        if classes is None:
            classes = reference.get("model_classes") or {}
        table, digest = query.weights, None
        if table is None:
            if not reference:
                return {"unweighed": ("the run started without a weighting table in force",)}
            document = await self._objects.get(reference["digest"])
            if document is None:
                return {"unweighed": (f"weighting table {reference['version']} cannot be read",)}
            table = WeightingTable.model_validate(json.loads(document))
            digest = reference["digest"]
        takt = weigh(used, table, classes)
        return {"takt": takt, "weights_digest": digest, "unweighed": takt.unweighed}

    async def _statement_of(self, entries: list[LedgerEntry]) -> dict[str, Any]:
        """The run's latest budget statement; empty when it has none that can be read."""
        statements = [e.content_digest for e in entries if e.kind == "budget.set"]
        latest = next((d for d in reversed(statements) if d is not None), None)
        if latest is None:
            return {}
        content = await self._objects.get(latest)
        if content is None:
            return {}
        statement: dict[str, Any] = json.loads(content)
        return statement

    async def _table_of(self, statement: dict[str, Any]) -> tuple[PriceTable | None, str | None]:
        reference = statement.get("price_table")
        if not reference:
            return None, None
        document = await self._objects.get(reference["digest"])
        if document is None:
            return None, None
        return PriceTable.model_validate(json.loads(document)), reference["digest"]
