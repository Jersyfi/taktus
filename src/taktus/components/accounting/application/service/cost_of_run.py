"""What a run cost, recomputed from the ledger at the price table it was held to.

The run's `budget.set` entry names its budget statement by digest, and the statement names the
price table by the digest of its document. Both documents are in the object store, content-
addressed, so the table read back is the table the run was held to, whatever the configuration
says today. The run's `step.finished` entries are metered (`domain.service.metering`) and the
tokens priced. What cannot be priced — a model the table does not know, tokens recorded without
a model, a run held without a table — is named, never counted as free (ADR-0005, ADR-0010).
Where the run was held with an uncalibrated margin an operator set below the floor, the
statement says so, and so does the cost (DEC-0047).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from taktus.components.accounting.domain.service import Meter, meter
from taktus.ports.ledger import Ledger
from taktus.ports.model import Priced, PriceTable, price
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Tenant, UnitOfWork
from taktus.shared.v1 import LedgerEntry, Value


class RunCost(Value):
    run_id: str
    meter: Meter
    priced: Priced | None
    """Money at the run's price table; None when the run was held without one."""
    table_digest: str | None
    unpriced: tuple[str, ...] = ()
    """What the amount leaves out, and why."""
    below_floor: str | None = None
    """The budget statement's word that the run was held with an uncalibrated margin set below
    the floor (DEC-0047); None when it was not."""


@dataclass(frozen=True)
class CostOfRun:
    run_id: str
    tenant: Tenant
    table: PriceTable | None = None
    """A table to price at instead of the run's own: to compare, never to rewrite."""


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
            if used.tokens:
                unpriced.append("the run was held without a price table")
            return RunCost(
                run_id=query.run_id,
                meter=used,
                priced=None,
                table_digest=None,
                unpriced=tuple(unpriced),
                below_floor=below_floor,
            )
        priced = price(used.tokens, table)
        unpriced.extend(f"no price for {kind}" for kind in priced.unpriced)
        return RunCost(
            run_id=query.run_id,
            meter=used,
            priced=priced,
            table_digest=digest,
            unpriced=tuple(unpriced),
            below_floor=below_floor,
        )

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
