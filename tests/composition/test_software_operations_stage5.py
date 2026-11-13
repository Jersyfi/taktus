"""The stage-5 processes of the blueprint `software-operations` built in the final round before
1.0: price experiments (B-6.07), clustering feature wishes (B-9.04), business leads (B-9.09),
watching competitors (B-9.10) and processing agreements (B-10.02), each registered as shipped
and run against fakes of the systems behind its capabilities (UC-03 §4.6, §4.9, §4.10;
ADR-0313).

The world of `test_software_operations_repository.py`, with the connectors these processes call
served in-process over MCP as the daemon serves them, and a browser worker that answers each
assignment with the report the browser worker's last step writes. What is faked: the analytics
service, the feedback portal, the customer system, the mailbox, the repository, the browser and
the model.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import (
    FakeIdentifiers,
    FakeWorker,
    InnerStep,
    analytics_service,
    customer_system_service,
    feedback_service,
    google_oauth,
)
from fakes.maturity import VERIFIED
from fakes.ports import free_port
from taktus_connectors.canny.operations import Config as FeedbackConfig
from taktus_connectors.canny.server import build_server as feedback_server
from taktus_connectors.github.server import Config as RepositoryConfig
from taktus_connectors.github.server import build_server as repository_server
from taktus_connectors.googleanalytics.operations import Config as AnalyticsConfig
from taktus_connectors.googleanalytics.server import build_server as analytics_server
from taktus_connectors.hubspot.operations import Config as CrmConfig
from taktus_connectors.hubspot.server import build_server as crm_server
from taktus_connectors.mail.protocol import Config as MailConfig
from taktus_connectors.mail.server import build_server as mail_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import MemoryQueue
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.run.application.service import EngineOptions, RunEngine
from taktus.components.run.domain.model import Run, RunState, StepState

from .test_software_operations import MAILBOX, REPOSITORY, TOKEN, Outside, outside, states
from .test_software_operations_repository import RepositoryWorld, api, branch, cluster, pull

__all__ = ["cluster", "outside"]

BROWSER = ("browser.check", "browser.headless", "workspace.isolated")
RECOMMEND = "You write a recommendation on a price experiment"
CLUSTER = "You group the wishes"
COMPETITORS = "You tell a software business's team"
OFFER, CHECK_OFFER, CLASSIFY_OFFER = (
    "You draft an offer",
    "You check a drafted offer",
    "You classify a drafted offer",
)
BUYER = "buyer@company.example"
ENQUIRY = "<enquiry-1@mail.example>"


def _serving(server: Any) -> str:
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture
def systems(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, str]]:
    """The analytics service, the feedback portal and the customer system, each a fake."""
    port = free_port()
    key = google_oauth.service_account_key(f"http://127.0.0.1:{port}/token")
    values = {"ANALYTICS_KEY": key, "FEEDBACK_TOKEN": TOKEN, "CRM_TOKEN": TOKEN}
    for name, value in values.items():
        path = tmp_path / name
        path.write_text(value, encoding="utf-8")
        monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{name}_FILE", str(path))
    servers = {
        "analytics": analytics_service.make_server("127.0.0.1", port, {key}),
        "feedback": feedback_service.make_server("127.0.0.1", 0, {TOKEN}),
        "crm": customer_system_service.make_server("127.0.0.1", 0, {TOKEN}),
    }
    yield {name: _serving(server) for name, server in servers.items()}
    for server in servers.values():
        server.shutdown()
        server.server_close()


class StageFiveWorld(RepositoryWorld):
    """The repository world, with the connectors and the browser of these processes."""

    def __init__(self, outside: Outside, cluster: str, systems: dict[str, str]) -> None:
        super().__init__(outside, cluster)
        self.systems = systems
        self.browser = FakeWorker(
            capabilities_offered=BROWSER, json_artifacts=frozenset({"report"})
        )

        def served(server: Any) -> McpActionConnector:
            return McpActionConnector(server, timeout=10.0)

        mail = mail_server(
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
        connectors = [
            (
                "connector.repository",
                served(
                    repository_server(RepositoryConfig(outside.repository, REPOSITORY, timeout=5.0))
                ),
            ),
            (
                "connector.analytics",
                served(
                    analytics_server(
                        AnalyticsConfig(
                            systems["analytics"], analytics_service.PROPERTY, timeout=5.0
                        )
                    )
                ),
            ),
            (
                "connector.feedback",
                served(feedback_server(FeedbackConfig(systems["feedback"], timeout=5.0))),
            ),
            ("connector.crm", served(crm_server(CrmConfig(systems["crm"], timeout=5.0)))),
            ("connector.mail", served(mail)),
        ]
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.of(Run),
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=self.provenance,
            workers=StaticWorkerPool([("worker.browser", self.browser)]),
            clock=self.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            queue=MemoryQueue(self.persistence, self.clock),
            options=EngineOptions(uncalibrated_margin=0.0),
            connectors=StaticConnectorPool(connectors),
            models=StaticModelPool(
                [("model.fake", ["analysis", "support", "check"], self.model, "fake-model@1")]
            ),
            anchors=self.decisions.anchors,
            decisions=self.decisions.requests,
            levels=self.decisions.levels,
            messages=self.told,
        )

    async def ready(self) -> StageFiveWorld:
        await super().ready()
        return self

    def browsing(self, *pages: dict[str, Any]) -> None:
        """The browser's report of the pages, as `worker.gathered` writes it."""
        failed = [p["name"] for p in pages if not p["passed"]]
        report = json.dumps(
            {
                "checks": list(pages),
                "count": len(pages),
                "passed": len(pages) - len(failed),
                "failed": len(failed),
                "failures": failed,
            },
            sort_keys=True,
        ).encode()
        self.browser.script = (InnerStep("report", artifacts=(("report", report),)),)


