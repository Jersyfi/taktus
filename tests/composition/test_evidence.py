"""The evidence of what is processed, where, by which adapter and kept how long, generated from
configuration and the ledger (UC-11.2, ADR-0176 §8).

The world of `test_acting`: `billing` reads through `connector.fake` and drafts with
`model.third`; `support` answers with `model.first`, which declares `eu`. Nothing in the
evidence is written by hand: a change of the configuration is a change of the evidence.
"""

from __future__ import annotations

from taktus.adapters.driven.memory import MemoryRepository
from taktus.adapters.driven.memory.trace_store import MemoryTraceStore
from taktus.components.governance.application.service import (
    ConfigureResidency,
    DeclareSources,
    TenantSources,
)
from taktus.components.governance.domain.model import SourceDeclaration
from taktus.composition.subjects import ProcessingEvidence
from taktus.ports.ledger import Fact
from taktus.ports.traces import TraceRetention
from taktus.shared.v1 import LedgerRefs

from .test_acting import TENANT, World


def evidence_of(world: World) -> tuple[ProcessingEvidence, TenantSources, MemoryTraceStore]:
    sources = TenantSources(
        MemoryRepository(world.persistence, SourceDeclaration),
        world.ledger,
        world.persistence,
        world.clock,
    )
    traces = MemoryTraceStore(world.persistence)
    return (
        ProcessingEvidence(
            register=world.reads.register,
            processes=world.processes,
            versions=world.versions,
            sources=sources,
            residency=world.residency,
            ledger=world.ledger,
            work=world.persistence,
            clock=world.clock,
            traces=traces,
        ),
        sources,
        traces,
    )


async def test_the_evidence_names_every_adapter_where_it_processes_and_how_long_it_keeps() -> None:
    world = await World().registered()
    evidence, _, _ = evidence_of(world)
    document = await evidence.evidence(TENANT)
    assert document["legally_reviewed"] is False and "Not legally reviewed" in document["notice"]
    adapters = {a["adapter"]: a for a in document["adapters"]}
    assert adapters["model.first"]["location"] == "eu"
    assert adapters["model.third"]["location"] == "elsewhere"
    assert document["residency_rule"] == "anywhere"
    keeping = {k["record"]: k["kept"] for k in document["keeping"]}
    assert keeping["trace"].startswith("30 days")
    assert "erases it" in keeping["run content"]
    assert document["personal_data_steps"] == []
    assert document["requests"]["prepared"] == 0


async def test_a_change_of_the_configuration_is_a_change_of_the_evidence() -> None:
    world = await World().registered()
    evidence, sources, traces = evidence_of(world)
    await sources.declare(DeclareSources(tenant=TENANT, personal=("fake.records",)), by="idn_a")
    await world.residency.configure(ConfigureResidency(tenant=TENANT, location="eu"), by="idn_a")
    async with world.persistence.transaction(TENANT):
        await traces.set_retention(TENANT, TraceRetention(days=7, configured_at=world.clock.now()))
        await world.ledger.record(
            TENANT,
            Fact(
                kind="subject.request_prepared",
                refs=LedgerRefs(tenant=TENANT, subject_request_id="dsr_1", actor="idn_a"),
                outcome="erasure",
            ),
        )
    document = await evidence.evidence(TENANT)
    assert document["personal_capabilities"] == ["fake.records"]
    (step,) = document["personal_data_steps"]
    assert (step["process"], step["step"], step["adapter"]) == (
        "billing",
        "fetch",
        "connector.fake",
    )
    assert step["personal_data"] == "declared personal"
    assert document["residency_rule"] == "eu"
    adapters = {a["adapter"]: a for a in document["adapters"]}
    assert adapters["model.third"]["within_residency_rule"] == "outside"
    assert {k["record"]: k["kept"] for k in document["keeping"]}["trace"].startswith("7 days")
    assert document["requests"]["prepared"] == 1
