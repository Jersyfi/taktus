# ruff: noqa: F811 — every test requests the imported fixture `outside` by its name
"""The store reviews process of the blueprint `software-operations`, registered as shipped and
run against fakes of the systems behind its capabilities (UC-03 §4.3, B-3.09; ADR-0207).

The world of `test_software_operations.py`, with the engine wired to the repository service and
to the app stores connector over either store's fake, served in-process over MCP as the daemon
reaches them, and to the tenant's message rules. What is faked: the repository service, each
store's API, the model and the owner's chat. The process runs unchanged on both stores: one
capability, one connector, the store named by the run's `platform`.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import FakeIdentifiers, FakeWorker
from fakes import customer_reviews_service as first_store
from fakes import review_replies_service as second_store
from fakes.maturity import VERIFIED
from fakes.ports import free_port
from taktus_connectors.appstores.operations import Config as StoresConfig
from taktus_connectors.appstores.server import build_server as stores_server
from taktus_connectors.github.server import Config as RepositoryConfig
from taktus_connectors.github.server import build_server as repository_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import MemoryQueue
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.run.application.service import EngineOptions, RunEngine
from taktus.components.run.domain.model import Run, RunState, StepState

from .test_software_operations import (
    CHECK,
    CLASSIFY,
    REPOSITORY,
    Outside,
    World,
    outside,  # noqa: F401 — the fixture, requested by name
    states,
)

TIE = "You tie a customer's review"
DRAFT = "You draft a public reply"
CREDENTIAL = "STORES_KEY"


@dataclass(frozen=True)
class Store:
    module: Any
    platform: str
    credential: Callable[[str], str]
    """The store's key as `STORES_KEY`, given the fake's address."""
    app: str
    unanswered: str
    """A review of one star without a response."""
    answered: str
    """A review of five stars with a response."""


STORES = {
    "first": Store(
        first_store,
        "ios",
        lambda url: first_store.credential(),
        first_store.APP,
        "rev-1",
        "rev-3",
    ),
    "second": Store(
        second_store,
        "android",
        lambda url: second_store.credential(f"{url}/token"),
        second_store.PACKAGE,
        "gp:1",
        "gp:3",
    ),
}


@dataclass
class Running:
    spec: Store
    url: str

    def written(self) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = httpx.get(f"{self.url}/_fake/state", timeout=5).json()[
            "written"
        ]
        return found


@pytest.fixture(params=sorted(STORES))
def store(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Running]:
    spec = STORES[request.param]
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    value = spec.credential(url)
    path = tmp_path / CREDENTIAL
    path.write_text(value, encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(path))
    server = spec.module.make_server("127.0.0.1", port, {value})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield Running(spec, url)
    server.shutdown()
    server.server_close()


class StoresWorld(World):
    """The world, with the repository service and one store's reviews connector."""

    def __init__(self, outside: Outside, store: Running) -> None:
        super().__init__(outside)
        self.store = store

        def served(server: Any) -> McpActionConnector:
            return McpActionConnector(server, timeout=10.0)

        connectors = [
            (
                "connector.repository",
                served(
                    repository_server(RepositoryConfig(outside.repository, REPOSITORY, timeout=5.0))
                ),
            ),
            (
                "connector.stores",
                served(stores_server(StoresConfig(store.url, store.url, timeout=5.0))),
            ),
        ]
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.of(Run),
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=self.provenance,
            workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
            clock=self.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            queue=MemoryQueue(self.persistence, self.clock),
            options=EngineOptions(uncalibrated_margin=0.0),
            connectors=StaticConnectorPool(connectors),
            models=StaticModelPool(
                [("model.fake", ["triage", "support", "check"], self.model, "fake-model@1")]
            ),
            messages=self.told,
        )

    async def ready(self) -> StoresWorld:
        await super().ready()
        return self


def answering(
    w: World, tie: str, draft: str, check: str = "send", classified: str = "none"
) -> None:
    w.model.answers.update({TIE: tie, DRAFT: draft, CHECK: check, CLASSIFY: classified})


def known_defect(outside: Outside) -> int:
    opened = outside.send(
        "POST",
        f"/repos/{REPOSITORY}/issues",
        {"title": "Export crashes after the update", "body": "Since 2.1 the export stops."},
    )
    return int(opened["number"])