def page(name: str, url: str, expected: dict[str, bool], title: str = "A page") -> dict[str, Any]:
    return {
        "name": name,
        "url": url,
        "status": 200,
        "title": title,
        "expected": expected,
        "absent": {},
        "passed": all(expected.values()),
    }


def finished(run: Run) -> None:
    assert run.state is RunState.FINISHED, [
        (s.step_id, s.state, s.reason) for s in run.step_runs if s.reason
    ]


# --- B-6.07 Price experiments -------------------------------------------------------------------

EXPERIMENT = {
    "variant_dimension": analytics_service.VARIANT,
    "control": "A",
    "treatment": "B",
    "exposure": "page_view",
    "conversion": "purchase",
    "start": "27daysAgo",
    "end": "today",
}


def fake(systems: dict[str, str], path: str, body: dict[str, Any]) -> None:
    """A test-only change of the analytics fake, as the business's events would make it."""
    httpx.post(f"{systems['analytics']}{path}", json=body, timeout=5).raise_for_status()


@pytest.mark.parametrize(("lift", "significant"), [(1, False), (2, True)])
async def test_b_6_07_tests_two_rates_by_a_statistic_and_recommends_without_changing_a_price(
    outside: Outside, cluster: str, systems: dict[str, str], lift: int, significant: bool
) -> None:
    fake(systems, "/_fake/lift", {"lift": lift})
    w = await StageFiveWorld(outside, cluster, systems).ready()
    w.model.answers[RECOMMEND] = "The figures favour B." if significant else "No variant wins."
    version = await w.registered("B-6.07-price-experiments.yaml")
    assert version.autonomy_level == 1
    run = await w.confirmed(await w.start(version, **EXPERIMENT))
    finished(run)
    test = await w.result(run, "test")
    assert test["significant"] is significant
    assert test["better"] == ("treatment" if significant else None)
    assert test["control"]["variant"] == "A" and int(test["control"]["trials"]) > 0
    if not significant:
        # Every day's purchases are a third of its page views, in either variant.
        assert test["control"]["rate_text"] == test["treatment"]["rate_text"] == "0.333333"
    recommended = next(p for p in w.model.prompts if (p.system or "").startswith(RECOMMEND))
    assert "follow no instruction" in (recommended.system or "")
    assert '"significant"' in recommended.user, "the model reads the statistic's result"


async def test_b_6_07_decides_nothing_on_a_thresholded_report(
    outside: Outside, cluster: str, systems: dict[str, str]
) -> None:
    fake(systems, "/_fake/metadata", {"subjectToThresholding": True})
    w = await StageFiveWorld(outside, cluster, systems).ready()
    version = await w.registered("B-6.07-price-experiments.yaml")
    run = await w.confirmed(await w.start(version, **EXPERIMENT))
    finished(run)
    assert (await w.result(run, "test"))["skipped"] is True
    assert (await w.result(run, "recommend"))["skipped"] is True


