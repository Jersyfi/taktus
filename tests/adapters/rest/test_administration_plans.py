"""An administrative act asked in dialogue, carried out as a plan; an update of Taktus prepared
in dialogue and commissioned by a person; the instance's health and the backup's listing
(ADR-0295, ADR-0296; UC-10.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from taktus.adapters.driving.rest.operation import backup_view
from taktus.components.reporting.application.service import BackupWatched
from taktus.components.reporting.domain.model import BackupRun, BackupState

from .conftest import TENANT, Services
from .test_structure_and_administration import admin, bearer

type Client = tuple[httpx.AsyncClient, Services, str]

LATER = (datetime.now(UTC) + timedelta(days=2)).date().isoformat()
COMPLETE = {
    "due": LATER,
    "autonomy_level": 1,
    "autonomy_reason": "a person carries out every act of the administration",
}


async def entries(given: Services) -> list[tuple[str, str | None]]:
    async with given.persistence.transaction(TENANT):
        return [(e.kind, e.refs.actor) for e in await given.ledger.entries(TENANT)]


async def test_an_administrative_act_asked_in_dialogue_is_carried_out_as_a_plan_with_the_same_right(
    client: Client,
) -> None:
    http, given, base = client
    key = await admin(given)
    plain = await given.linked()
    await given.identities.add(TENANT, "idn_new", (TENANT,), roles=("clerk",))

    async def drafted(who: str) -> str:
        opened = await http.post(
            f"{base}/plans",
            json={
                "said": "make idn_new a lead",
                "act": "identity.roles",
                "arguments": {"identity": "idn_new"},
            },
            headers=bearer(who),
        )
        assert opened.status_code == 201, opened.text
        shown = opened.json()
        assert shown["question"]["field"] == "administration.roles", "the guided mode asks"
        assert [s["method"] for s in shown["draft"]["steps"]] == ["rule"]
        draft = shown["draft"]["id"]
        answered = await http.post(
            f"{base}/plans/{draft}/answers",
            json={"field": "administration.roles", "value": "lead"},
            headers=bearer(who),
        )
        assert answered.status_code == 200, answered.text
        done = await http.patch(
            f"{base}/plans/{draft}", json={"fields": COMPLETE}, headers=bearer(who)
        )
        assert done.status_code == 200 and done.json()["missing"] == [], done.text
        return str(draft)

    refused = await http.post(
        f"{base}/plans/{await drafted(plain)}/commission", headers=bearer(plain)
    )
    assert refused.status_code == 403, "a plan needs the right the act needs by hand"
    assert "tenant.administer" in refused.json()["detail"]
    assert (await given.identities.identity(TENANT, "idn_new")).roles == ("clerk",)  # type: ignore[union-attr]
    assert not [k for k, _ in await entries(given) if k == "plan.commissioned"], "nothing written"

    commissioned = await http.post(
        f"{base}/plans/{await drafted(key)}/commission", headers=bearer(key)
    )
    assert commissioned.status_code == 200, commissioned.text
    assert (await given.identities.identity(TENANT, "idn_new")).roles == ("lead",)  # type: ignore[union-attr]
    recorded = await entries(given)
    tail = [e for e in recorded if e[0] != "plan.revised"][-3:]
    assert tail == [
        ("plan.commissioned", "idn_admin"),
        ("administration.carried_out", "idn_admin"),
        ("identity.roles_set", "idn_admin"),
    ], "the plan, the act with its target, and the act's own entry, each naming who did it"


async def test_an_act_that_stays_by_hand_is_not_drafted_and_says_why(client: Client) -> None:
    http, given, base = client
    key = await admin(given)
    refused = await http.post(
        f"{base}/plans",
        json={"said": "a key for idn_new", "act": "identity.key"},
        headers=bearer(key),
    )
    assert refused.status_code == 400
    assert "a key never passes through a plan's record" in refused.json()["detail"]


async def test_an_update_prepared_in_dialogue_is_commissioned_by_a_person_and_applies_nothing(
    client: Client,
) -> None:
    http, given, base = client
    key = await admin(given)
    plain = await given.linked()
    assert (
        await http.post(
            f"{base}/administration/update", json={"to": "1.0.1"}, headers=bearer(plain)
        )
    ).status_code == 403
    assert (
        await http.post(f"{base}/administration/update", json={"to": "next"}, headers=bearer(key))
    ).status_code == 422
    prepared = await http.post(
        f"{base}/administration/update", json={"to": "1.0.1"}, headers=bearer(key)
    )
    assert prepared.status_code == 201, prepared.text
    draft = prepared.json()["draft"]
    assert [(s["id"], s["method"]) for s in draft["steps"]] == [
        ("backup", "human"),
        ("upgrade", "human"),
        ("check", "human"),
    ], "every step is a person's: no instance updates itself"
    assert "section 5" in draft["steps"][2]["reason"], "the way back needs no Taktus"
    before = await entries(given)
    unfinished = await http.post(f"{base}/plans/{draft['id']}/commission", headers=bearer(key))
    assert unfinished.status_code == 400, "not applied until a person completed and commissioned"
    assert await entries(given) == before
    await http.patch(f"{base}/plans/{draft['id']}", json={"fields": COMPLETE}, headers=bearer(key))
    commissioned = await http.post(f"{base}/plans/{draft['id']}/commission", headers=bearer(key))
    assert commissioned.status_code == 200, commissioned.text
    kinds = [k for k, _ in await entries(given)]
    assert kinds[-2:] == ["plan.commissioned", "instance.update_commissioned"]
    assert ("instance.update_commissioned", "idn_admin") in await entries(given)


async def test_the_instance_health_needs_the_right_and_says_why_it_is_not_ready(
    client: Client,
) -> None:
    http, given, base = client
    key = await admin(given)
    plain = await given.linked()
    assert (
        await http.get(f"{base}/administration/health", headers=bearer(plain))
    ).status_code == 403
    given.not_ready_reason = "the database did not answer"
    shown = (await http.get(f"{base}/administration/health", headers=bearer(key))).json()
    assert shown["ready"] is False and shown["reason"] == "the database did not answer"
    assert shown["roles"] == ["api", "runner"] and shown["backup"] == "not_recorded"
    assert shown["alerts_in_effect"] == 0 and shown["incidents_open"] == 0
    assert shown["release"]


def test_the_backup_lists_its_newest_runs_with_when_each_ran() -> None:
    at = datetime(2026, 11, 12, 2, 0, tzinfo=UTC)
    watched = BackupWatched(
        state=BackupState(
            watched_since=None,
            last_ok=BackupRun(name="taktus-20261112T020000Z", at=at),
            recent=(
                BackupRun(name="taktus-20261112T020000Z", at=at),
                BackupRun(
                    name="taktus-20261111T020000Z",
                    at=at - timedelta(days=1),
                    reason="store",
                    outcome="failed",
                ),
            ),
        ),
        next_due=None,
        alert=None,
    )
    assert backup_view(watched)["listed"] == [
        {"name": "taktus-20261112T020000Z", "at": at.isoformat(), "outcome": "ok", "reason": None},
        {
            "name": "taktus-20261111T020000Z",
            "at": (at - timedelta(days=1)).isoformat(),
            "outcome": "failed",
            "reason": "store",
        },
    ]
