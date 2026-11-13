"""The release and stage-5 processes of the blueprint `software-operations` beyond a cluster's
workloads, each registered as shipped and run against fakes of the systems behind its
capabilities (UC-03 §4.8, §4.9; ADR-0210 to ADR-0213).

The world of `test_software_operations_repository.py`, with the connectors of this area served
in-process over MCP as the daemon serves them: the app stores, a serverless platform, a site
hosting service, a newsletter service, a website, an analytics property, a warehouse and the
chat. What is faked: every system behind them (`tests/fakes/`), the model and the owner's chat.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fakes import (
    FakeIdentifiers,
    analytics_service,
    app_stores_service,
    chat_service,
    google_oauth,
    newsletter_service,
    serverless_service,
    site_deploys_service,
    warehouse_service,
    website_service,
)
from fakes.maturity import VERIFIED
from fakes.owner_channel import OWNER
from fakes.ports import free_port
from taktus_connectors.appstores.operations import Config as StoresConfig
from taktus_connectors.appstores.server import build_server as stores_server
from taktus_connectors.bigquery.operations import Config as WarehouseConfig
from taktus_connectors.bigquery.server import build_server as warehouse_server
from taktus_connectors.cloudrun.operations import Config as ServerlessConfig
from taktus_connectors.cloudrun.server import build_server as serverless_server
from taktus_connectors.github.server import Config as RepositoryConfig
from taktus_connectors.github.server import build_server as repository_server
from taktus_connectors.googleanalytics.operations import Config as AnalyticsConfig
from taktus_connectors.googleanalytics.server import build_server as analytics_server
from taktus_connectors.httpcheck.operations import Config as CheckConfig
from taktus_connectors.httpcheck.server import build_server as check_server
from taktus_connectors.kubernetes.operations import Config as WorkloadsConfig
from taktus_connectors.kubernetes.server import build_server as workloads_server
from taktus_connectors.mailchimp.operations import Config as NewsletterConfig
from taktus_connectors.mailchimp.server import build_server as newsletter_server
from taktus_connectors.netlify.operations import Config as SitesConfig
from taktus_connectors.netlify.server import build_server as sites_server
from taktus_connectors.prometheus.operations import Config as MetricsConfig
from taktus_connectors.prometheus.server import build_server as metrics_server
from taktus_connectors.slack.server import Config as ChatConfig
from taktus_connectors.slack.server import build_server as chat_server
from taktus_connectors.wordpress.operations import Config as WebsiteConfig
from taktus_connectors.wordpress.server import build_server as website_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import MemoryQueue
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
)
from taktus.components.run.application.service import ConfirmSteps, EngineOptions, RunEngine
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.composition.personal import ConfiguredPersonalCredentials
from taktus.ports.connector import CallContext, idempotency_key
from taktus.ports.worker import CredentialReference

from .test_software_operations import REPOSITORY, TOKEN, Outside, bundle, states
from .test_software_operations import outside as outside  # the fixture, requested by name
from .test_software_operations_repository import (
    RepositoryWorld,
    api,
    branch,
    pull,
)
from .test_software_operations_repository import cluster as cluster  # the fixture, by name

CONVERSATION = "C0000000001"
WEBSITE = "taktus:" + TOKEN


def _serving(server: Any) -> str:
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}"


def _stores_key(base: str) -> str:
    private = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    return json.dumps(
        {
            "ios": {
                "issuer_id": "69a6de70-0000-47e3-e053-5b8c7c11a4d1",
                "key_id": "2X9R4HXF34",
                "private_key": private.decode("ascii"),
            },
            "android": json.loads(google_oauth.service_account_key(f"{base}/token")),
        }
    )


@dataclass
class Systems:
    """The systems of this area's capabilities, each a fake at its own address."""

    stores: str
    serverless: str
    sites: str
    newsletter: str
    website: str
    analytics: str
    warehouse: str
    chat: str
    servers: list[Any]

    def state(self, system: str) -> Any:
        return httpx.get(f"{getattr(self, system)}/_fake/state", timeout=5).json()

    def fake(self, system: str, path: str, body: dict[str, Any]) -> None:
        """A test-only change of a fake, as the system's people or its reviewers make it."""
        httpx.post(f"{getattr(self, system)}{path}", json=body, timeout=5).raise_for_status()


