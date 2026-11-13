"""The removal test of a knowledge source (UC-5.5 §2, ADR-0265 §5, S-01): removing the wiki
changes what Taktus knows and breaks no process.

The wiki connector is configured beside the loopback, as `TAKTUS_CONNECTORS` would configure
it, over the fake of the wiki, and K-01 is registered. The removal test runs K-01 twice, as
rehearsals: with the wiki, the answer cites its pages; without it, the search has no adapter
and falls back to a person. The verdict is *changed*, never *broke*. The rehearsals read with
the removal test's own identity and its own credential (ADR-0264); nothing leaves the system.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import yaml
from composition.test_knowledge_answers import Reader
from fakes import FakeClock, FakeIdentifiers, wiki_service
from fakes.identity import directory
from fakes.maturity import VERIFIED
from taktus_connectors.bookstack.server import Config, build_server

from integration.test_removal_test import TENANT, result_of, run_removal
from taktus.adapters.driven.connectors.loopback import ADAPTER as LOOPBACK
from taktus.adapters.driven.connectors.loopback import LoopbackConnector
from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.models.pool import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.adapters.driving.cli.wiring import Services
from taktus.components.catalog.application.service import RecordRemovalResultHandler
from taktus.components.catalog.domain.model import AdapterMaturity
from taktus.components.command.application.service import CommissionPlanHandler
from taktus.components.knowledge.domain.model import KnowledgeEntry
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.run.application.query import ProvenanceQuery, RecordedResponses
from taktus.components.run.application.service import RunEngine
from taktus.components.run.domain.model import Run, RunState
from taktus.composition.knowledge import IndexedCitations
from taktus.composition.levels import VersionStatements
from taktus.composition.loopback import Loopback, Pools
from taktus.composition.personal import ConfiguredPersonalCredentials
from taktus.shared.v1 import Command, Plan

ROOT = Path(__file__).resolve().parents[2]
K_01 = ROOT / "blueprints" / "knowledge" / "processes" / "K-01-answer-from-knowledge.yaml"
SOURCE = "connector.knowledge"
REMOVER = "idn_test"
"""The identity the removal test runs as, and its rehearsals with it."""


@pytest.fixture
def wiki_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    token = f"{secrets.token_hex(6)}:{secrets.token_hex(12)}"
    server = wiki_service.make_server("127.0.0.1", 0, {token: "read"})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    path = tmp_path / "KNOWLEDGE_TOKEN_REMOVAL"
    path.write_text(token, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_KNOWLEDGE_TOKEN_REMOVAL_FILE", str(path))
    url = f"http://127.0.0.1:{server.server_address[1]}"

    httpx.post(
        f"{url}/_fake/pages",
        json={"book": "Administration", "name": "Holidays", "markdown": "Holidays: 30 days."},
        timeout=5,
    ).raise_for_status()
    yield url
    server.shutdown()
    server.server_close()


def services_with_the_wiki(url: str) -> Services:
    """The wiring of `composition/local.py` over memory, as `connector_services` of
    `test_removal_test.py` builds it, with the wiki connector, a model and the knowledge index."""
    clock, ids = FakeClock(), FakeIdentifiers()
    persistence = MemoryPersistence()
    runs = MemoryRepository(persistence, Run)
    objects = MemoryObjectStore()
    ledger = ChainedLedger(MemoryLedgerStore(persistence), clock)
    provenance = MemoryProvenanceStore(persistence)
    recordings = RecordedResponses(runs, persistence, objects)
    loopback = LoopbackConnector()
    wiki = McpActionConnector(build_server(Config(target=url, timeout=5.0)), timeout=10.0)
    pools = Pools(
        StaticWorkerPool([]),
        StaticConnectorPool([(SOURCE, wiki), (LOOPBACK, loopback)]),
        StaticModelPool([("model.fake", ["triage", "support"], Reader(), "fake-model@1")]),
    )
    entries = MemoryRepository(persistence, KnowledgeEntry)

    def engine_for(
        workers: StaticWorkerPool, connectors: StaticConnectorPool, models: StaticModelPool
    ) -> RunEngine:
        return RunEngine(
            maturities=VERIFIED,
            runs=runs,
            work=persistence,
            objects=objects,
            ledger=ledger,
            provenance=provenance,
            workers=workers,
            clock=clock,
            ids=ids,
            telemetry=NoTelemetry(),
            connectors=connectors,
            models=models,
            recordings=recordings,
            statements=VersionStatements(
                persistence, MemoryRepository(persistence, ProcessVersion)
            ),
            personal=ConfiguredPersonalCredentials(
                {(REMOVER, "KNOWLEDGE_TOKEN"): "KNOWLEDGE_TOKEN_REMOVAL"}
            ),
            citations=IndexedCitations(entries, persistence),
        )

    commission = CommissionPlanHandler(
        MemoryRepository(persistence, Command),
        MemoryRepository(persistence, Plan),
        persistence,
        clock,
        ids,
    )
    versions = MemoryRepository(persistence, ProcessVersion)
    loopback.bind(
        Loopback(
            pools=pools,
            versions=versions,
            work=persistence,
            commission=commission,
            engine_for=engine_for,
            record=RecordRemovalResultHandler(
                MemoryRepository(persistence, AdapterMaturity), persistence, ledger, clock
            ),
            recordings=recordings,
            clock=clock,
            ids=ids,
        )
    )
    placed = directory((TENANT,), persistence=persistence, clock=clock)
    return Services(
        identities=placed.directory,
        tenants=placed.tenants,
        register_version=RegisterProcessVersionHandler(versions, persistence, ledger=ledger),
        commission=commission,
        engine=engine_for(pools.workers, pools.connectors, pools.models),
        provenance=ProvenanceQuery(provenance, runs, ledger, persistence),
        runs=runs,
        ledger=ledger,
        work=persistence,
        clock=clock,
        ids=ids,
        storage="memory, for the test",
    )


async def test_removing_the_knowledge_source_changes_what_is_known_and_breaks_no_process(
    wiki_url: str,
) -> None:
    services = services_with_the_wiki(wiki_url)
    bundle = yaml.safe_load(K_01.read_text(encoding="utf-8"))
    await services.register_version.execute(RegisterProcessVersion(bundle, tenant=TENANT))

    run = await run_removal(services, SOURCE)
    assert run.state is RunState.FINISHED, run.reason
    result = (await result_of(services, run, "exercise"))["output"]
    assert "knowledge.documents" in result["configuration"]["serves"]
    (process,) = result["processes"]
    assert process["process"] == "k-01@2"
    assert process["exercised"] == "run", process.get("note")
    assert process["baseline"]["state"] == "finished", "with the wiki, the answer is cited"
    assert process["withheld"]["state"] == "escalated"
    assert process["withheld"]["at_step"] == "search"
    search = next(s for s in process["steps"] if s["step"] == "search")
    assert search["fallback"] == "human" and "falls back to a person" in search["reason"]
    assert process["verdict"] == result["verdict"] == "changed", process["note"]
    assert "a person takes over" in process["note"]

    async with services.work.transaction(TENANT):
        entries = list(await services.ledger.entries(TENANT))
    assert not [e for e in entries if e.kind.startswith("egress.")], "nothing left the system"
