"""The ledger, exported as a telemetry signal entry by entry (UC-6.1, ADR-0253 §3).

Every committed entry becomes one span `ledger.entry`, whose attributes are the entry's own
fields and nothing else: its kind, sequence number and place, its hash and its predecessor's, its
time, every reference it carries, its method, model, adapter, outcome, content digest, duration
and consumption. A ledger entry carries no text (ADR-0006), so neither does the signal.

The scheduler's leader reads each tenant's entries above the place it reached, up to the stable
head, and emits them in sequence order. It starts at the head it finds at its first look: the
signal carries what is recorded from then on, and the export of the file
(`GET /ledger/export`) carries the history. A signal is the operator's telemetry, never the
record: an entry the signal lost is still in the ledger.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timedelta
from typing import Any

import structlog

from taktus.composition.tenancy import this_round
from taktus.ports.clock import Clock
from taktus.ports.identity import ServedTenants
from taktus.ports.persistence import LedgerStore, Tenant, UnitOfWork
from taktus.ports.telemetry import AttributeValue, Telemetry
from taktus.shared.v1 import LedgerEntry

SPAN = "ledger.entry"
_SEGMENT = re.compile(r"^[a-z][a-z0-9_]*$")
"""One part of a dotted attribute name, as the telemetry adapter accepts it."""
BATCH = 500
INTERVAL_SECONDS = 5

log = structlog.get_logger("taktusd")


def attributes_of(entry: LedgerEntry) -> dict[str, AttributeValue]:
    """The entry's fields as span attributes, `ledger.<field>`, its references and consumption
    flattened, `ledger.refs.<name>`; an absent field is left out. A mapping keyed by data
    rather than by field names — the tokens per model, keyed by the model's name — is one
    attribute holding it as JSON: a model's name is not an attribute name, and an entry the
    exporter refuses would hold the signal at that entry for good."""
    found: dict[str, AttributeValue] = {}

    def put(prefix: str, document: Mapping[str, Any]) -> None:
        for key, value in document.items():
            if value is None:
                continue
            name = f"{prefix}.{key}"
            if isinstance(value, Mapping) and not all(_SEGMENT.match(str(k)) for k in value):
                found[name] = json.dumps(value, sort_keys=True, default=str)
            elif isinstance(value, Mapping):
                put(name, value)
            elif isinstance(value, bool | int | float | str):
                found[name] = value
            else:
                found[name] = str(value)

    put("ledger", entry.document())
    return found


class LedgerSignal:
    def __init__(self, store: LedgerStore, work: UnitOfWork, telemetry: Telemetry) -> None:
        self._store = store
        self._work = work
        self._telemetry = telemetry
        self._reached: dict[Tenant, int] = {}

    async def look(self, tenant: Tenant) -> int:
        """Emit the tenant's entries committed since the last look; how many."""
        async with self._work.transaction(tenant):
            head = await self._store.head(tenant)
        if tenant not in self._reached:
            self._reached[tenant] = head
            return 0
        emitted = 0
        while self._reached[tenant] < head:
            async with self._work.transaction(tenant):
                batch = await self._store.after(
                    tenant, self._reached[tenant], limit=BATCH, through=head
                )
            if not batch:
                break
            for entry in batch:
                async with self._telemetry.span(SPAN, attributes_of(entry)):
                    pass
                emitted += 1
            self._reached[tenant] = batch[-1].seq
        return emitted


def ledger_signal_tick(
    signal: LedgerSignal,
    tenants: ServedTenants,
    clock: Clock,
    *,
    interval_seconds: int = INTERVAL_SECONDS,
) -> Callable[[], Awaitable[None]]:
    """What the scheduler calls on every tick. A look that fails is logged and made again."""
    last: list[datetime] = []

    async def tick() -> None:
        now = clock.now()
        if last and now - last[0] < timedelta(seconds=interval_seconds):
            return
        last[:] = [now]
        for tenant in await this_round(tenants, "scheduler"):
            try:
                await signal.look(tenant)
            except Exception as error:  # the signal must never take the scheduler down
                log.error(
                    "the ledger's signal was not emitted; the next look tries again",
                    tenant=tenant,
                    error=f"{type(error).__name__}: {error}",
                )

    return tick
