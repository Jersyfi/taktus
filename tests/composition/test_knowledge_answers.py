"""K-01 Answer from knowledge, registered as shipped and run against the wiki connector over the
fake of the wiki (UC-5.5 §2, ADR-0265).

What is proven, bullet by bullet of UC-5.5 §2:

- every statement of the answer names the source it came from, with the link the source gives;
  each step whose result rests on knowledge is `sourced` and declares its check; and an answer
  with a statement that names no document the asker read does not leave the step;
- two identities whose rights in the wiki differ ask the same question, and each gets only what
  the wiki shows them: the search runs with each one's own token, and an identity without one
  gets nothing from the source;
- the index keeps references and digests of what was read, never the text; a document changed
  or removed while the answer was written is reflected in the index, and the answer says so
  beside the source.

The removal test of the source is `tests/integration/test_knowledge_removal.py`. What is faked:
the wiki and the model.
"""

from __future__ import annotations

import json
import re
import secrets
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from fakes import FakeClock, FakeIdentifiers, wiki_service
from fakes.maturity import VERIFIED
from fakes.model import FakeModel
from taktus_connectors.bookstack.server import Config, build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.knowledge.domain.model import KnowledgeEntry
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.run.application.service import EngineOptions, RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.composition.knowledge import IndexedCitations
from taktus.composition.personal import ConfiguredPersonalCredentials
from taktus.ports.model import Completion, Prompt
from taktus.ports.worker import Limits
from taktus.shared.v1 import Commissioned, Plan, PlanResult, PlanStatus, PriceKinds

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "blueprints" / "knowledge" / "processes" / "K-01-answer-from-knowledge.yaml"
TENANT = "default"
ADA, BOB, CAROL = "person:ada", "person:bob", "person:carol"
QUESTION = "How many days of holiday do I have?"
TERMS = "You turn a question"
ANSWER = "You answer a question"
CITED = re.compile(r'document\\?"\s*:\s*\\?"(\d+)')


def bundle() -> dict[str, Any]:
    found: dict[str, Any] = yaml.safe_load(BUNDLE.read_text(encoding="utf-8"))
    return found


@dataclass
class Wiki:
    url: str
    tokens: dict[str, str]
    """Identity -> the value of its own token."""

    def post(self, path: str, body: dict[str, Any]) -> None:
        httpx.post(f"{self.url}/_fake/{path}", json=body, timeout=5).raise_for_status()

    def pages(self) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = httpx.get(f"{self.url}/_fake/pages", timeout=5).json()[
            "pages"
        ]
        return found

    def page_id(self, name: str) -> int:
        return int(next(p for p in self.pages() if p["name"] == name)["id"])

    def requests(self) -> int:
        return int(httpx.get(f"{self.url}/_fake/state", timeout=5).json()["requests"])


@pytest.fixture
def wiki(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Wiki]:
    """The wiki with a page on holidays in the book only Ada may view, and one in the book
    both may; each person's own token in a file its variable names (ADR-0264)."""
    tokens = {who: f"{secrets.token_hex(6)}:{secrets.token_hex(12)}" for who in (ADA, BOB)}
    server = wiki_service.make_server(
        "127.0.0.1",
        0,
        {value: "read" for value in tokens.values()},
        {tokens[BOB]: {"Using Taktus"}},
    )
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    for who, value in tokens.items():
        name = f"KNOWLEDGE_TOKEN_{who.split(':')[1].upper()}"
        path = tmp_path / name
        path.write_text(value, encoding="utf-8")
        monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{name}_FILE", str(path))
    found = Wiki(f"http://127.0.0.1:{server.server_address[1]}", tokens)
    found.post(
        "pages",
        {"book": "Administration", "name": "Holidays", "markdown": "Holidays: 30 days a year."},
    )
    found.post(
        "pages",
        {
            "book": "Using Taktus",
            "name": "Leave",
            "markdown": "Holidays are asked for in the portal.",
        },
    )
    yield found
    server.shutdown()
    server.server_close()


@dataclass
class Reader(FakeModel):
    """A model that searches for `holidays` and answers one statement per document it was
    given, citing it; `answering` runs while it answers, as a person editing the wiki would."""

    said: Callable[[list[str]], dict[str, Any]] | None = None
    answering: Callable[[], None] | None = None
    seen: list[str] = field(default_factory=list)

    async def complete(self, prompt: Prompt) -> Completion:
        self.prompts.append(prompt)
        system = prompt.system or ""
        if system.startswith(TERMS):
            text = "holidays"
        else:
            assert system.startswith(ANSWER), system
            self.seen.append(str(prompt))
            documents = list(dict.fromkeys(CITED.findall(str(prompt))))
            if self.answering is not None:
                self.answering()
            said = (
                self.said(documents)
                if self.said is not None
                else {
                    "statements": [
                        {"text": f"Document {d} says how holidays are taken.", "sources": [d]}
                        for d in documents
                    ]
                }
            )
            text = json.dumps(said)
        return Completion(
            text=text,
            model=self.name,
            tokens_in=10,
            tokens_out=10,
            by_kind=PriceKinds(input=10, output=10),
            finish="stop",
        )


