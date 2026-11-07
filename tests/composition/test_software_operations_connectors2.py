"""The processes of the blueprint `software-operations` that gained a provider in release 1.0,
each run against the new provider's connector and its fake (ADR-0266 to ADR-0269).

The worlds of `test_software_operations.py` and `test_software_operations_release.py`, with the
connector that serves one capability replaced by the new provider's, under the same capability
and the same credential name: a mail service's API under `mail.messages` and
`newsletter.broadcasts`, an event analytics service under `analytics.reports`, a content lake
under `website.posts`, a functions platform under `deployment.sites`. The worlds build their
connectors from module names, which the tests point at the new connector; nothing of the worlds
changes. What is faked: every system behind them (`tests/fakes/`), the model and the owner's
chat.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import (
    content_lake_service,
    functions_service,
    google_oauth,
    mail_api_service,
    product_analytics_service,
)
from fakes.ports import free_port
from taktus_connectors.cloudfunctions.operations import Config as FunctionsConfig
from taktus_connectors.cloudfunctions.server import build_server as functions_server
from taktus_connectors.mixpanel.operations import Config as EventsConfig
from taktus_connectors.mixpanel.server import build_server as events_server
from taktus_connectors.resend.api import Config as MailApiConfig
from taktus_connectors.resend.server import build_server as mail_api_server
from taktus_connectors.sanity.operations import Config as ContentConfig
from taktus_connectors.sanity.server import build_server as content_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.components.run.domain.model import StepState
from taktus.ports.connector import CallContext, idempotency_key
from taktus.ports.worker import CredentialReference

from . import test_software_operations as support
from . import test_software_operations_release as release
from .test_software_operations import TOKEN, Outside, World, replying, states
from .test_software_operations import outside as outside  # the fixture, requested by name
from .test_software_operations_release import (
    CONVERSATION,
    ReleaseWorld,
    Systems,
    chat_messages,
    finished,
    merged_change,
)
from .test_software_operations_release import systems as systems  # the fixture, by name
from .test_software_operations_repository import cluster as cluster  # the fixture, by name

SENDER = "support@example.org"
EVENTS_KEY = "svc-taktus:" + TOKEN
CONTENT_TOKEN = "sk-" + TOKEN
FIRST = "example-sources/web/1.0.0.tar.gz#1730000000000001"
SECOND = "example-sources/web/1.1.0.tar.gz#1730000000000002"


def _serving(server: Any) -> str:
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}"


def _credential(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    path = tmp_path / f"new-{name}"
    path.write_text(value, encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{name}_FILE", str(path))


class New:
    """The new providers' fakes, each at its own address."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        port = free_port()
        functions_key = google_oauth.service_account_key(f"http://127.0.0.1:{port}/token")
        self.servers = [
            mail_api_service.make_server("127.0.0.1", 0, {TOKEN}),
            product_analytics_service.make_server("127.0.0.1", 0, {EVENTS_KEY}),
            content_lake_service.make_server("127.0.0.1", 0, {CONTENT_TOKEN}),
            functions_service.make_server("127.0.0.1", port, {functions_key}),
        ]
        self.mail, self.events, self.content, self.functions = [_serving(s) for s in self.servers]
        self.tmp_path, self.monkeypatch = tmp_path, monkeypatch
        self.functions_key = functions_key

    def state(self, system: str) -> Any:
        return httpx.get(f"{getattr(self, system)}/_fake/state", timeout=5).json()

    def stop(self) -> None:
        for server in self.servers:
            server.shutdown()
            server.server_close()

    def credential(self, name: str, value: str) -> None:
        _credential(self.tmp_path, self.monkeypatch, name, value)


