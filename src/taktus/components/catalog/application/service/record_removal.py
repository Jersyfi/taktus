"""Use case: the result of a removal test is written to the adapter's maturity and to the
ledger, in one transaction.

The ledger entry is `removal.tested`: `adapter` names the integration, `outcome` the verdict,
`content_digest` the digest of the result document, and `refs.run_id` the run of the removal
test process that produced it. It carries nothing else (ADR-0006); the result itself is the
step's artifact in that run. The maturity record keeps the last result and derives what is
still missing for *verified*.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from taktus.components.catalog.domain.model import AdapterMaturity, RemovalResult
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerEntry, LedgerRefs

REMOVAL_TESTED = "removal.tested"


@dataclass(frozen=True)
class RecordRemovalResult:
    result: RemovalResult
    tenant: Tenant


class RecordRemovalResultHandler:
    def __init__(
        self,
        maturities: Repository[AdapterMaturity],
        work: UnitOfWork,
        ledger: Ledger,
        clock: Clock,
    ) -> None:
        self._maturities = maturities
        self._work = work
        self._ledger = ledger
        self._clock = clock

    async def execute(self, command: RecordRemovalResult) -> tuple[AdapterMaturity, LedgerEntry]:
        result = command.result
        async with self._work.transaction(command.tenant):
            current = await self._maturities.get(command.tenant, result.integration)
            record = AdapterMaturity(
                id=result.integration,
                tenant=command.tenant,
                family=result.family,
                conformance_passed_at=None if current is None else current.conformance_passed_at,
                removal=result,
                updated_at=self._clock.now(),
            )
            await self._maturities.put(command.tenant, record)
            entry = await self._ledger.record(
                command.tenant,
                Fact(
                    kind=REMOVAL_TESTED,
                    refs=LedgerRefs(tenant=command.tenant, run_id=result.run_id),
                    adapter=result.integration,
                    outcome=str(result.verdict),
                    content_digest=digest_of(result),
                ),
            )
        return record, entry


def digest_of(result: RemovalResult) -> str:
    canonical = json.dumps(result.document(), ensure_ascii=False, sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()