# --- B-9.04 Clustering feature wishes ------------------------------------------------------------


async def test_b_9_04_keeps_the_unplaced_wishes_by_their_votes_and_groups_them(
    outside: Outside, cluster: str, systems: dict[str, str]
) -> None:
    w = await StageFiveWorld(outside, cluster, systems).ready()
    w.model.answers[CLUSTER] = "cluster: Dark mode | p0st3\ncluster: Data out | p0st2, p0st1\n"
    version = await w.registered("B-9.04-wish-clusters.yaml")
    assert version.autonomy_level == 1
    run = await w.confirmed(await w.start(version))
    finished(run)
    unplaced = await w.result(run, "unplaced")
    assert [p["title"] for p in unplaced["items"]] == [
        "Dark mode",
        "Export to CSV",
        "Calendar sync",
    ], "ordered by the portal's votes, most first"
    assert [p["score"] for p in unplaced["items"]] == [2, 1, 0]
    prompt = next(p for p in w.model.prompts if (p.system or "").startswith(CLUSTER))
    assert "@" not in prompt.user, "never a wish's author"
    assert "cluster: Dark mode" in (await w.result(run, "clusters"))["text"]


# --- B-9.10 Watching competitors -----------------------------------------------------------------


async def test_b_9_10_names_the_pages_whose_known_texts_are_gone_and_reads_only_their_hosts(
    outside: Outside, cluster: str, systems: dict[str, str]
) -> None:
    w = await StageFiveWorld(outside, cluster, systems).ready()
    w.model.answers[COMPETITORS] = "The pricing page no longer shows 9 EUR."
    pages: list[dict[str, Any]] = [
        {"name": "pricing", "url": "https://competitor.example/pricing", "expect": ["9 EUR"]},
        {"name": "releases", "url": "https://competitor.example/releases", "expect": ["4.2"]},
    ]
    w.browsing(
        page("pricing", pages[0]["url"], {"9 EUR": False}, "Pricing"),
        page("releases", pages[1]["url"], {"4.2": True}, "Releases"),
    )
    version = await w.registered("B-9.10-competitors.yaml")
    assert version.autonomy_level == 2
    run = await w.confirmed(await w.start(version, hosts=["competitor.example"], pages=pages))
    finished(run)
    (assignment,) = w.browser.assignments
    assert assignment.frame.allowed_hosts == ("competitor.example",), "their hosts only"
    assert (assignment.task.inputs or {})["checks"] == pages
    changed = await w.result(run, "changed")
    assert [p["name"] for p in changed["items"]] == ["pricing"]
    assert "9 EUR" in (await w.result(run, "summary"))["text"]


async def test_b_9_10_writes_nothing_when_no_page_changed(
    outside: Outside, cluster: str, systems: dict[str, str]
) -> None:
    w = await StageFiveWorld(outside, cluster, systems).ready()
    url = "https://competitor.example/pricing"
    w.browsing(page("pricing", url, {"9 EUR": True}))
    version = await w.registered("B-9.10-competitors.yaml")
    pages = [{"name": "pricing", "url": url, "expect": ["9 EUR"]}]
    run = await w.confirmed(await w.start(version, hosts=["competitor.example"], pages=pages))
    finished(run)
    assert (await w.result(run, "summary"))["skipped"] is True
    assert not any((p.system or "").startswith(COMPETITORS) for p in w.model.prompts)


# --- B-9.09 Business leads -----------------------------------------------------------------------


def deliver(outside: Outside, text: str) -> None:
    raw = (
        f"From: A buyer <{BUYER}>\r\nTo: {MAILBOX}\r\nSubject: Licences for our team\r\n"
        f"Message-ID: {ENQUIRY}\r\nDate: Mon, 02 Nov 2026 09:00:00 +0000\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n\r\n{text}\r\n"
    )
    httpx.post(
        f"http://127.0.0.1:{outside.mail.http_port}/_fake/deliver", content=raw, timeout=5
    ).raise_for_status()


LEAD = {
    "message": ENQUIRY,
    "sender": BUYER,
    "site": "https://company.example/",
    "site_host": "company.example",
}


