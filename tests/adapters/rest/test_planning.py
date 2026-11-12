"""The plan dialogue and the coach on the HTTP surface (ADR-0279; UC-1.2, UC-13.1, UC-10.3,
UC-13.3): a person opens a plan, answers the guided questions or sets the fields in the expert
mode, and commissions it; the coach shows a person their own hints only."""

from __future__ import annotations

from datetime import timedelta

import httpx

from taktus.shared.v1 import Command, Intent, ReplyTo

from .conftest import TENANT, Services
from .test_agent_surface import registered

type Client = tuple[httpx.AsyncClient, Services, str]

STEPS = [
    {
        "id": "read",
        "method": "rule",
        "reason": "a rule reads the invoice",
        "rejected": [],
        "exactness": "exact",
    }
]


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def test_a_plan_is_worked_out_in_the_guided_mode_and_commissioned(client: Client) -> None:
    http, given, base = client
    key = await given.linked()
    opened = await http.post(
        f"{base}/plans", json={"said": "answer supplier invoices"}, headers=bearer(key)
    )
    assert opened.status_code == 201, opened.text
    view = opened.json()
    draft = view["draft"]["id"]
    assert view["question"]["field"] == "steps", "the goal is what the person said"
    assert "A step is" in view["question"]["explains"], "the term is explained where it appears"

    answers = [
        ("steps", STEPS, None),
        ("due", "2026-12-01T09:00:00+00:00", None),
        ("autonomy_level", 2, None),
        ("autonomy_reason", "a person confirms every reply", None),
        ("estimates", {"figure": 2, "unit": "seconds", "basis": "the last 30 runs"}, "read"),
    ]
    for field, value, step in answers:
        asked = await http.get(f"{base}/plans/{draft}?mode=guided", headers=bearer(key))
        assert asked.json()["question"]["field"] == field
        answered = await http.post(
            f"{base}/plans/{draft}/answers",
            json={"field": field, "value": value, "step_id": step},
            headers=bearer(key),
        )
        assert answered.status_code == 200, answered.text
    done = answered.json()
    assert done["question"] is None and done["missing"] == []
    assert done["estimates"] == ["step read: 2 seconds, computed from the last 30 runs"]
    assert any(s["field"] == "results_in" and not s["asked"] for s in done["settings"])

    plan = await http.post(f"{base}/plans/{draft}/commission", headers=bearer(key))
    assert plan.status_code == 200, plan.text
    assert plan.json()["status"] == "commissioned" and plan.json()["id"] == f"{draft}@v6"


async def test_the_guided_mode_offers_safe_levels_and_the_expert_mode_sets_any(
    client: Client,
) -> None:
    http, given, base = client
    key = await given.linked()
    draft = (await http.post(f"{base}/plans", json={"said": "x"}, headers=bearer(key))).json()
    path = f"{base}/plans/{draft['draft']['id']}"
    high = await http.post(
        f"{path}/answers", json={"field": "autonomy_level", "value": 3}, headers=bearer(key)
    )
    assert high.status_code == 400 and "level 1 or 2" in high.json()["detail"]
    expert = await http.patch(path, json={"fields": {"autonomy_level": 3}}, headers=bearer(key))
    assert expert.status_code == 200 and expert.json()["question"] is None
    assert expert.json()["draft"]["autonomy_level"] == 3


async def test_commissioning_a_draft_that_lacks_a_part_is_refused_naming_it(
    client: Client,
) -> None:
    http, given, base = client
    key = await given.linked()
    draft = (await http.post(f"{base}/plans", json={"said": "x"}, headers=bearer(key))).json()
    refused = await http.post(
        f"{base}/plans/{draft['draft']['id']}/commission", headers=bearer(key)
    )
    assert refused.status_code == 400
    assert "the date it is due" in refused.json()["missing"]
    assert "the agent's name" not in refused.json()["missing"], "a plan that is no agent"
    _, bob = await given.identity.directory.add(TENANT, "idn_eve", (TENANT,))
    foreign = await http.get(f"{base}/plans/{draft['draft']['id']}", headers=bearer(bob))
    assert foreign.status_code == 404, "a draft is its person's"


