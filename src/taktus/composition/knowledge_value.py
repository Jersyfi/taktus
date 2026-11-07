"""The same work with and without a knowledge source connected, compared on the value
ledger's figures and read for the HTTP surface (UC-5.5 §2, ADR-0291).

The facts come from components that never import each other: the ledger's run and step
entries, the process component's versions — which steps read knowledge —, accounting's spend
of each side's runs, and the value component's stated basis for the currency. The value
component computes the figures. Only the processes the reader may see are compared.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from taktus.components.accounting.application.service.spend import SpendHandler, SpendOfCases
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.value.application.service import ValueBases
from taktus.components.value.domain.model import Figure
from taktus.components.value.domain.service import knowledge
from taktus.ports.clock import Clock
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork

ENDED = frozenset({"run.finished", "run.escalated"})


class KnowledgeComparison:
    def __init__(
        self,
        *,
        versions: Repository[ProcessVersion],
        ledger: Ledger,
        spend: SpendHandler,
        bases: ValueBases,
        work: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._versions = versions
        self._ledger = ledger
        self._spend = spend
        self._bases = bases
        self._work = work
        self._clock = clock

    async def figures(
        self, tenant: Tenant, visible: frozenset[str], days: int, *, until: datetime | None = None
    ) -> list[Figure]:
        """Per process the reader may see whose versions read knowledge: both sides' cockpit
        figures and their differences, over the runs that ended in the period."""
        end = until or self._clock.now()
        since = end - timedelta(days=days)
        async with self._work.transaction(tenant):
            ended = await self._ledger.of_kinds(tenant, ENDED, since=since, until=end)
            ids = {
                e.refs.run_id
                for e in ended
                if e.refs.run_id is not None
                and e.refs.process_version is not None
                and e.refs.process_version.rsplit("@", 1)[0] in visible
            }
            entries = await self._ledger.of_runs(tenant, ids, knowledge.KINDS) if ids else []
            reads: dict[str, frozenset[str]] = {}
            for ref in sorted({e.refs.process_version for e in entries if e.refs.process_version}):
                held = await self._versions.get(tenant, ref)
                reads[ref] = frozenset() if held is None else knowledge.knowledge_reads(held.work)
        stated = await self._bases.current(tenant)
        currency = "EUR" if stated is None else stated.basis.currency
        out: list[Figure] = []
        for process, tallies in sorted(knowledge.sides(entries, reads, since, end).items()):
            cases = {run: side for side in knowledge.SIDES for run in tallies[side].runs}
            spent = await self._spend.of_cases(
                SpendOfCases(process, tenant, cases, since=None, until=end)
            )
            costs: dict[knowledge.Side, float | None] = {
                side: next((c.amounts.get(currency) for c in spent.cases if c.case == side), None)
                for side in knowledge.SIDES
            }
            steps = {s for ref, r in reads.items() if ref.rsplit("@", 1)[0] == process for s in r}
            out.extend(
                knowledge.comparison(
                    process,
                    tallies,
                    steps,
                    since=since,
                    until=end,
                    costs=costs,
                    currency=currency,
                )
            )
        return out
