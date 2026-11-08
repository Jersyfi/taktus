"""K-01 run with the wiki connected and without it, compared on the value ledger's figures
(UC-5.5 §2, ADR-0291).

The same process answers the same question twice with the wiki connected, and once on an
engine that has no connector for `knowledge.documents`: the search falls back to a person and
the run escalates. The comparison reads the ledger, the version's knowledge reads and
accounting's spend, and puts both sides beside each other on the cockpit's figures.
"""

from __future__ import annotations

from fakes.maturity import VERIFIED

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import MemoryProvenanceStore, MemoryRepository
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.accounting.application.service.spend import SpendHandler
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.run.application.service import EngineOptions, RunEngine
from taktus.components.run.domain.model import Run, RunState
from taktus.components.value.application.service import ValueBases
from taktus.components.value.domain.model import ValueBasis
from taktus.composition.knowledge import IndexedCitations
from taktus.composition.knowledge_value import KnowledgeComparison
from taktus.composition.personal import ConfiguredPersonalCredentials

from .test_knowledge_answers import ADA, TENANT, Wiki, World, why
from .test_knowledge_answers import wiki as wiki  # the fixture


class Both(World):
    """One ledger, two engines: one with the wiki connected, one without any connector."""

    def __init__(self, wiki: Wiki) -> None:
        super().__init__(wiki)
        self.bare = RunEngine(
            maturities=VERIFIED,
            runs=MemoryRepository(self.persistence, Run),
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=MemoryProvenanceStore(self.persistence),
            workers=StaticWorkerPool([]),
            clock=self.clock,
            ids=self.ids,
            telemetry=NoTelemetry(),
            options=EngineOptions(uncalibrated_margin=0.0),
            connectors=StaticConnectorPool([]),
            models=StaticModelPool(
                [("model.fake", ["triage", "support"], self.model, "fake-model@1")]
            ),
            personal=ConfiguredPersonalCredentials(
                {(ADA, "KNOWLEDGE_TOKEN"): "KNOWLEDGE_TOKEN_ADA"}
            ),
            citations=IndexedCitations(self.entries, self.persistence),
        )
        self.comparison = KnowledgeComparison(
            versions=MemoryRepository(self.persistence, ProcessVersion),
            ledger=self.ledger,
            spend=SpendHandler(self.ledger, self.objects, self.persistence),
            bases=ValueBases(
                MemoryRepository(self.persistence, ValueBasis),
                self.ledger,
                self.persistence,
                self.clock,
            ),
            work=self.persistence,
            clock=self.clock,
        )

    async def ask_without(self) -> Run:
        connected = self.engine
        self.engine = self.bare
        try:
            return await self.ask(ADA)
        finally:
            self.engine = connected


async def test_the_same_work_with_and_without_the_wiki_is_compared_on_the_value_ledger(
    wiki: Wiki,
) -> None:
    w = Both(wiki)
    first, second = await w.ask(ADA), await w.ask(ADA)
    alone = await w.ask_without()
    assert first.state is RunState.FINISHED and second.state is RunState.FINISHED, why(first)
    assert alone.state is RunState.ESCALATED, why(alone)
    process = first.process_version.rsplit("@", 1)[0]
    found = {
        f.id: f
        for f in await w.comparison.figures(TENANT, frozenset({process}), 30)
        if f.subject == process
    }
    assert found["value.with_knowledge.runs_ended"].basis["runs"] == sorted([first.id, second.id])
    assert found["value.without_knowledge.runs_ended"].basis["runs"] == [alone.id]
    assert found["value.with_knowledge.quality"].value == 1
    assert found["value.without_knowledge.quality"].value == 0
    assert found["value.knowledge_effect.quality"].value == 1
    assert found["value.knowledge_effect.escalation_rate"].value == -1
    assert found["value.with_knowledge.automation"].value == 1
    assert found["value.knowledge_effect.quality"].basis["knowledge_reads"] == [
        "confirm",
        "search",
    ]
    for compared in ("cycle_seconds", "quality", "cost_per_case", "automation"):
        for prefix in ("value.with_knowledge", "value.without_knowledge"):
            figure = found[f"{prefix}.{compared}"]
            assert figure.value is not None or figure.withheld, figure.id
            assert figure.value != 0 or figure.withheld is None, figure.id
    assert await w.comparison.figures(TENANT, frozenset(), 30) == [], "a process not seen"
