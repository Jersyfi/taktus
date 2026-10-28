"""What acts for a tenant, what depends on it, and how a process really runs, gathered from the
records that exist (ADR-0147, UC-7.8, UC-6.16, UC-9.7).

Two processes over two connectors and three models, configured as the pools resolve them now:
`billing` reads through `connector.fake` alone and drafts with `model.third`, falling back to a
person of the role `support-lead`; `support` asks the purpose `reasoning`, which `model.first`
serves and `model.second` could. The views read the versions, the pools, the residency rule,
the ledger and the provenance store, and store nothing."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from fakes import FakeClock, FakeConnector, FakeWorker
from fakes.identity import directory
from fakes.model import FakeModel

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.models.pool import Declared
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.catalog.domain.model import AdapterMaturity
from taktus.components.governance.application.service import TenantResidency
from taktus.components.governance.domain.model import ResidencyRule
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.composition.acting import ActingReads
from taktus.composition.maturity import CatalogMaturities, InstanceCatalogue
from taktus.composition.pools import Pools
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerRefs, Provenance

AT = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)
TENANT = "default"
READ = "fake.records.read"


def bundle(id: str, *steps: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": id,
        "version": "1",
        "name": id,
        "autonomy": {"level": 2, "reason": "a person confirms", "toward_next": "twenty runs"},
        "steps": list(steps),
    }


BILLING = bundle(
    "billing",
    {
        "id": "fetch",
        "method": "rule",
        "reason": "r",
        "rejected": [],
        "exactness": "sourced",
        "work": {"rule": "connector", "operation": READ, "input": {"id": "x"}},
    },
    {
        "id": "draft",
        "method": "llm",
        "reason": "r",
        "rejected": [],
        "exactness": "free",
        "fallback": {"when": "unsure", "to": "human", "role": "support-lead"},
        "work": {"purpose": "summary", "prompt": "Summarise."},
        "depends_on": ["fetch"],
    },
)
SUPPORT = bundle(
    "support",
    {
        "id": "answer",
        "method": "llm",
        "reason": "r",
        "rejected": [],
        "exactness": "tolerant",
        "fallback": {"when": "unsure", "to": "llm"},
        "work": {"purpose": "reasoning", "prompt": "Answer."},
    },
)


class Held:
    def __init__(self) -> None:
        self.requested: list[tuple[str, str]] = []

    async def held(self, tenant: str) -> frozenset[str]:
        return frozenset(a for a, _ in self.requested)

    async def request(self, tenant: str, adapter: str, actor: str) -> Any:
        self.requested.append((adapter, actor))
        return SimpleNamespace(adapter=adapter)


class NoBlocks:
    def __init__(self, *blocks: Any) -> None:
        self._blocks = blocks

    async def blocks(self, tenant: str) -> tuple[Any, ...]:
        return self._blocks


class Runs:
    """The runs the wrong-result read looks up: only their process version matters to it."""

    def __init__(self, **versions: str) -> None:
        self._versions = versions

    async def get(self, tenant: str, run_id: str) -> Any:
        version = self._versions.get(run_id)
        return None if version is None else SimpleNamespace(process_version=version)


class World:
    def __init__(self) -> None:
        self.clock = FakeClock(AT)
        self.persistence = MemoryPersistence()
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.provenance = MemoryProvenanceStore(self.persistence)
        self.pools = Pools(
            StaticWorkerPool([("worker.fake", FakeWorker())]),
            StaticConnectorPool([("connector.fake", FakeConnector())]),
            StaticModelPool(
                [
                    ("model.first", ["reasoning"], FakeModel(answer="a"), "first@1"),
                    ("model.second", ["reasoning"], FakeModel(answer="b"), "second@1"),
                    ("model.third", ["summary"], FakeModel(answer="c"), "third@1"),
                ],
                {"model.first": Declared(location="eu"), "model.third": Declared()},
            ),
        )
        maturities = MemoryRepository(self.persistence, AdapterMaturity)
        self.versions = MemoryRepository(self.persistence, ProcessVersion)
        self.processes = MemoryRepository(self.persistence, Process)
        self.stops = Held()
        self.identity = directory((TENANT,), persistence=self.persistence, clock=self.clock)
        self.residency = TenantResidency(
            MemoryRepository(self.persistence, ResidencyRule),
            self.ledger,
            self.persistence,
            self.clock,
        )
        self.reads = ActingReads(
            processes=self.processes,
            versions=self.versions,
            maturities=maturities,
            runs=Runs(**{"bill-1": "billing@1", "remind-1": "support@1"}),  # type: ignore[arg-type]
            catalogue=InstanceCatalogue(
                self.pools, CatalogMaturities(maturities, self.persistence, self.pools)
            ),
            pools=self.pools,
            residency=self.residency,
            stops=self.stops,  # type: ignore[arg-type]
            blocked=NoBlocks(),  # type: ignore[arg-type]
            identities=self.identity.directory,
            provenance=self.provenance,
            ledger=self.ledger,
            work=self.persistence,
            clock=self.clock,
        )

    async def registered(self) -> World:
        register = RegisterProcessVersionHandler(
            self.versions, self.persistence, self.processes, ledger=self.ledger, clock=self.clock
        )
        for given in (BILLING, SUPPORT):
            await register.execute(RegisterProcessVersion(bundle=given, tenant=TENANT, by="idn_a"))
        return self


EVERYTHING = frozenset({"billing", "support"})


async def test_the_register_lists_every_adapter_with_the_steps_it_acts_in() -> None:
    world = await World().registered()
    register = await world.reads.register(TENANT, EVERYTHING)
    by = {r.adapter: r for r in register.rows}
    assert set(by) == {
        "worker.fake",
        "connector.fake",
        "model.first",
        "model.second",
        "model.third",
    }
    fetch = by["connector.fake"]
    assert [(u.process_id, u.step_id, u.without) for u in fetch.uses] == [
        ("billing", "fetch", "breaks")
    ]
    assert "without it 1 process would break: billing" in fetch.attention
    third = by["model.third"]
    (draft,) = third.uses
    assert draft.without == "degrades" and draft.role == "support-lead"
    assert by["model.first"].uses[0].instead == "model.second"
    assert by["model.second"].uses == (), "it serves nothing while model.first is first"
    assert by["model.first"].location == "eu" and by["model.third"].location == "elsewhere"
    assert register.rows[-1].attention == (), "what needs no attention comes last"


async def test_a_process_the_reader_may_not_see_is_left_out_of_every_row() -> None:
    world = await World().registered()
    register = await world.reads.register(TENANT, frozenset({"support"}))
    assert all("billing" not in r.processes for r in register.rows)


async def test_the_stop_is_requested_by_the_person_through_the_adapter_stop() -> None:
    world = await World().registered()
    await world.reads.stop(TENANT, "connector.fake", "idn_a")
    assert world.stops.requested == [("connector.fake", "idn_a")]
    by = {r.adapter: r for r in (await world.reads.register(TENANT, EVERYTHING)).rows}
    assert by["connector.fake"].stopped


async def test_removing_an_adapter_reads_the_configuration_as_it_is_now() -> None:
    world = await World().registered()
    view = await world.reads.remove(TENANT, "connector.fake", EVERYTHING)
    assert [u.step_id for u in view.breaks] == ["fetch"]
    first = await world.reads.remove(TENANT, "model.first", EVERYTHING)
    assert [u.instead for u in first.degrades] == ["model.second"]


async def test_residency_is_held_against_the_tenant_s_rule() -> None:
    world = await World().registered()
    view = await world.reads.residency(TENANT, EVERYTHING)
    assert view.permitted == "anywhere"
    assert {r.adapter: r.residency for r in view.rows}["model.first"] == "inside"


def record(id: str, run: str, step: str, seq: int, pv: str, *reads: tuple[str, str]) -> Provenance:
    return Provenance.model_validate(
        {
            "id": id,
            "run_id": run,
            "step_id": step,
            "process_version": pv,
            "method": "rule",
            "exactness": "sourced",
            "inputs": [
                {
                    "kind": "result",
                    "run_id": r,
                    "step_id": s,
                    "digest": "sha256:" + "a" * 64,
                    "observed_at": AT,
                }
                for r, s in reads
            ],
            "outputs": [],
            "result_digest": "sha256:" + "b" * 64,
            "ledger_seq": seq,
            "recorded_at": AT,
        }
    )


async def test_a_wrong_result_is_followed_forward_across_processes_to_what_left() -> None:
    world = await World().registered()
    async with world.persistence.transaction(TENANT):
        await world.provenance.append(TENANT, record("p0", "bill-1", "fetch", 1, "billing@1"))
        await world.provenance.append(
            TENANT, record("p1", "remind-1", "answer", 2, "support@1", ("bill-1", "fetch"))
        )
    async with world.persistence.transaction(TENANT):
        await world.ledger.record(
            TENANT,
            Fact(
                kind="egress.write",
                refs=LedgerRefs(tenant=TENANT, run_id="remind-1", step_id="answer"),
            ),
        )
    view = await world.reads.wrong_result(TENANT, "bill-1", "fetch", EVERYTHING)
    assert view is not None
    assert [(r.run_id, r.left) for r in view.reached] == [("remind-1", ("egress.write",))]
    assert view.left == 1 and view.built_on == {"support@1": 1}
    hidden = await world.reads.wrong_result(TENANT, "bill-1", "fetch", frozenset({"support"}))
    assert hidden is None, "a run the reader may not see is answered as none"


async def test_variants_read_the_projection_and_the_active_version() -> None:
    world = await World().registered()
    for kind, outcome in (("step.awaiting", "fell_back"), ("run.finished", None)):
        async with world.persistence.transaction(TENANT):
            await world.ledger.record(
                TENANT,
                Fact(
                    kind=kind,
                    refs=LedgerRefs(
                        tenant=TENANT,
                        run_id="bill-1",
                        step_id="draft" if kind == "step.awaiting" else None,
                        process_version="billing@1",
                    ),
                    outcome=outcome,
                ),
            )
    view = await world.reads.variants(TENANT, "billing")
    assert view is not None
    assert view.designed == ("fetch", "draft") and view.runs == 1
    assert view.variants[0].path == ("fell_back@draft",)
    assert await world.reads.variants(TENANT, "nothing") is None
