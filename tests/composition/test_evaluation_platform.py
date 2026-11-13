"""An evaluation platform connected by capability, each capability on only where configured:
a scored evaluation copied, a process version's prompts mirrored, a run's cost reconciled
(UC-5.8, ADR-0305).

The platform is the fake of its public API (`tests/fakes/evaluation_platform_service.py`), in a
thread of this process; its connector is served in-process over MCP, as an instance reaches it.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Collection, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from adapters.persistence.samples import process_version
from adapters.persistence.samples import run as a_run
from fakes import FakeClock
from fakes import evaluation_platform_service as service
from taktus_connectors.langfuse import declaration
from taktus_connectors.langfuse.operations import Config
from taktus_connectors.langfuse.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence
from taktus.adapters.driven.telemetry.masking import MaskingPolicy
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.domain.model import Evaluation, EvaluationCase
from taktus.components.process.domain.model.evaluation import (
    CaseResult,
    Purpose,
    Score,
    Side,
    Verdict,
)
from taktus.components.run.domain.model import Run
from taktus.composition.evaluation_platform import (
    COSTS,
    DIFFERED,
    EVALUATIONS,
    PROMPTS,
    RECONCILED,
    EvaluationPlatform,
)
from taktus.ports.connector import Capabilities, ResolvedConnector
from taktus.ports.ledger import Fact
from taktus.shared.v1 import Consumption, ExactnessClass, LedgerRefs, Method

T = "acme"
AT = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
PAIR = f"pk-{secrets.token_hex(6)}:sk-{secrets.token_hex(12)}"
TRACE = "0af7651916cd43dd8448eb211c80319c"


@pytest.fixture
def platform_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    server = service.make_server("127.0.0.1", 0, {PAIR})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    path = tmp_path / "pair"
    path.write_text(PAIR, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_EVALUATION_PLATFORM_KEYS_FILE", str(path))
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@dataclass
class Pool:
    """The connector pool: the platform's connector for the capabilities switched on."""

    connector: McpActionConnector
    on: Collection[str]

    async def resolve(self, capability: str) -> ResolvedConnector | None:
        if capability not in self.on:
            return None
        return ResolvedConnector(
            adapter="evaluation-platform",
            connector=self.connector,
            declaration=Capabilities.model_validate(declaration.capabilities()),
        )


@dataclass
class World:
    platform: EvaluationPlatform
    ledger: ChainedLedger
    persistence: MemoryPersistence
    url: str

    async def kinds(self) -> list[tuple[str, str | None]]:
        async with self.persistence.transaction(T):
            return [(e.kind, e.outcome) for e in await self.ledger.entries(T)]

    def state(self) -> dict[str, object]:
        found: dict[str, object] = httpx.get(f"{self.url}/_fake/state").json()
        return found


def world(url: str, on: Collection[str] = (EVALUATIONS, PROMPTS, COSTS)) -> World:
    persistence = MemoryPersistence()
    ledger = ChainedLedger(MemoryLedgerStore(persistence), FakeClock(AT))
    connector = McpActionConnector(build_server(Config(url, timeout=5.0)))
    platform = EvaluationPlatform(
        Pool(connector, on),
        ledger,
        persistence,
        masking=MaskingPolicy(kinds=("email",)),
    )
    return World(platform, ledger, persistence, url)


def scored(verdict: Verdict = Verdict.PASSED) -> Evaluation:
    def score(value: float) -> Score:
        return Score(
            scorer="draft#0",
            step="draft",
            method=Method.RULE,
            exactness=ExactnessClass.TOLERANT,
            score=value,
            how="rule",
        )

    return Evaluation(
        id="evl_1",
        tenant=T,
        process_id="answers",
        purpose=Purpose.CHANGE,
        version="answers@1",
        candidate="answers@2",
        acting_for="idn_owner",
        cases=(
            EvaluationCase(
                id="refund", inputs={"text": "Refund for ada@example.org"}, targets={"draft": "ok"}
            ),
        ),
        results=(
            CaseResult(
                case="refund", side=Side.ACTIVE, run_id="run_a", score=0.8, scores=(score(0.8),)
            ),
            CaseResult(
                case="refund", side=Side.PROPOSED, run_id="run_b", score=0.9, scores=(score(0.9),)
            ),
        ),
        verdict=verdict,
        started_at=AT,
    )