@pytest.fixture
def systems(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Systems]:
    ports = {name: free_port() for name in ("stores", "serverless", "analytics", "warehouse")}
    base = {name: f"http://127.0.0.1:{port}" for name, port in ports.items()}
    values = {
        "STORES_KEY": _stores_key(base["stores"]),
        "SERVERLESS_KEY": google_oauth.service_account_key(f"{base['serverless']}/token"),
        "ANALYTICS_KEY": google_oauth.service_account_key(f"{base['analytics']}/token"),
        "WAREHOUSE_KEY": google_oauth.service_account_key(f"{base['warehouse']}/token"),
        # The own key of the person who asks B-9.02 its question (ADR-0264).
        "WAREHOUSE_KEY_OWNER": google_oauth.service_account_key(
            f"{base['warehouse']}/token", "owner@example.iam.gserviceaccount.com"
        ),
        "SITES_TOKEN": TOKEN,
        "NEWSLETTER_TOKEN": TOKEN,
        "WEBSITE_TOKEN": WEBSITE,
        "CHAT_TOKEN": TOKEN,
    }
    for name, value in values.items():
        path = tmp_path / name
        path.write_text(value, encoding="utf-8")
        monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{name}_FILE", str(path))
    servers = [
        app_stores_service.make_server("127.0.0.1", ports["stores"], {values["STORES_KEY"]}),
        serverless_service.make_server(
            "127.0.0.1", ports["serverless"], {values["SERVERLESS_KEY"]}
        ),
        analytics_service.make_server("127.0.0.1", ports["analytics"], {values["ANALYTICS_KEY"]}),
        warehouse_service.make_server(
            "127.0.0.1",
            ports["warehouse"],
            {values["WAREHOUSE_KEY"], values["WAREHOUSE_KEY_OWNER"]},
        ),
        site_deploys_service.make_server("127.0.0.1", 0, {TOKEN}),
        newsletter_service.make_server("127.0.0.1", 0, {TOKEN}),
        website_service.make_server("127.0.0.1", 0, {WEBSITE}),
        chat_service.make_server("127.0.0.1", 0, {TOKEN: "write"}),
    ]
    urls = [_serving(s) for s in servers]
    names = ("stores", "serverless", "analytics", "warehouse", "sites", "newsletter", "website")
    yield Systems(**dict(zip(names, urls, strict=False)), chat=urls[-1], servers=servers)
    for server in servers:
        server.shutdown()
        server.server_close()


class ReleaseWorld(RepositoryWorld):
    """The repository world, with this area's connectors. `serverless` puts the serverless
    platform where the cluster serves `deployment.workloads`, under the same credential name."""

    def __init__(
        self,
        outside: Outside,
        cluster: str,
        systems: Systems,
        *,
        serverless: bool = False,
        answers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(outside, cluster)
        self.systems = systems
        # The independent check and the classification of a text for the team (ADR-0142).
        self.model.answers.update(
            {"You check a text": "send", "You classify a text": "none", **(answers or {})}
        )

        def served(server: Any) -> McpActionConnector:
            return McpActionConnector(server, timeout=10.0)

        workloads = (
            serverless_server(
                ServerlessConfig(systems.serverless, "example", "europe-west1", timeout=5.0)
            )
            if serverless
            else workloads_server(WorkloadsConfig(cluster, "default", timeout=5.0))
        )
        connectors = [
            (
                "connector.repository",
                served(
                    repository_server(RepositoryConfig(outside.repository, REPOSITORY, timeout=5.0))
                ),
            ),
            (
                "connector.check",
                served(check_server(CheckConfig(f"{outside.metrics}/service", timeout=5.0))),
            ),
            ("connector.metrics", served(metrics_server(MetricsConfig(outside.metrics, 5.0)))),
            ("connector.workloads", served(workloads)),
            ("connector.sites", served(sites_server(SitesConfig(systems.sites, timeout=5.0)))),
            (
                "connector.stores",
                served(stores_server(StoresConfig(systems.stores, systems.stores, timeout=5.0))),
            ),
            (
                "connector.newsletter",
                served(newsletter_server(NewsletterConfig(systems.newsletter, timeout=5.0))),
            ),
            (
                "connector.website",
                served(website_server(WebsiteConfig(systems.website, timeout=5.0))),
            ),
            (
                "connector.analytics",
                served(
                    analytics_server(
                        AnalyticsConfig(systems.analytics, analytics_service.PROPERTY, timeout=5.0)
                    )
                ),
            ),
            (
                "connector.warehouse",
                served(
                    warehouse_server(
                        WarehouseConfig(
                            systems.warehouse,
                            warehouse_service.PROJECT,
                            warehouse_service.DATASET,
                            timeout=5.0,
                        )
                    )
                ),
            ),
            ("connector.chat", served(chat_server(ChatConfig(target=systems.chat, timeout=5.0)))),
        ]
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.of(Run),
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=self.provenance,
            workers=StaticWorkerPool([("worker.coding", self.worker)]),
            clock=self.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            queue=MemoryQueue(self.persistence, self.clock),
            options=EngineOptions(uncalibrated_margin=0.0),
            connectors=StaticConnectorPool(connectors),
            models=StaticModelPool(
                [
                    (
                        "model.fake",
                        ["review", "release", "analysis", "check"],
                        self.model,
                        "fake-model@1",
                    )
                ]
            ),
            anchors=self.decisions.anchors,
            decisions=self.decisions.requests,
            levels=self.decisions.levels,
            messages=self.told,
            personal=ConfiguredPersonalCredentials(
                {(OWNER, "WAREHOUSE_KEY"): "WAREHOUSE_KEY_OWNER"}
            ),
        )