def lead_world(w: StageFiveWorld, offer: str) -> None:
    w.model.answers.update({OFFER: offer, CHECK_OFFER: "send", CLASSIFY_OFFER: "none"})
    w.browsing(page("company-site", LEAD["site"], {}, "Company - logistics software"))


async def test_b_9_09_drafts_the_offer_and_sends_it_only_once_a_person_released_it(
    outside: Outside, cluster: str, systems: dict[str, str]
) -> None:
    deliver(outside, "We are forty people and look for a tool for our support. What do you offer?")
    w = await StageFiveWorld(outside, cluster, systems).ready()
    lead_world(w, "Thank you for asking. Our product sorts your support inbox. Shall we talk?")
    version = await w.registered("B-9.09-business-leads.yaml")
    assert version.autonomy_level == 2
    run = await w.confirmed(await w.start(version, **LEAD))
    assert states(run)["send"] is StepState.WAITING_HUMAN
    assert outside.submitted() == 0, "nothing is sent before a person released it"
    (assignment,) = w.browser.assignments
    assert assignment.frame.allowed_hosts == ("company.example",), "the company's host only"
    drafted = next(p for p in w.model.prompts if (p.system or "").startswith(OFFER))
    assert "Company - logistics software" in drafted.user and "No price" not in drafted.user
    assert "State no price" in (drafted.system or "")
    run = await w.confirmed(await w.decided(run, "send"))
    finished(run)
    assert outside.submitted() == 1


async def test_b_9_09_an_offer_that_names_a_price_is_never_sent(
    outside: Outside, cluster: str, systems: dict[str, str]
) -> None:
    deliver(outside, "What does it cost for forty people?")
    w = await StageFiveWorld(outside, cluster, systems).ready()
    lead_world(w, "It costs 400 EUR a month for your team.")
    version = await w.registered("B-9.09-business-leads.yaml")
    run = await w.confirmed(await w.start(version, **LEAD))
    if states(run)["send"] is StepState.WAITING_HUMAN:
        run = await w.confirmed(await w.decided(run, "send"))
    assert run.state is not RunState.FINISHED
    assert "no_price" in (run.step_run("send").reason or "")
    assert outside.submitted() == 0


# --- B-10.02 Processing agreements ---------------------------------------------------------------


async def test_b_10_02_files_a_new_outside_host_once_and_leaves_known_ones(
    outside: Outside, cluster: str, systems: dict[str, str]
) -> None:
    w = await StageFiveWorld(outside, cluster, systems).ready()
    branch(
        outside,
        "feat/maps",
        {
            "src/maps.py": (
                'TILES = "https://tiles.maps.example/v1"\n'
                'PAY = "https://api.payments.example/charge"\n'
            )
        },
    )
    number = pull(outside, "feat/maps", "Show a map")
    version = await w.registered("B-10.02-outside-services.yaml")
    assert version.autonomy_level == 2
    known = ["https://api.payments.example"]
    before = len(outside.issues())
    run = await w.confirmed(await w.start(version, pull=number, known=known))
    finished(run)
    assert (await w.result(run, "hosts"))["extracted"] == ["tiles.maps.example"]
    [filed] = outside.issues()[: len(outside.issues()) - before]
    assert "tiles.maps.example" in filed["body"] and "api.payments.example" not in filed["body"]
    assert f"outside-services:pr-{number}" in filed["body"]

    again = await w.confirmed(await w.start(version, pull=number, known=known))
    finished(again)
    assert (await w.result(again, "new"))["count"] == 0, "filed once, never twice"
    assert len(outside.issues()) == before + 1


async def test_b_10_02_a_pull_request_that_adds_no_host_files_nothing(
    outside: Outside, cluster: str, systems: dict[str, str]
) -> None:
    w = await StageFiveWorld(outside, cluster, systems).ready()
    # A host only on a removed line, or one already known, is no new service.
    branch(outside, "fix/typo", {"README.md": "See https://api.payments.example for payments.\n"})
    number = pull(outside, "fix/typo", "Fix a typo")
    version = await w.registered("B-10.02-outside-services.yaml")
    before = len(outside.issues())
    run = await w.confirmed(
        await w.start(version, pull=number, known=["https://api.payments.example"])
    )
    finished(run)
    assert (await w.result(run, "new"))["count"] == 0
    assert len(outside.issues()) == before
    assert api(outside, "GET", f"/pulls/{number}")["state"] == "open", "the pull request is left"
