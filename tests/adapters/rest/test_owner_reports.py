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