class World:
    def __init__(self, wiki: Wiki | None, model: Reader | None = None) -> None:
        self.clock, self.ids = FakeClock(), FakeIdentifiers()
        self.persistence = MemoryPersistence()
        self.objects = MemoryObjectStore()
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.model = model or Reader()
        self.entries = MemoryRepository(self.persistence, KnowledgeEntry)
        self.versions = MemoryRepository(self.persistence, ProcessVersion)
        connectors = (
            []
            if wiki is None
            else [
                (
                    "connector.knowledge",
                    McpActionConnector(
                        build_server(Config(target=wiki.url, timeout=5.0)), timeout=10.0
                    ),
                )
            ]
        )
        self.engine = RunEngine(
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
            connectors=StaticConnectorPool(connectors),
            models=StaticModelPool(
                [("model.fake", ["triage", "support"], self.model, "fake-model@1")]
            ),
            personal=ConfiguredPersonalCredentials(
                {
                    (ADA, "KNOWLEDGE_TOKEN"): "KNOWLEDGE_TOKEN_ADA",
                    (BOB, "KNOWLEDGE_TOKEN"): "KNOWLEDGE_TOKEN_BOB",
                }
            ),
            citations=IndexedCitations(self.entries, self.persistence),
        )
        self.register = RegisterProcessVersionHandler(
            self.versions, self.persistence, ledger=self.ledger
        )

    async def ask(self, who: str, question: str = QUESTION) -> Run:
        version = await self.register.execute(RegisterProcessVersion(bundle(), tenant=TENANT))
        plan = Plan(
            id=f"pln_{secrets.token_hex(4)}",
            command_id="cmd_1",
            goal=version.name,
            autonomy_level=version.autonomy_level,
            steps=version.ordered(),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=who, at=self.clock.now()),
        )
        return await self.engine.start(
            StartRun(
                plan=plan,
                work=version.work,
                budget=Limits.model_validate(dict(version.limits or {})),
                process_version=version.ref,
                actor=who,
                tenant=TENANT,
                inputs={"question": question},
            )
        )

    async def result(self, run: Run, step: str) -> Any:
        checkpoint = run.step_run(step).checkpoint
        assert checkpoint is not None and checkpoint.result_digest is not None
        return json.loads(await self.objects.get(checkpoint.result_digest) or b"null")

    async def index(self) -> list[KnowledgeEntry]:
        async with self.persistence.transaction(TENANT):
            return list(await self.entries.list(TENANT))


def states(run: Run) -> dict[str, StepState]:
    return {s.step_id: s.state for s in run.step_runs}


def why(run: Run) -> list[tuple[str, str | None]]:
    return [(s.step_id, s.reason) for s in run.step_runs]


# --- every statement names its source, and the step is sourced ----------------------------------


def test_every_step_that_rests_on_knowledge_is_sourced_and_declares_its_check() -> None:
    steps = {s["id"]: s for s in bundle()["steps"]}
    for name in ("search", "answer", "confirm", "cite"):
        assert steps[name]["exactness"] == "sourced", name
        assert steps[name]["checks"], name
    assert steps["search"]["work"]["on_behalf"] is True
    assert steps["confirm"]["work"]["on_behalf"] is True
    assert steps["cite"]["work"]["rule"] == "citation"


async def test_k_01_answers_with_every_statement_naming_its_source_and_its_link(
    wiki: Wiki,
) -> None:
    w = World(wiki)
    run = await w.ask(ADA)
    assert run.state is RunState.FINISHED, why(run)
    cited = await w.result(run, "cite")
    holidays, leave = wiki.page_id("Holidays"), wiki.page_id("Leave")
    assert [s["document"] for s in cited["sources"]] == [str(holidays), str(leave)]
    assert [s["url"] for s in cited["sources"]] == [
        f"{wiki.url}/books/administration/page/holidays",
        f"{wiki.url}/books/using-taktus/page/leave",
    ]
    assert all(s["standing"] == "current" for s in cited["sources"])
    assert cited["statements"] == [
        {"text": f"Document {holidays} says how holidays are taken.", "sources": [1]},
        {"text": f"Document {leave} says how holidays are taken.", "sources": [2]},
    ]
    assert (
        f"[1] [Holidays]({wiki.url}/books/administration/page/holidays), version 1"
        in (cited["answer"])
    )


async def test_an_answer_naming_a_document_the_asker_did_not_read_does_not_leave(
    wiki: Wiki,
) -> None:
    model = Reader(
        said=lambda _: {"statements": [{"text": "Everyone has 40 days.", "sources": ["999"]}]}
    )
    w = World(wiki, model)
    run = await w.ask(ADA)
    assert run.state is RunState.ESCALATED, "a person takes over (the step's fallback)"
    cite = run.step_run("cite")
    assert cite.state is not StepState.SUCCEEDED
    assert "names the document '999', which the search did not read" in (cite.reason or "")
    assert cite.checkpoint is None or cite.checkpoint.result_digest is None