@pytest.fixture
def new(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[New]:
    found = New(tmp_path, monkeypatch)
    yield found
    found.stop()


def mail_api(new: New) -> None:
    """The support world's `mail.messages` served by the mail API connector."""
    new.monkeypatch.setattr(support, "mail_server", mail_api_server)
    new.monkeypatch.setattr(
        support, "MailConfig", lambda **_: MailApiConfig(new.mail, SENDER, timeout=5.0)
    )


def replaced(new: New) -> None:
    """The release world's newsletter, website, analytics and site connectors, each the new
    provider's, under the credential names the processes reference."""
    m = new.monkeypatch
    m.setattr(release, "newsletter_server", mail_api_server)
    m.setattr(release, "NewsletterConfig", lambda *_, **__: MailApiConfig(new.mail, SENDER, 5.0))
    m.setattr(release, "website_server", content_server)
    m.setattr(release, "WebsiteConfig", lambda *_, **__: ContentConfig(new.content, timeout=5.0))
    m.setattr(release, "analytics_server", events_server)
    m.setattr(
        release,
        "AnalyticsConfig",
        lambda *_, **__: EventsConfig(new.events, product_analytics_service.PROJECT, timeout=5.0),
    )
    m.setattr(release, "sites_server", functions_server)
    m.setattr(
        release,
        "SitesConfig",
        lambda *_, **__: FunctionsConfig(new.functions, "example", "europe-west1", timeout=5.0),
    )
    new.credential("WEBSITE_TOKEN", CONTENT_TOKEN)
    new.credential("ANALYTICS_KEY", EVENTS_KEY)
    new.credential("SITES_TOKEN", new.functions_key)


# --- mail.messages over a mail service's API (ADR-0266) ----------------------------------------


async def test_b_3_02_runs_unchanged_on_a_mail_service_s_api(outside: Outside, new: New) -> None:
    mail_api(new)
    w = await World(outside).ready()
    version = await w.registered("B-3.02-draft-reply.yaml")
    replying(w, "You can export the report under Settings, then Export.")
    before = len(new.state("mail")["sent"])
    run = await w.start(version, message=mail_api_service.RECEIVED)
    assert len(new.state("mail")["sent"]) == before, "nothing sent before a person released it"
    run = await w.confirmed(run)
    finished(run)
    read = (await w.result(run, "read-message"))["output"]
    assert read["subject"], "the received message was read through the API"
    [reply] = new.state("mail")["sent"][before:]
    assert reply["to"] == [read["from"][0]]


# --- newsletter.broadcasts and website.posts (ADR-0266, ADR-0268) -------------------------------


async def test_b_9_07_runs_unchanged_on_a_mail_service_s_broadcasts(
    outside: Outside, cluster: str, systems: Systems, new: New
) -> None:
    replaced(new)
    w = await ReleaseWorld(
        outside, cluster, systems, answers={"You write the newsletter": "Sign-in works again."}
    ).ready()
    merged_change(outside, "fix/sign-in", "Fix sign-in")
    version = await w.registered("B-9.07-newsletter.yaml")
    inputs = {
        "audience": mail_api_service.SEGMENT,
        "from_name": "Example",
        "reply_to": "news@example.org",
    }
    run = await w.confirmed(await w.start(version, release="2.0", since_hours=336, **inputs))
    assert states(run)["send"] is StepState.WAITING_HUMAN
    before = list(new.state("mail")["broadcasts_sent"])
    run = await w.confirmed(await w.decided(run, "send"))
    finished(run)
    assert len(new.state("mail")["broadcasts_sent"]) == len(before) + 1
    assert (await w.result(run, "draft"))["output"]["recipients"] == 240


async def test_b_8_08_runs_unchanged_on_a_content_lake(
    outside: Outside, cluster: str, systems: Systems, new: New
) -> None:
    replaced(new)
    w = await ReleaseWorld(
        outside, cluster, systems, answers={"You write the website post": release.POST}
    ).ready()
    merged_change(outside, "fix/sign-in", "Fix sign-in")
    version = await w.registered("B-8.08-changelog-and-website.yaml")
    run = await w.confirmed(await w.start(version, release="2.0", since_hours=336))
    assert states(run)["publish"] is StepState.WAITING_HUMAN
    documents = new.state("content")["documents"]
    [draft] = [k for k in documents if k.startswith("drafts.")]
    assert documents[draft]["title"] == "What is new in 2.0", "drafted, not published"
    run = await w.confirmed(await w.decided(run, "publish"))
    finished(run)
    documents = new.state("content")["documents"]
    assert not [k for k in documents if k.startswith("drafts.")]
    assert documents[draft.removeprefix("drafts.")]["title"] == "What is new in 2.0"


# --- analytics.reports over an event analytics service (ADR-0267) -------------------------------


async def test_b_9_03_s_event_version_posts_the_weeks_as_the_service_gave_them(
    outside: Outside, cluster: str, systems: Systems, new: New
) -> None:
    replaced(new)
    w = await ReleaseWorld(
        outside, cluster, systems, answers={"You read a software product's use": "Steady."}
    ).ready()
    version = await w.registered("B-9.03-weekly-trends-events.yaml")
    before = len(chat_messages(systems))
    run = await w.confirmed(await w.start(version, address=CONVERSATION, event="sign up"))
    finished(run)
    weeks = (await w.result(run, "weeks"))["output"]["rows"]
    assert weeks and set(weeks[0]["metrics"]) == {"unique", "general"}
    [post] = chat_messages(systems)[before:]
    assert "Steady." in post["text"] and weeks[0]["dimensions"]["week"] in post["text"]


# --- deployment.sites on a functions platform (ADR-0269) ---------------------------------------


async def serving(new: New) -> str:
    """The version the function serves, read through the connector: a reading of the API is
    what completes a deployment in the fake, as time does on the platform."""
    connector = McpActionConnector(
        functions_server(FunctionsConfig(new.functions, "example", "europe-west1", timeout=5.0))
    )
    context = CallContext(
        tenant="t",
        identity="idn_release",
        run_id="run_look",
        step_id="look",
        attempt=1,
        idempotency_key=idempotency_key("run_look", "look", 1),
        credentials=(CredentialReference(name="SITES_TOKEN", injected_as="env"),),
    )
    result = await connector.call("deployment.sites.read", context, {"name": "web"})
    return str(result.output["live"])


@pytest.mark.parametrize("smoke", ["/health", "/missing"])
async def test_b_8_05_s_site_version_runs_unchanged_on_a_functions_platform(
    outside: Outside, cluster: str, systems: Systems, new: New, smoke: str
) -> None:
    replaced(new)
    w = await ReleaseWorld(outside, cluster, systems).ready()
    version = await w.registered("B-8.05-site-deployment.yaml")
    run = await w.confirmed(await w.start(version, site="web", build=SECOND, smoke_path=smoke))
    if smoke == "/missing":
        assert states(run)["rollback"] is StepState.WAITING_HUMAN
        assert new.state("functions")["functions"]["web"]["serving"] == SECOND
        run = await w.confirmed(await w.decided(run, "rollback"))
    finished(run)
    assert (await w.result(run, "before"))["output"]["live"] == FIRST
    assert await serving(new) == (FIRST if smoke == "/missing" else SECOND)


@pytest.mark.parametrize(("rate", "rolled_back"), [("0.001", False), ("0.2", True)])
async def test_b_8_06_s_hosted_version_runs_on_a_functions_platform(
    outside: Outside, cluster: str, systems: Systems, new: New, rate: str, rolled_back: bool
) -> None:
    replaced(new)
    w = await ReleaseWorld(outside, cluster, systems).ready()
    version = await w.registered("B-8.06-hosted-deployment.yaml")
    run = await w.confirmed(
        await w.start(
            version, target="web", build=SECOND, error_rate_query=rate, max_error_rate="0.02"
        )
    )
    if rolled_back:
        assert states(run)["rollback"] is StepState.WAITING_HUMAN
        run = await w.confirmed(await w.decided(run, "rollback"))
    finished(run)
    assert await serving(new) == (FIRST if rolled_back else SECOND)