async def test_an_agent_is_drafted_in_the_dialogue_and_registered_when_commissioned(
    client: Client,
) -> None:
    http, given, base = client
    key = await given.linked()
    await registered(given)
    opened = await http.post(
        f"{base}/plans",
        json={"said": "read the daily figures", "agent": True},
        headers=bearer(key),
    )
    assert opened.status_code == 201, opened.text
    draft = opened.json()["draft"]["id"]
    refused = await http.post(f"{base}/plans/{draft}/commission", headers=bearer(key))
    assert refused.status_code == 400
    assert {"the agent's name", "the process it runs"} <= set(refused.json()["missing"])

    answers = [
        ("steps", "daily@1", None),
        ("agent.name", "figures", None),
        ("agent.instructions", "Read the figures and say what changed.", None),
        ("agent.model", "summarising", None),
        ("agent.sources", "figures", None),
        ("due", "2026-12-01T09:00:00+00:00", None),
        ("autonomy_level", 1, None),
        ("autonomy_reason", "it proposes; a person reads and acts", None),
        ("estimates", {"figure": 1, "basis": "a rule's last runs"}, "one"),
    ]
    for field, value, step in answers:
        asked = await http.get(f"{base}/plans/{draft}?mode=guided", headers=bearer(key))
        assert asked.json()["question"]["field"] == field, asked.json()["question"]
        answered = await http.post(
            f"{base}/plans/{draft}/answers",
            json={"field": field, "value": value, "step_id": step},
            headers=bearer(key),
        )
        assert answered.status_code == 200, answered.text
    assert answered.json()["missing"] == [] and answered.json()["question"] is None

    plan = await http.post(f"{base}/plans/{draft}/commission", headers=bearer(key))
    assert plan.status_code == 200, plan.text
    assert plan.json()["agent"] == "figures@1" and plan.json()["status"] == "commissioned"
    assert given.built_agents is not None
    core = await given.built_agents.active_core(TENANT, "figures")
    assert core is not None and core.flow == "daily" and core.autonomy_level == 1
    async with given.persistence.transaction(TENANT):
        proposed = await given.ledger.of_kinds(TENANT, ("agent.core_proposed",))
    assert [(e.refs.actor, e.refs.plan_id) for e in proposed] == [("idn_ada", plan.json()["id"])]

    again = await http.post(f"{base}/plans/{draft}/commission", headers=bearer(key))
    assert again.status_code == 400 and again.json()["reason"] == "exists"


async def test_the_coach_shows_a_person_their_own_hints_only_and_is_switched_off(
    client: Client,
) -> None:
    http, given, base = client
    key = await given.linked()
    _, eve = await given.identity.directory.add(TENANT, "idn_eve", (TENANT,))
    shown = await http.get(f"{base}/coach", headers=bearer(key))
    assert shown.status_code == 200
    assert shown.json()["settings"] == {
        "on": True,
        "hints_per_week": 1,
        "default_hints_per_week": 1,
    }
    start = given.clock.now()
    async with given.persistence.transaction(TENANT):
        commands = given.workspace.planning._commands
        for week in range(4):
            await commands.put(
                TENANT,
                Command(
                    id=f"cmd_{week}",
                    channel="channel.chat",
                    identity="idn_ada",
                    org_path=(TENANT,),
                    intent=Intent(raw="summarise the open invoices"),
                    reply_to=ReplyTo(channel="channel.chat", address="C1"),
                    received_at=start + timedelta(days=7 * week, seconds=1),
                ),
            )
    given.clock.current = start + timedelta(days=22)
    hints = (await http.get(f"{base}/coach", headers=bearer(key))).json()["hints"]
    assert len(hints) == 1, hints
    assert (await http.get(f"{base}/coach", headers=bearer(eve))).json()["hints"] == []
    dismissed = await http.post(f"{base}/coach/hints/{hints[0]['id']}/dismiss", headers=bearer(key))
    assert dismissed.status_code == 200 and dismissed.json()["hints"] == []
    off = await http.put(f"{base}/coach", json={"on": False}, headers=bearer(key))
    assert off.json()["settings"]["on"] is False