async def test_a_scored_evaluation_is_copied_and_stays_whole_in_taktus(platform_url: str) -> None:
    given = world(platform_url)
    evaluation = scored()
    assert await given.platform.copy(T, evaluation) is True
    state = given.state()
    assert (state["datasets"], state["items"], state["run_items"], state["scores"]) == (1, 1, 2, 2)
    assert evaluation.verdict is Verdict.PASSED, "the copy changes nothing in the evaluation"
    assert ("platform.evaluation.copied", "copied") in await given.kinds()

    again = await given.platform.copy(T, evaluation)
    assert again is True and given.state()["scores"] == 2, "a repeat writes nothing"


async def test_personal_content_leaves_masked_by_the_policy(platform_url: str) -> None:
    given = world(platform_url)
    await given.platform.copy(T, scored())
    async with httpx.AsyncClient() as client:
        (item,) = (await client.get(f"{platform_url}/_fake/items")).json()["items"]
    assert item["input"] == {"text": "Refund for [masked]"}, "masked before it left"


async def seeded(url: str, trace: str, cost: float) -> None:
    """A trace the platform received over OpenTelemetry, with the cost it computed."""
    async with httpx.AsyncClient() as client:
        await client.post(f"{url}/_fake/traces", json={"id": trace, "totalCost": cost})


async def test_the_platform_s_scores_stand_beside_the_verdict_and_never_replace_it(
    platform_url: str,
) -> None:
    given = world(platform_url)
    evaluation = scored(Verdict.REGRESSED)
    for run in ("run_a", "run_b"):
        await seeded(platform_url, run, 0.01)
    await given.platform.copy(T, evaluation)
    read = await given.platform.scores(T, evaluation)
    assert read is not None and read.verdict == "regressed", "Taktus's verdict, unchanged"
    assert read.cases["run_b"] == {"proposed-draft-0": 0.9}


async def test_the_prompt_of_a_model_step_is_mirrored_once_per_version(platform_url: str) -> None:
    given = world(platform_url)
    version = process_version()
    llm = version.steps[0].model_copy(update={"method": Method.LLM})
    version = version.model_copy(
        update={
            "steps": (llm, *version.steps[1:]),
            "work": {**version.work, llm.id: {"purpose": "drafting", "prompt": "Draft it."}},
        }
    )
    first = await given.platform.mirror(T, version)
    assert first == {llm.id: 1}
    assert await given.platform.mirror(T, version) == {llm.id: 1}, "the repeat finds its mark"
    assert given.state()["prompts"] == {f"{version.process_id}.{llm.id}": 1}


def spent(run: Run, usd: float) -> Run:
    first = run.step_runs[0].model_copy(update={"consumption": Consumption(currency={"usd": usd})})
    return run.model_copy(update={"step_runs": (first, *run.step_runs[1:])})


async def traced(given: World, run: Run) -> None:
    async with given.persistence.transaction(T):
        await given.ledger.record(
            T,
            Fact(
                kind="run.created",
                refs=LedgerRefs(tenant=T, run_id=run.id, trace_id=TRACE),
                outcome="created",
            ),
        )


async def test_a_cost_that_differs_is_reported_and_taktus_keeps_its_own(platform_url: str) -> None:
    given = world(platform_url)
    await seeded(platform_url, TRACE, 0.5)
    run = spent(a_run("run_cost", T), 0.02)
    await traced(given, run)
    reconciled = await given.platform.reconcile(T, run)
    assert reconciled is not None and reconciled.differs
    assert str(reconciled.platform) == "0.5" and reconciled.own is not None
    kinds = await given.kinds()
    assert (RECONCILED, "differs") in kinds and (DIFFERED, "differs") in kinds
    assert run.consumed().currency == {"usd": 0.02}, "Taktus keeps its own figure"

    await seeded(platform_url, TRACE, 0.02)
    agreeing = await given.platform.reconcile(T, run)
    assert agreeing is not None and not agreeing.differs


async def test_each_capability_is_switched_on_and_off_on_its_own(platform_url: str) -> None:
    given = world(platform_url, on=(COSTS,))
    await seeded(platform_url, TRACE, 0.02)
    before = given.state()["requests"]
    assert await given.platform.copy(T, scored()) is False
    assert await given.platform.mirror(T, process_version()) == {}
    assert given.state()["requests"] == before, "nothing is called for what is off"
    run = spent(a_run("run_cost", T), 0.02)
    await traced(given, run)
    assert await given.platform.reconcile(T, run) is not None

    off = world(platform_url, on=())
    assert await off.platform.reconcile(T, run) is None
    assert await off.kinds() == []


async def test_a_platform_that_is_gone_changes_nothing() -> None:
    given = world("http://127.0.0.1:9")  # nothing listens there
    evaluation = scored()
    assert await given.platform.copy(T, evaluation) is False
    assert evaluation.verdict is Verdict.PASSED
    assert await given.kinds() == [("platform.evaluation.copied", "failed")]