async def submit_staged(systems: Systems, **input: Any) -> None:
    """A version submitted as a staged release, as a person submits it at the store's console
    or B-8.03 with a first share."""
    connector = McpActionConnector(
        stores_server(StoresConfig(systems.stores, systems.stores, timeout=5.0)), timeout=10.0
    )
    context = CallContext(
        tenant="t",
        identity="idn_release",
        run_id="run_staged",
        step_id="submit",
        attempt=1,
        idempotency_key=idempotency_key("run_staged", "submit", 1),
        credentials=(CredentialReference(name="STORES_KEY", injected_as="env"),),
    )
    await connector.call("stores.releases.submit", context, input)


def serverless_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """`WORKLOADS_TOKEN` as a serverless platform takes it: the service account key, under the
    name the release processes reference, so that they run unchanged (ADR-0211)."""
    monkeypatch.setenv(
        "TAKTUS_CREDENTIAL_WORKLOADS_TOKEN_FILE",
        os.environ["TAKTUS_CREDENTIAL_SERVERLESS_KEY_FILE"],
    )


def finished(run: Run) -> None:
    assert run.state is RunState.FINISHED, [
        (s.step_id, s.state, s.reason) for s in run.step_runs if s.reason
    ]


# --- B-8.05 on a hosted site, B-8.05 and B-8.06 on a serverless platform (ADR-0211) -------------


async def test_b_8_05_on_a_site_publishes_the_version_and_a_passed_smoke_test_leaves_it(
    outside: Outside, cluster: str, systems: Systems
) -> None:
    w = await ReleaseWorld(outside, cluster, systems).ready()
    version = await w.registered("B-8.05-site-deployment.yaml")
    live, nxt = site_deploys_service.DEPLOYS[0], site_deploys_service.DEPLOYS[1]
    run = await w.confirmed(await w.start(version, site="web", build=nxt, smoke_path="/health"))
    finished(run)
    assert systems.state("sites")["sites"]["web"]["live"] == nxt
    assert (await w.result(run, "before"))["output"]["live"] == live
    assert (await w.result(run, "rollback"))["skipped"] is True


async def test_b_8_05_on_a_site_puts_the_earlier_version_back_only_once_a_person_decided(
    outside: Outside, cluster: str, systems: Systems
) -> None:
    w = await ReleaseWorld(outside, cluster, systems).ready()
    version = await w.registered("B-8.05-site-deployment.yaml")
    live, nxt = site_deploys_service.DEPLOYS[0], site_deploys_service.DEPLOYS[1]
    run = await w.confirmed(await w.start(version, site="web", build=nxt, smoke_path="/missing"))
    assert states(run)["rollback"] is StepState.WAITING_HUMAN
    assert systems.state("sites")["sites"]["web"]["live"] == nxt, "not put back yet"
    run = await w.confirmed(await w.decided(run, "rollback"))
    finished(run)
    assert systems.state("sites")["sites"]["web"]["live"] == live


