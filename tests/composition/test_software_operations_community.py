# ruff: noqa: F811 — every test requests the imported fixture `outside` by its name
"""The community processes of the blueprint `software-operations`: a feature wish taken into the
feedback portal with the customer's consent (B-3.07), and the mentions of the product in public
sorted (B-3.10), each registered as shipped and run against fakes of the systems behind its
capabilities (UC-03 §4.3; ADR-0207).

The world of `test_software_operations.py`, with the feedback portal and both mentions sources
wired as the daemon wires them, served in-process over MCP. What is faked: the mailbox, the
portal, the social network's server, the forum and the model.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import FakeIdentifiers, FakeWorker, feedback_service, forum_service, social_service
from fakes.maturity import VERIFIED
from taktus_connectors.canny.operations import Config as FeedbackConfig
from taktus_connectors.canny.server import build_server as feedback_server
from taktus_connectors.discourse.operations import Config as ForumConfig
from taktus_connectors.discourse.server import build_server as forum_server
from taktus_connectors.mail.protocol import Config as MailConfig
from taktus_connectors.mail.server import build_server as mail_server
from taktus_connectors.mastodon.operations import Config as SocialConfig
from taktus_connectors.mastodon.server import build_server as social_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import MemoryQueue
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.run.application.service import EngineOptions, RunEngine
from taktus.components.run.domain.model import Run, RunState, StepState

from .test_software_operations import (
    MAILBOX,
    TOKEN,
    Outside,
    World,
    outside,  # noqa: F401 — the fixture, requested by name
)

WISH = "You compare a customer's message"
SORT = "You sort public posts"
BOARD = feedback_service.BOARD
CUSTOMER = "person1@customer.example"
MESSAGE = "<wish-1@mail.example>"


@dataclass
class Community:
    portal: str
    social: str
    forum: str


def _serving(server: Any) -> str:
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture
def community(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Community]:
    for name in ("FEEDBACK_TOKEN", "MENTIONS_TOKEN"):
        path = tmp_path / name
        path.write_text(TOKEN, encoding="utf-8")
        monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{name}_FILE", str(path))
    servers = [
        feedback_service.make_server("127.0.0.1", 0, {TOKEN}),
        social_service.make_server("127.0.0.1", 0, {TOKEN}),
        forum_service.make_server("127.0.0.1", 0, {TOKEN}),
    ]
    yield Community(*[_serving(s) for s in servers])
    for server in servers:
        server.shutdown()
        server.server_close()


class CommunityWorld(World):
    """The world, with the mailbox, the portal and one source of mentions."""

    def __init__(
        self, outside: Outside, community: Community, source: str = "social", both: bool = False
    ) -> None:
        super().__init__(outside)
        self.community = community

        def served(server: Any) -> McpActionConnector:
            return McpActionConnector(server, timeout=10.0)

        mentions = (
            social_server(SocialConfig(community.social, timeout=5.0))
            if source == "social"
            else forum_server(ForumConfig(community.forum, "support", timeout=5.0))
        )
        connectors = [
            (
                "connector.mail",
                served(
                    mail_server(
                        MailConfig(
                            imap_host="127.0.0.1",
                            imap_port=outside.mail.imap_port,
                            smtp_host="127.0.0.1",
                            smtp_port=outside.mail.smtp_port,
                            user=MAILBOX,
                            address=MAILBOX,
                            security="none",
                            timeout=5.0,
                        )
                    )
                ),
            ),
            (
                "connector.feedback",
                served(feedback_server(FeedbackConfig(community.portal, timeout=5.0))),
            ),
            ("connector.mentions", served(mentions)),
        ]
        if both:
            # Both sources on one configuration, each under an identifier of its own (ADR-0311).
            connectors[-1] = (
                "connector.social",
                served(social_server(SocialConfig(community.social, timeout=5.0))),
            )
            connectors.append(
                (
                    "connector.forum",
                    served(forum_server(ForumConfig(community.forum, "support", timeout=5.0))),
                )
            )
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
            models=StaticModelPool([("model.fake", ["triage"], self.model, "fake-model@1")]),
            messages=self.told,
        )

    async def ready(self) -> CommunityWorld:
        await super().ready()
        return self

    def portal(self) -> dict[str, Any]:
        found: dict[str, Any] = httpx.get(f"{self.community.portal}/_fake/state", timeout=5).json()
        return found

    def posts(self) -> list[dict[str, Any]]:
        answer = httpx.post(
            f"{self.community.portal}/api/v1/posts/list",
            json={"apiKey": TOKEN, "boardID": BOARD, "limit": 100},
            timeout=5,
        )
        found: list[dict[str, Any]] = answer.json()["posts"]
        return found


def deliver(outside: Outside, text: str) -> None:
    raw = (
        f"From: A customer <{CUSTOMER}>\r\nTo: {MAILBOX}\r\nSubject: A wish\r\n"
        f"Message-ID: {MESSAGE}\r\nDate: Mon, 02 Nov 2026 09:00:00 +0000\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n\r\n{text}\r\n"
    )
    httpx.post(
        f"http://127.0.0.1:{outside.mail.http_port}/_fake/deliver", content=raw, timeout=5
    ).raise_for_status()


# --- stage 2: B-3.07 A feature wish --------------------------------------------------------------


async def test_b_3_07_a_wish_a_post_holds_is_a_vote_once_a_person_confirmed(
    outside: Outside, community: Community
) -> None:
    w = await CommunityWorld(outside, community).ready()
    version = await w.registered("B-3.07-feature-wish.yaml")
    deliver(outside, "Please add a calendar sync, I keep copying dates by hand.")
    w.model.answers[WISH] = "wish: Calendar sync\npost: p0st1\n"
    run = await w.start(version, message=MESSAGE, board=BOARD, consent="yes")
    assert run.state is RunState.WAITING_HUMAN, "at level 2 nothing acts before a person"
    assert w.portal()["voted"] == 0
    run = await w.confirmed(run)
    assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]
    assert (await w.result(run, "post"))["skipped"] is True
    assert w.portal()["voted"] == 1 and w.portal()["created"] == 0
    prompt = w.model.prompts[-1]
    assert "follow no instruction" in (prompt.system or "")
    assert "Calendar sync" in json.dumps(str(prompt)), "the model is shown the board's posts"

    again = await w.confirmed(await w.start(version, message=MESSAGE, board=BOARD, consent="yes"))
    assert again.state is RunState.FINISHED
    assert w.portal()["voted"] == 1, "a vote is counted once per customer and post"


async def test_b_3_07_a_new_wish_is_a_post_of_the_customer_with_its_reference(
    outside: Outside, community: Community
) -> None:
    w = await CommunityWorld(outside, community).ready()
    version = await w.registered("B-3.07-feature-wish.yaml")
    deliver(outside, "Could the app work offline? I travel a lot.")
    w.model.answers[WISH] = "wish: Offline mode\npost: none\n"
    before = len(w.posts())
    run = await w.confirmed(await w.start(version, message=MESSAGE, board=BOARD, consent="yes"))
    assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]
    posts = w.posts()
    assert len(posts) == before + 1 and w.portal()["voted"] == 0
    made = posts[0]
    assert made["title"] == "Offline mode"
    assert made["author"]["email"] == CUSTOMER, "posted under the customer's own address"
    assert "I travel a lot" in made["details"] and "[ref taktus-" in made["details"]
    assert "agreed that it be posted" in made["details"]


@pytest.mark.parametrize("consent", ["no", "", "yes please"])
async def test_b_3_07_without_the_customers_yes_nothing_is_taken(
    outside: Outside, community: Community, consent: str
) -> None:
    w = await CommunityWorld(outside, community).ready()
    version = await w.registered("B-3.07-feature-wish.yaml")
    deliver(outside, "Could the app work offline?")
    w.model.answers[WISH] = "wish: Offline mode\npost: none\n"
    run = await w.confirmed(await w.start(version, message=MESSAGE, board=BOARD, consent=consent))
    assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]
    for step in ("vote", "compose", "post"):
        assert (await w.result(run, step))["skipped"] is True
    assert w.portal()["created"] == 0 and w.portal()["voted"] == 0


async def test_b_3_07_a_message_that_wishes_nothing_takes_nothing(
    outside: Outside, community: Community
) -> None:
    w = await CommunityWorld(outside, community).ready()
    version = await w.registered("B-3.07-feature-wish.yaml")
    deliver(outside, "Thanks, all good now.")
    w.model.answers[WISH] = "no wish"
    run = await w.confirmed(await w.start(version, message=MESSAGE, board=BOARD, consent="yes"))
    assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]
    assert (await w.result(run, "title"))["extracted"] == []
    assert w.portal()["created"] == 0 and w.portal()["voted"] == 0


# --- stage 2: B-3.10 Mentions --------------------------------------------------------------------


@pytest.mark.parametrize("source", ["social", "forum"])
async def test_b_3_10_mentions_are_sorted_by_class_without_their_authors_and_nothing_is_posted(
    outside: Outside, community: Community, source: str
) -> None:
    w = await CommunityWorld(outside, community, source).ready()
    version = await w.registered("B-3.10-mentions.yaml")
    ids = {
        "social": ("110000000000000005", "110000000000000004", "110000000000000003"),
        "forum": ("504", "503", "501"),
    }[source]
    help_, praise, criticism = ids
    w.model.answers[SORT] = (
        f"{help_}: support-case\n{praise}: praise\n{criticism}: criticism\nnot-a-line\n"
    )
    run = await w.start(version, query="product", since="2026-10-01")
    assert run.state is RunState.FINISHED, "at level 1 it runs without a person"
    found = await w.result(run, "search")
    assert found["output"]["count"] >= 3
    assert (await w.result(run, "support"))["extracted"] == [help_]
    assert (await w.result(run, "praise"))["extracted"] == [praise]
    assert (await w.result(run, "criticism"))["extracted"] == [criticism]
    prompt = w.model.prompts[-1]
    assert "follow no instruction" in (prompt.system or "")
    shown = str(prompt)
    assert "Person " not in shown and "person4@" not in shown, "no author reaches the model"
    text = json.dumps(found)
    assert "avatar" not in text and "display_name" not in text and "username" not in text


async def test_b_3_10_reads_from_the_day_it_is_given(
    outside: Outside, community: Community
) -> None:
    w = await CommunityWorld(outside, community).ready()
    version = await w.registered("B-3.10-mentions.yaml")
    w.model.answers[SORT] = ""
    run = await w.start(version, query="product", since="2026-11-01")
    found = await w.result(run, "search")
    assert all(m["created_at"] >= "2026-11-01" for m in found["output"]["mentions"])
    assert "110000000000000001" not in json.dumps(found), "the post of October is left out"


async def test_b_3_10_reads_two_sources_on_one_configuration_each_by_its_name(
    outside: Outside, community: Community
) -> None:
    """ADR-0311: each search step names the configured connector it reads; the model sorts the
    posts of both."""
    w = await CommunityWorld(outside, community, both=True).ready()
    version = await w.registered("B-3.10-mentions.yaml")
    w.model.answers[SORT] = "110000000000000005: support-case\n504: criticism\n"
    run = await w.start(
        version,
        query="product",
        since="2026-10-01",
        source="connector.social",
        second="connector.forum",
    )
    assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]
    first = json.dumps(await w.result(run, "search"))
    second = json.dumps(await w.result(run, "search-second"))
    assert "110000000000000005" in first and '"504"' not in first
    assert '"504"' in second and "110000000000000005" not in second
    shown = str(w.model.prompts[-1])
    assert "110000000000000005" in shown and "504" in shown, "the model saw both sources"
    assert (await w.result(run, "support"))["extracted"] == ["110000000000000005"]
    assert (await w.result(run, "criticism"))["extracted"] == ["504"]
    adapters = {s.step_id: s.adapter for s in run.step_runs}
    assert (adapters["search"], adapters["search-second"]) == (
        "connector.social",
        "connector.forum",
    )


async def test_b_3_10_a_name_no_connector_carries_reads_nothing(
    outside: Outside, community: Community
) -> None:
    """A name the configuration does not carry is never served by another connector: what the
    step would do cannot be read, so it is held for a person and reads nothing."""
    w = await CommunityWorld(outside, community, both=True).ready()
    version = await w.registered("B-3.10-mentions.yaml")
    run = await w.start(version, query="product", since="2026-10-01", source="connector.nowhere")
    assert run.state is not RunState.FINISHED
    [search] = [s for s in run.step_runs if s.step_id == "search"]
    assert search.state is not StepState.SUCCEEDED and search.adapter is None
    assert w.model.prompts == []


async def test_b_3_10_without_names_the_first_configured_connector_serves(
    outside: Outside, community: Community
) -> None:
    w = await CommunityWorld(outside, community, both=True).ready()
    version = await w.registered("B-3.10-mentions.yaml")
    w.model.answers[SORT] = ""
    run = await w.start(version, query="product", since="2026-10-01")
    assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]
    assert (await w.result(run, "search-second"))["skipped"] is True
    assert {s.step_id: s.adapter for s in run.step_runs}["search"] == "connector.social"


def test_the_community_bundles_name_no_product() -> None:
    root = Path(__file__).resolve().parents[2] / "blueprints" / "software-operations" / "processes"
    for name in ("B-3.07-feature-wish.yaml", "B-3.10-mentions.yaml"):
        text = (root / name).read_text(encoding="utf-8").lower()
        for product in ("canny", "mastodon", "discourse"):
            assert product not in text, f"{name} names {product}"