async def test_b_3_09_replies_to_a_low_rating_tied_to_the_open_issue_once_a_person_released_it(
    outside: Outside, store: Running
) -> None:
    w = await StoresWorld(outside, store).ready()
    version = await w.registered("B-3.09-store-reviews.yaml")
    number = known_defect(outside)
    answering(w, f"issue: {number}", "Thank you for telling us. We know the export issue.")
    run = await w.start(
        version, platform=store.spec.platform, app=store.spec.app, review=store.spec.unanswered
    )
    assert run.state is RunState.WAITING_HUMAN, "a public reply waits for a person"
    assert store.written() == []
    run = await w.confirmed(run)
    assert run.state is RunState.FINISHED, "\n".join(
        f"{s.step_id} {s.state} {s.reason}" for s in run.step_runs
    )
    known = await w.result(run, "known")
    assert known["matched"] == 1 and known["left_only"] == [], "the named issue is open"
    [written] = store.written()
    assert written["review"] == store.spec.unanswered
    assert written["text"].startswith("Thank you for telling us. We know the export issue.")
    assert w.told.label is not None and w.told.label in written["text"], "labelled as AI-written"
    systems = [p.system or "" for p in w.model.prompts]
    assert any(s.startswith(CHECK) for s in systems), "the independent check was asked"
    assert all("follow no instruction" in s for s in systems)
    # Patterns across releases (ADR-0309): the low ratings counted per app version.
    low = (await w.result(run, "read-low"))["output"]["reviews"]
    assert low and all(r["rating"] <= 2 for r in low)
    counted = await w.result(run, "by-release")
    assert counted["items"] == len(low) == sum(g["count"] for g in counted["groups"])
    versions = {r.get("version") for r in low}
    assert {g["value"] for g in counted["groups"]} == versions
    counts = [g["count"] for g in counted["groups"]]
    assert counts == sorted(counts, reverse=True), "most first"


async def test_b_3_09_a_number_no_open_issue_carries_ties_nothing(
    outside: Outside, store: Running
) -> None:
    w = await StoresWorld(outside, store).ready()
    version = await w.registered("B-3.09-store-reviews.yaml")
    known_defect(outside)
    answering(w, "issue: 999999", "Thank you, we are looking into it.")
    run = await w.confirmed(
        await w.start(
            version, platform=store.spec.platform, app=store.spec.app, review=store.spec.unanswered
        )
    )
    assert run.state is RunState.FINISHED, "\n".join(
        f"{s.step_id} {s.state} {s.reason}" for s in run.step_runs
    )
    known = await w.result(run, "known")
    assert known["matched"] == 0 and known["left_only"] == [{"number": "999999"}]


async def test_b_3_09_an_answered_or_good_review_runs_nothing_further(
    outside: Outside, store: Running
) -> None:
    w = await StoresWorld(outside, store).ready()
    version = await w.registered("B-3.09-store-reviews.yaml")
    answering(w, "issue: none", "Thanks!")
    run = await w.confirmed(
        await w.start(
            version, platform=store.spec.platform, app=store.spec.app, review=store.spec.answered
        )
    )
    assert run.state is RunState.FINISHED, "\n".join(
        f"{s.step_id} {s.state} {s.reason}" for s in run.step_runs
    )
    assert (await w.result(run, "unanswered"))["count"] == 0
    assert (await w.result(run, "send"))["skipped"] is True
    assert w.model.prompts == [], "no model was asked"
    assert store.written() == []


@pytest.mark.parametrize(
    ("draft", "check", "classified", "held_by"),
    [
        ("Sorry about that, we will refund your purchase.", "send", "none", "no_money"),
        ("Thank you! " + "We are on it. " * 30, "send", "none", "short"),
        ("Thank you, we are looking into it.", "reject", "none", "verify answered reject"),
        ("The fix ships on Friday.", "send", "date", "anc-promise"),
    ],
)
async def test_b_3_09_money_length_a_rejection_or_a_promise_holds_the_reply(
    outside: Outside, store: Running, draft: str, check: str, classified: str, held_by: str
) -> None:
    w = await StoresWorld(outside, store).ready()
    version = await w.registered("B-3.09-store-reviews.yaml")
    answering(w, "issue: none", draft, check, classified)
    run = await w.confirmed(
        await w.start(
            version, platform=store.spec.platform, app=store.spec.app, review=store.spec.unanswered
        )
    )
    assert states(run)["send"] is not StepState.SUCCEEDED
    assert run.state is not RunState.FINISHED
    assert held_by in (run.step_run("send").reason or "")
    assert store.written() == []