async def test_an_answer_whose_statements_name_no_source_fails_its_check(wiki: Wiki) -> None:
    model = Reader(
        said=lambda _: {"statements": [{"text": "Everyone has 40 days.", "sources": []}]}
    )
    w = World(wiki, model)
    run = await w.ask(ADA)
    assert run.state is RunState.ESCALATED, "a person takes over (the step's fallback)"
    assert states(run)["answer"] is not StepState.SUCCEEDED, why(run)
    assert states(run).get("cite") is not StepState.SUCCEEDED


# --- the rights of the source hold ----------------------------------------------------------------


async def test_two_identities_asking_the_same_get_only_what_the_wiki_shows_each(
    wiki: Wiki,
) -> None:
    w = World(wiki)
    ada = await w.ask(ADA)
    bob = await w.ask(BOB)
    assert ada.state is RunState.FINISHED and bob.state is RunState.FINISHED, why(bob)
    ada_cited, bob_cited = await w.result(ada, "cite"), await w.result(bob, "cite")
    assert [s["title"] for s in ada_cited["sources"]] == ["Holidays", "Leave"]
    assert [s["title"] for s in bob_cited["sources"]] == ["Leave"]
    bob_read = await w.result(bob, "search")
    assert "30 days" not in json.dumps(bob_read), "nothing of what Bob may not view was read"
    assert "30 days" in w.model.seen[0] and "30 days" not in w.model.seen[1], (
        "the model answering Bob never saw it either"
    )


async def test_an_identity_without_an_own_credential_gets_nothing_from_the_source(
    wiki: Wiki,
) -> None:
    w = World(wiki)
    before = wiki.requests()
    run = await w.ask(CAROL)
    search = run.step_run("search")
    assert search.state is not StepState.SUCCEEDED
    assert f"{CAROL} has no credential of its own" in (search.reason or "")
    assert wiki.requests() == before, "no request reached the wiki"
    assert run.state is RunState.ESCALATED, "a person takes over (the step's fallback)"


# --- the index: references and digests, changed and removed ---------------------------------------


async def test_the_index_keeps_references_and_digests_never_the_text(wiki: Wiki) -> None:
    w = World(wiki)
    run = await w.ask(ADA)
    assert run.state is RunState.FINISHED, why(run)
    entries = await w.index()
    assert sorted(e.title for e in entries) == ["Holidays", "Leave"]
    assert all(
        e.held and e.version == "1" and e.capability == "knowledge.documents" for e in entries
    )
    stored = json.dumps([e.document() for e in entries])
    assert "30 days" not in stored and "portal" not in stored


async def test_a_document_changed_while_the_answer_was_written_is_said_and_indexed(
    wiki: Wiki,
) -> None:
    model = Reader()
    model.answering = lambda: wiki.post(
        "edit", {"id": wiki.page_id("Holidays"), "markdown": "Holidays: 28 days a year."}
    )
    w = World(wiki, model)
    run = await w.ask(ADA)
    assert run.state is RunState.FINISHED, why(run)
    cited = await w.result(run, "cite")
    holidays = next(s for s in cited["sources"] if s["title"] == "Holidays")
    assert holidays["standing"] == "changed"
    assert holidays["version"] == "1", "the version the statement rests on"
    assert "the source now holds version 2; this answer rests on version 1" in holidays["note"]
    assert "— changed: the source now holds version 2" in cited["answer"]
    entry = next(e for e in await w.index() if e.title == "Holidays")
    assert entry.version == "2" and [o.version for o in entry.earlier] == ["1"]


async def test_a_document_removed_while_the_answer_was_written_is_said_and_indexed(
    wiki: Wiki,
) -> None:
    model = Reader()
    model.answering = lambda: wiki.post("delete", {"id": wiki.page_id("Leave")})
    w = World(wiki, model)
    run = await w.ask(ADA)
    assert run.state is RunState.FINISHED, why(run)
    cited = await w.result(run, "cite")
    leave = next(s for s in cited["sources"] if s["title"] == "Leave")
    assert leave["standing"] == "removed"
    assert "— removed: the source no longer shows this document" in cited["answer"]
    entry = next(e for e in await w.index() if e.title == "Leave")
    assert not entry.held and entry.version == "1"


async def test_a_search_that_finds_nothing_answers_nothing(wiki: Wiki) -> None:
    model = Reader()
    w = World(wiki, model)
    wiki.post("views", {"token": wiki.tokens[BOB], "books": []})
    run = await w.ask(BOB)
    assert run.state is RunState.FINISHED, why(run)
    assert (await w.result(run, "search"))["output"]["documents"] == []
    assert not model.seen, "no model was asked to answer from nothing"
    assert await w.index() == []
