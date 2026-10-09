"""The run's maturity port, answered from the catalog's record (ADR-0039, NTC-0051).

From autonomy level 3 a step runs only on an adapter whose maturity is *verified* or above. The
catalog component keeps one maturity record per adapter identifier and derives *verified* from
its two halves (`components/catalog/domain/model/maturity.py`); the run asks through its own
port. Composition joins the two, because components never import each other.

A conformance pass counts only for the configuration it names (ADR-0044). The standing is
therefore derived against the configuration the run's own pools resolve for the identifier now:
the adapter, what it declared and its version. Where they differ from what the pass names, the
adapter is *experimental*, and `missing` says the pass was for another configuration.

The loopback connector is no integration: it is Taktus reached by Taktus, every operation of it
is a read inside the instance, and the removal test never lists it, so it can never earn the
removal half (`docs/architecture/contracts.md` §4). It is answered as such, not as *verified*
(NTC-0079). An adapter nothing has recorded is *experimental*.
"""

from __future__ import annotations

from taktus.adapters.driven.connectors.loopback import ADAPTER as LOOPBACK
from taktus.components.catalog.domain.model import AdapterMaturity
from taktus.components.run.ports import Standing
from taktus.composition.pools import Pools
from taktus.ports.persistence import Repository, Tenant, UnitOfWork

NOT_INTEGRATIONS: frozenset[str] = frozenset({LOOPBACK})


class CatalogMaturities:
    def __init__(
        self, records: Repository[AdapterMaturity], work: UnitOfWork, pools: Pools
    ) -> None:
        self._records = records
        self._work = work
        self._pools = pools

    async def standing(self, tenant: Tenant, adapter: str) -> Standing:
        if adapter in NOT_INTEGRATIONS:
            return Standing(adapter=adapter, integration=False)
        async with self._work.transaction(tenant):
            record = await self._records.get(tenant, adapter)
        if record is None:
            return Standing(
                adapter=adapter,
                maturity="experimental",
                missing=(
                    "the conformance suite has not been recorded as passed",
                    "the removal test has not run",
                ),
            )
        try:
            current = await self._pools.configuration(adapter)
        except Exception:
            current = None
        return Standing(
            adapter=adapter,
            maturity=str(record.maturity(current)),
            missing=record.missing(current),
        )