@pytest.mark.parametrize("smoke", ["/health", "/missing"])
async def test_b_8_05_runs_unchanged_on_a_serverless_platform(
    outside: Outside, cluster: str, systems: Systems, smoke: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    serverless_key(monkeypatch)
    w = await ReleaseWorld(outside, cluster, systems, serverless=True).ready()
    version = await w.registered("B-8.05-web-deployment.yaml")
    release = {"deployment": "web", "container": "app", "image": "registry.example/app:1.1.0"}
    run = await w.confirmed(await w.start(version, **release, smoke_path=smoke))
    if smoke == "/missing":
        assert states(run)["rollback"] is StepState.WAITING_HUMAN
        run = await w.confirmed(await w.decided(run, "rollback"))
    finished(run)
    images = systems.state("serverless")["services"]["web"]["images"]
    assert images == (
        [serverless_service.IMAGE] if smoke == "/missing" else ["registry.example/app:1.1.0"]
    )


@pytest.mark.parametrize(("rate", "rolled_back"), [("0.001", False), ("0.2", True)])
async def test_b_8_06_runs_unchanged_on_a_serverless_platform(
    outside: Outside,
    cluster: str,
    systems: Systems,
    rate: str,
    rolled_back: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serverless_key(monkeypatch)
    w = await ReleaseWorld(outside, cluster, systems, serverless=True).ready()
    version = await w.registered("B-8.06-backend-deployment.yaml")
    release = {"deployment": "web", "container": "app", "image": "registry.example/api:2.4.1"}
    run = await w.confirmed(
        await w.start(version, **release, error_rate_query=rate, max_error_rate="0.02")
    )
    if rolled_back:
        assert states(run)["rollback"] is StepState.WAITING_HUMAN
        run = await w.confirmed(await w.decided(run, "rollback"))
    finished(run)
    images = systems.state("serverless")["services"]["web"]["images"]
    assert images == ([serverless_service.IMAGE] if rolled_back else [release["image"]])


# --- B-1.03's brake on a serverless platform (ADR-0310) -----------------------------------------

BRAKE = {"query": "service_calls_per_second", "throttle_above": 100, "throttle_to": 1}


async def test_b_1_03_at_level_1_proposes_the_throttle_and_a_person_performs_it(
    outside: Outside, cluster: str, systems: Systems, monkeypatch: pytest.MonkeyPatch
) -> None:
    """As shipped, at level 1: the runaway is named by rule and the throttle waits for a person
    to perform it; the platform is not touched by Taktus."""
    serverless_key(monkeypatch)
    w = await ReleaseWorld(outside, cluster, systems, serverless=True).ready()
    version = await w.registered("B-1.03-runaway.yaml")
    run = await w.start(version, **BRAKE)
    assert run.state is RunState.WAITING_HUMAN
    assert states(run)["throttle"] is StepState.WAITING_HUMAN
    runaway = await w.result(run, "runaway")
    assert runaway["count"] == 1 and runaway["first"]["labels"]["function"] == "web"
    assert len(systems.state("serverless")["services"]["web"]["revisions"]) == 1
    run = await w.engine.confirm(
        ConfirmSteps(run_id=run.id, steps=("throttle",), actor=OWNER, tenant="t", performed=True)
    )
    finished(run)
    assert len(systems.state("serverless")["services"]["web"]["revisions"]) == 1, "a person did"


async def test_b_1_03_at_level_2_throttles_the_runaway_once_a_person_confirmed(
    outside: Outside, cluster: str, systems: Systems, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tenant's version at level 2: the brake is set once confirmed, and names the limit
    before; below the threshold nothing is throttled."""
    serverless_key(monkeypatch)
    w = await ReleaseWorld(outside, cluster, systems, serverless=True).ready()
    raised = bundle("B-1.03-runaway.yaml")
    raised["autonomy"] = {**raised["autonomy"], "level": 2}
    version = await w.register.execute(RegisterProcessVersion(raised, tenant="t", by=OWNER))
    calm = await w.confirmed(await w.start(version, **{**BRAKE, "throttle_above": 1000}))
    finished(calm)
    assert (await w.result(calm, "throttle"))["skipped"] is True
    run = await w.start(version, **BRAKE)
    assert run.state is RunState.WAITING_HUMAN, "at level 2 nothing starts before a person"
    run = await w.confirmed(run)
    finished(run)
    throttled = (await w.result(run, "throttle"))["output"]
    assert throttled["name"] == "web" and throttled["max_instances"] == 1
    assert throttled["max_instances_before"] is None
    assert len(systems.state("serverless")["services"]["web"]["revisions"]) == 2


# --- B-8.02, B-8.03, B-8.04 at an app store (ADR-0210) -----------------------------------------


async def test_b_8_02_gives_the_newest_build_to_the_testers_and_files_their_feedback_once(
    outside: Outside, cluster: str, systems: Systems
) -> None:
    w = await ReleaseWorld(outside, cluster, systems).ready()
    version = await w.registered("B-8.02-beta.yaml")
    inputs = {"platform": "ios", "app": app_stores_service.APP, "group": "g-1"}
    before = len(outside.issues())
    run = await w.confirmed(await w.start(version, **inputs))
    finished(run)
    assert systems.state("stores")["ios"]["groups"]["g-1"] == ["b-2"]
    [filed] = outside.issues()[: len(outside.issues()) - before]
    assert "beta-feedback:" in filed["body"] and "@" not in filed["body"], "never the tester"
    again = await w.confirmed(await w.start(version, **inputs))
    finished(again)
    marks = [i["body"].splitlines()[-1] for i in outside.issues() if "beta-feedback:" in i["body"]]
    assert len(marks) == 2 and len(set(marks)) == 2, "the next run files the next piece, once"


async def test_b_8_02_on_the_store_without_feedback_skips_the_feedback(
    outside: Outside, cluster: str, systems: Systems
) -> None:
    w = await ReleaseWorld(outside, cluster, systems).ready()
    version = await w.registered("B-8.02-beta.yaml")
    inputs = {"platform": "android", "app": app_stores_service.PACKAGE, "group": "internal"}
    run = await w.confirmed(await w.start(version, **inputs))
    finished(run)
    [release] = systems.state("stores")["android"]["tracks"]["internal"]
    assert release["versionCodes"] == ["2"] and release["status"] == "completed"
    assert (await w.result(run, "feedback"))["skipped"] is True


async def test_b_8_03_submits_only_once_a_person_decided_and_files_a_rejection_at_once(
    outside: Outside, cluster: str, systems: Systems
) -> None:
    w = await ReleaseWorld(outside, cluster, systems).ready()
    version = await w.registered("B-8.03-store-submission.yaml")
    inputs = {"platform": "ios", "app": app_stores_service.APP, "release": "v-11"}
    run = await w.confirmed(await w.start(version, **inputs))
    assert states(run)["submit"] is StepState.WAITING_HUMAN
    assert systems.state("stores")["ios"]["versions"]["v-11"] == "PREPARE_FOR_SUBMISSION"
    # The review, as the store's reviewers will conclude it once it is submitted.
    systems.fake("stores", "/_fake/verdict", {"version": "v-11", "state": "REJECTED"})
    before = len(outside.issues())
    run = await w.confirmed(await w.decided(run, "submit"))
    finished(run)
    [filed] = outside.issues()[: len(outside.issues()) - before]
    assert filed["title"] == "The store's review rejected a version"


async def test_b_8_04_at_a_store_raises_the_staged_release_and_halts_it_on_a_rise(
    outside: Outside, cluster: str, systems: Systems
) -> None:
    w = await ReleaseWorld(outside, cluster, systems).ready()
    android = {"platform": "android", "app": app_stores_service.PACKAGE}
    await submit_staged(systems, **android, version="2", fraction=0.01)
    rollout = await w.registered("B-8.04-store-rollout.yaml")
    run = await w.confirmed(
        await w.start(
            rollout,
            **android,
            first=0.05,
            second=0.2,
            third=1,
            crash_rate_query="0.2",
            max_crash_rate="0.01",
        )
    )
    finished(run)
    staged = systems.state("stores")["android"]["tracks"]["production"]
    assert any(r["status"] == "halted" and r.get("userFraction") == 0.05 for r in staged), staged
    assert (await w.result(run, "raise-2"))["skipped"] is True


# --- B-8.01 Preparing a release (ADR-0212) ------------------------------------------------------

TEXTS = (
    "Test plan\n- sign in\n\nChangelog\n- Fixed: sign-in\n\nStore texts\nSign-in works again.\n\n"
    "Newsletter\nSigning in works again."
)


async def test_b_8_01_drafts_the_texts_from_the_changes_merged_into_the_base(
    outside: Outside, cluster: str, systems: Systems
) -> None:
    w = await ReleaseWorld(
        outside, cluster, systems, answers={"You draft the texts": TEXTS}
    ).ready()
    branch(outside, "fix/sign-in", {"src/a.py": "a = 2\n"})
    number = pull(outside, "fix/sign-in", "Fix sign-in")
    head = api(outside, "GET", f"/pulls/{number}")["head"]["sha"]
    api(outside, "PUT", f"/pulls/{number}/merge", {"sha": head, "merge_method": "squash"})
    branch(outside, "release/2.0", {"CHANGELOG.md": "2.0\n"})
    release = pull(outside, "release/2.0", "Release 2.0")
    version = await w.registered("B-8.01-release-texts.yaml")
    run = await w.confirmed(await w.start(version, pull=release, since_hours=336))
    finished(run)
    assert (await w.result(run, "changes"))["count"] == 1
    [comment] = api(outside, "GET", f"/issues/{release}/comments")
    assert "1 change(s)" in comment["body"] and "Store texts" in comment["body"]
    assert "Fix sign-in" in str(w.model.prompts[-1].user), "the model was given the titles"


def merged_change(outside: Outside, name: str, title: str) -> None:
    """A change merged into the base, as a person merges it."""
    branch(outside, name, {f"src/{name.replace('/', '_')}.py": "a = 3\n"})
    number = pull(outside, name, title)
    head = api(outside, "GET", f"/pulls/{number}")["head"]["sha"]
    api(outside, "PUT", f"/pulls/{number}/merge", {"sha": head, "merge_method": "squash"})


# --- B-8.08 Changelog and website, B-9.07 Newsletter (ADR-0212) -------------------------------


POST = "<p>Signing in works again.</p><ul><li>Fixed: sign-in</li></ul>"


async def test_b_8_08_drafts_the_post_and_publishes_it_only_once_a_person_decided(
    outside: Outside, cluster: str, systems: Systems
) -> None:
    w = await ReleaseWorld(
        outside, cluster, systems, answers={"You write the website post": POST}
    ).ready()
    merged_change(outside, "fix/sign-in", "Fix sign-in")
    version = await w.registered("B-8.08-changelog-and-website.yaml")
    run = await w.confirmed(await w.start(version, release="2.0", since_hours=336))
    assert states(run)["publish"] is StepState.WAITING_HUMAN
    posts = systems.state("website")["posts"]
    [drafted] = [p for p in posts.values() if p["status"] == "draft"]
    assert drafted["title"] == "What is new in 2.0", "drafted, not published"
    run = await w.confirmed(await w.decided(run, "publish"))
    finished(run)
    statuses = [p["status"] for p in systems.state("website")["posts"].values()]
    assert statuses.count("publish") == 2 and "draft" not in statuses


async def test_b_9_07_drafts_the_newsletter_and_sends_it_only_once_a_person_decided(
    outside: Outside, cluster: str, systems: Systems
) -> None:
    w = await ReleaseWorld(
        outside, cluster, systems, answers={"You write the newsletter": "Sign-in works again."}
    ).ready()
    merged_change(outside, "fix/sign-in", "Fix sign-in")
    version = await w.registered("B-9.07-newsletter.yaml")
    inputs = {"audience": "list-1", "from_name": "Example", "reply_to": "news@example.org"}
    run = await w.confirmed(await w.start(version, release="2.0", since_hours=336, **inputs))
    assert states(run)["send"] is StepState.WAITING_HUMAN
    assert systems.state("newsletter")["sent"] == [], "nothing sent before the decision"
    run = await w.confirmed(await w.decided(run, "send"))
    finished(run)
    assert len(systems.state("newsletter")["sent"]) == 1
    assert (await w.result(run, "draft"))["output"]["recipients"] == 1200


# --- B-9.02, B-9.03, B-9.06 over the copy without personal fields (ADR-0213) -------------------


def chat_messages(systems: Systems) -> list[dict[str, Any]]:
    found = httpx.get(
        f"{systems.chat}/_fake/messages", params={"channel": CONVERSATION}, timeout=5
    ).json()
    return list(found.get("messages", []) if isinstance(found, dict) else found)


async def test_b_9_02_answers_a_question_from_the_warehouses_rows_in_the_questions_thread(
    outside: Outside, cluster: str, systems: Systems
) -> None:
    w = await ReleaseWorld(
        outside,
        cluster,
        systems,
        answers={
            "You write one query": warehouse_service.FUNNEL,
            "You read the rows": "Of 1000 who visited, 60 subscribed.",
        },
    ).ready()
    version = await w.registered("B-9.02-figures.yaml")
    inputs = {
        "question": "How many visitors subscribe?",
        "tables": "signups_funnel(step, users)",
        "address": CONVERSATION,
        "thread": "1730000000.000100",
    }
    asked = {"channel": CONVERSATION, "ts": inputs["thread"], "user": "U1", "text": "How many?"}
    systems.fake("chat", "/_fake/messages", asked)
    before = len(chat_messages(systems))
    run = await w.confirmed(await w.start(version, **inputs))
    finished(run)
    [reply] = chat_messages(systems)[before:]
    assert "visited" in reply["text"] and warehouse_service.FUNNEL in reply["text"]
    assert systems.state("warehouse")["dry_runs"] >= 1, "the warehouse judged it a query first"


async def test_b_9_02_a_statement_that_changes_data_never_reaches_the_warehouse(
    outside: Outside, cluster: str, systems: Systems
) -> None:
    w = await ReleaseWorld(
        outside, cluster, systems, answers={"You write one query": "DELETE FROM signups_funnel"}
    ).ready()
    version = await w.registered("B-9.02-figures.yaml")
    inputs = {"question": "x", "tables": "t", "address": CONVERSATION, "thread": "1.1"}
    run = await w.confirmed(await w.start(version, **inputs))
    assert run.state is not RunState.FINISHED
    assert states(run)["rows"] is not StepState.SUCCEEDED
    assert systems.state("warehouse")["queries"] == 0


async def test_b_9_03_posts_the_weeks_as_the_analytics_service_gave_them(
    outside: Outside, cluster: str, systems: Systems
) -> None:
    w = await ReleaseWorld(
        outside, cluster, systems, answers={"You read a software product's use": "Steady."}
    ).ready()
    version = await w.registered("B-9.03-weekly-trends.yaml")
    before = len(chat_messages(systems))
    run = await w.confirmed(await w.start(version, address=CONVERSATION))
    finished(run)
    weeks = (await w.result(run, "weeks"))["output"]["rows"]
    assert weeks and set(weeks[0]["metrics"]) == {"activeUsers", "newUsers", "sessions"}
    [post] = chat_messages(systems)[before:]
    assert "Steady." in post["text"] and weeks[0]["dimensions"]["isoYearIsoWeek"] in post["text"]


async def test_b_9_06_proposes_from_the_funnel_and_starts_nothing(
    outside: Outside, cluster: str, systems: Systems
) -> None:
    proposal = "Most leave after signed_up. Hypothesis: the activation mail is late."
    w = await ReleaseWorld(
        outside, cluster, systems, answers={"You read the steps": proposal}
    ).ready()
    version = await w.registered("B-9.06-onboarding.yaml")
    before = len(chat_messages(systems))
    run = await w.confirmed(
        await w.start(version, funnel_query=warehouse_service.FUNNEL, address=CONVERSATION)
    )
    finished(run)
    [post] = chat_messages(systems)[before:]
    assert proposal in post["text"] and "subscribed" in post["text"]
