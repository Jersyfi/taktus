"""The reports to the owner on the control plane's surface (ADR-0045): the view with its
history and the repository text, read by the owner and whom they named only; and an answer
written in a report's thread taken through the webhook intake, never kept as a command."""

from __future__ import annotations

from datetime import timedelta

import httpx

from taktus.components.reporting.application.service import ConfigureChannel, RaiseReport
from taktus.components.reporting.domain.model import ReportKind
from taktus.ports.connector import Intake, IntakeResult

from .conftest import TENANT, Services
from .test_surface import is_problem

type Client = tuple[httpx.AsyncClient, Services, str]

OWNER = "idn_owner"
NAMED = "idn_deputy"


async def configured(given: Services) -> dict[str, dict[str, str]]:
    keys: dict[str, dict[str, str]] = {}
    for name in (OWNER, NAMED, "idn_outsider"):
        _, key = await given.identities.add(TENANT, name, (TENANT,), roles=("owner",))
        keys[name] = {"Authorization": f"Bearer {key}"}
    await given.owner.configure.execute(
        ConfigureChannel(
            tenant=TENANT,
            document={
                "owner": OWNER,
                "named": [NAMED],
                "channel": "channel.repo",
                "address": "acme/taktus#412",
                "language": "de",
            },
            actor="operator",
        )
    )
    await given.owner.raising.execute(
        RaiseReport(
            tenant=TENANT,
            id="need_0001",
            kind=ReportKind.NEED,
            title="A token for the live test",
            needed=["A token in the environment `live`."],
            steps=["Create it.", "Store it."],
            standing_still=["The live test."],
            due=given.clock.now().date() + timedelta(days=7),
        )
    )
    return keys


async def test_every_report_route_needs_an_account_key_of_the_owner_or_someone_named(
    client: Client,
) -> None:
    http, given, base = client
    keys = await configured(given)
    for path in ("/owner/reports", "/owner/reports/need_0001", "/owner/reports/need_0001/text"):
        is_problem(await http.get(f"{base}{path}"), 401)
        is_problem(await http.get(f"{base}{path}", headers=keys["idn_outsider"]), 403)
        assert (await http.get(f"{base}{path}", headers=keys[OWNER])).status_code == 200
        assert (await http.get(f"{base}{path}", headers=keys[NAMED])).status_code == 200
    is_problem(await http.get(f"{base}/owner/reports/nothing", headers=keys[OWNER]), 404)


async def test_the_view_and_the_repository_text_carry_the_same_report(client: Client) -> None:
    http, given, base = client
    keys = await configured(given)
    listed = (await http.get(f"{base}/owner/reports", headers=keys[OWNER])).json()["reports"]
    [seen] = listed
    assert seen["id"] == "need_0001" and seen["needed"] == ["A token in the environment `live`."]
    assert [h["event"] for h in seen["history"]] == ["raised", "message_delivered"]
    assert all(h["by_you"] is False for h in seen["history"])
    text = await http.get(f"{base}/owner/reports/need_0001/text", headers=keys[OWNER])
    assert text.headers["content-type"].startswith("text/markdown")
    assert "# need_0001 — A token for the live test" in text.text
    assert f"**Needed by:** {seen['due']}" in text.text


async def test_an_answer_in_a_report_s_thread_is_taken_and_kept_as_no_event(
    client: Client,
) -> None:
    http, given, base = client
    await configured(given)
    report = await given.owner.queries.one(TENANT, "need_0001")
    assert report is not None and report.message() is not None
    thread = report.message().thread  # type: ignore[union-attr]
    who, _ = await given.identity.person(TENANT, "idn_writer")
    code = await given.identity.code(who)
    assert (await given.identities.unknown_sender("channel.repo", "300300", code)).linked
    given.connector.answer = IntakeResult(
        accepted=Intake.model_validate(
            {
                "event_id": "dlv_answer",
                "event": "issue_comment.created",
                "channel": "channel.repo",
                "sender": {"account": "300300", "kind": "person"},
                "intent": {"raw": "erledigt"},
                "context": {},
                "reply_to": {
                    "channel": "channel.repo",
                    "address": "acme/taktus#412",
                    "thread": thread,
                },
                "occurred_at": "2026-09-16T08:15:00Z",
            }
        )
    )
    response = await http.post(f"{base}/intake/channel.repo", content="{}")
    assert response.status_code == 202
    assert response.json() == {"answer": "not_filed", "replied": True}
    async with given.persistence.transaction(TENANT):
        assert await given.events.list(TENANT) == []


# --- the old link, and the answer given on the report's page (ADR-0120) -------------------------


async def test_a_browser_without_a_key_is_sent_to_the_report_s_page(client: Client) -> None:
    http, given, base = client
    await configured(given)
    browser = {"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
    sent = await http.get(f"{base}/owner/reports/need_0001", headers=browser)
    assert sent.status_code == 303
    assert sent.headers["location"] == "../../app/#/reports/need_0001"
    page = httpx.URL(f"{base}/owner/reports/need_0001").join(sent.headers["location"])
    assert page.path == f"{httpx.URL(base).path.rstrip('/')}/app/"
    assert page.fragment == "/reports/need_0001"


async def test_a_client_asking_for_json_keeps_today_s_answer(client: Client) -> None:
    http, given, base = client
    keys = await configured(given)
    as_json = {"Accept": "application/json"}
    is_problem(await http.get(f"{base}/owner/reports/need_0001", headers=as_json), 401)
    is_problem(await http.get(f"{base}/owner/reports/need_0001"), 401)
    with_key = {**keys[OWNER], "Accept": "text/html"}
    seen = await http.get(f"{base}/owner/reports/need_0001", headers=with_key)
    assert seen.status_code == 200 and seen.json()["id"] == "need_0001"


async def test_a_report_is_answered_on_its_page_and_filed_once_confirmed(client: Client) -> None:
    http, given, base = client
    keys = await configured(given)
    said = len(given.deliveries.said)
    path = f"{base}/owner/reports/need_0001"
    for route in ("answer", "confirm"):
        is_problem(await http.post(f"{path}/{route}", json={"confirmed": True}), 401)
    body = {"option": "done"}
    outsider = keys["idn_outsider"]
    is_problem(await http.post(f"{path}/answer", json=body, headers=outsider), 403)
    elsewhere = f"{base}/owner/reports/nothing/answer"
    is_problem(await http.post(elsewhere, json=body, headers=keys[OWNER]), 404)
    is_problem(await http.post(f"{path}/answer", json={}, headers=keys[OWNER]), 422)
    confirmed = {"confirmed": True}
    is_problem(await http.post(f"{path}/confirm", json=confirmed, headers=keys[OWNER]), 409)
    read = (await http.post(f"{path}/answer", json=body, headers=keys[OWNER])).json()
    assert read["outcome"] == "reflected" and read["message"]
    assert read["report"]["state"] == "reflected" and read["report"]["reading"]["by_you"]
    done = await http.post(f"{path}/confirm", json=confirmed, headers=keys[OWNER])
    assert done.json()["outcome"] == "filed"
    assert done.json()["report"]["filed"]["by_you"] is True
    assert len(given.deliveries.said) == said, "nothing is said in the channel"
