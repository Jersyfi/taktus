"""Use case: the instance runs the conformance suite of an adapter's contract and records what
it found, in the same operation (ADR-0044).

This is the one writer of the conformance half of an adapter's maturity. Its command names the
adapter, who started the run and, where a process started it, that run. It takes no report, no
verdict and no date: the report is what the suite returned a moment ago, through the catalog's
`Suites` port, and the outcome is read from the report's checks here.

The evidence — the report together with the configuration it was taken under — is stored as
one document in the object store. Then one transaction writes two things. The ledger entry
`conformance.tested`: `adapter` names the integration, `outcome` is `passed`, `failed` or
`incomplete`, `content_digest` is the digest of the evidence, and `refs` name the actor and the
run. And the conformance half of the adapter's maturity record, which keeps the removal half
as it was. A run that did not pass is recorded too, as not passed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from taktus.components.catalog.domain.model import (
    AdapterMaturity,
    ConformanceResult,
    judged,
)
from taktus.components.catalog.ports import Suites
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerEntry, LedgerRefs

CONFORMANCE_TESTED = "conformance.tested"


@dataclass(frozen=True)
class RunConformance:
    integration: str
    """The adapter identifier: `worker.<kind>`, `connector.<label>`, `model.endpoint`."""
    tenant: Tenant
    actor: str
    """Who started the run, as the ledger names them."""
    run_id: str | None = None
    """The run of the process that started it, when a process did."""


class RunConformanceHandler:
    def __init__(
        self,
        suites: Suites,
        maturities: Repository[AdapterMaturity],
        work: UnitOfWork,
        ledger: Ledger,
        objects: ObjectStore,
        clock: Clock,
    ) -> None:
        self._suites = suites
        self._maturities = maturities
        self._work = work
        self._ledger = ledger
        self._objects = objects
        self._clock = clock

    async def execute(self, command: RunConformance) -> tuple[AdapterMaturity, LedgerEntry]:
        ran = await self._suites.run(command.integration)
        outcome, failed, inconclusive = judged(ran.report)
        evidence = {
            "integration": ran.integration,
            "contract": ran.contract,
            "taktus_version": ran.taktus_version,
            "configuration": ran.configuration.document(),
            "report": ran.report,
        }
        digest = await self._objects.put(
            json.dumps(evidence, ensure_ascii=False, sort_keys=True).encode("utf-8")
        )
        now = self._clock.now()
        result = ConformanceResult(
            integration=ran.integration,
            family=ran.family,
            contract=ran.contract,
            taktus_version=ran.taktus_version,
            configuration=ran.configuration,
            outcome=outcome,
            failed=failed,
            inconclusive=inconclusive,
            digest=digest,
            tested_at=now,
            actor=command.actor,
            run_id=command.run_id,
        )
        async with self._work.transaction(command.tenant):
            current = await self._maturities.get(command.tenant, ran.integration)
            record = AdapterMaturity(
                id=ran.integration,
                tenant=command.tenant,
                family=ran.family,
                conformance=result,
                removal=None if current is None else current.removal,
                updated_at=now,
            )
            await self._maturities.put(command.tenant, record)
            entry = await self._ledger.record(
                command.tenant,
                Fact(
                    kind=CONFORMANCE_TESTED,
                    refs=LedgerRefs(
                        tenant=command.tenant, run_id=command.run_id, actor=command.actor
                    ),
                    adapter=ran.integration,
                    outcome=outcome,
                    content_digest=digest,
                ),
            )
        return record, entry
