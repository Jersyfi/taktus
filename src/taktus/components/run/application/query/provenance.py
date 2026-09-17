"""Queries over the provenance chain (ADR-0021): what an artifact is made of, and whether a
run's chain is unbroken.

`chain` answers "given an artifact, what produced it, and what produced that?" in one query of
the store. `verify` reads a run, its records and its ledger entries and holds them against
each other with the domain's rule (`domain.service.provenance.verify`)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from taktus.components.run.domain.model import Run, UnknownRun
from taktus.components.run.domain.service.provenance import ChainVerification, verify
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import ProvenanceStore, Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Provenance


@dataclass(frozen=True)
class ChainOf:
    """The full chain behind one artifact of one run."""

    run_id: str
    artifact_id: str
    tenant: Tenant


@dataclass(frozen=True)
class ProvenanceOfRun:
    run_id: str
    tenant: Tenant


class ProvenanceQuery:
    def __init__(
        self,
        provenance: ProvenanceStore,
        runs: Repository[Run],
        ledger: Ledger,
        work: UnitOfWork,
    ) -> None:
        self._provenance = provenance
        self._runs = runs
        self._ledger = ledger
        self._work = work

    async def chain(self, query: ChainOf) -> Sequence[Provenance]:
        """From the record that produced the artifact back to the first input, in one query.
        Empty when the run has no record listing the artifact."""
        async with self._work.transaction(query.tenant):
            return await self._provenance.chain(query.tenant, query.run_id, query.artifact_id)

    async def of_run(self, query: ProvenanceOfRun) -> Sequence[Provenance]:
        async with self._work.transaction(query.tenant):
            return await self._provenance.of_run(query.tenant, query.run_id)

    async def verify(self, query: ProvenanceOfRun) -> ChainVerification:
        """Every completed step has one record, every input leads to a record that lists it,
        every record agrees with its ledger entry."""
        async with self._work.transaction(query.tenant):
            run = await self._runs.get(query.tenant, query.run_id)
            if run is None:
                raise UnknownRun(query.run_id)
            records = await self._provenance.of_run(query.tenant, query.run_id)
            entries = await self._ledger.entries(query.tenant, query.run_id)
        return verify(run, records, entries)
