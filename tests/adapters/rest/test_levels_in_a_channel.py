"""The run level asked for in the owner-facing channel says what the web app is handed (UC-6.10
*beyond the web app*, ADR-0069, issue #193).

The web app draws `GET /levels/runs/{id}`. The owner's conversation, a chat that cannot draw
it, receives the text equivalent of the same level — every element's text, with the same states
and figures — and the link under which the web app draws that run live, under the instance's
prefix. A run the asker may not see is answered there as one that does not exist.
"""

from __future__ import annotations

from datetime import timedelta

import httpx

from taktus.components.reporting.application.service import ConfigureChannel
from taktus.components.run.domain.model import StepRun, StepState
from taktus.ports.connector import Intake
from taktus.shared.v1 import Consumption, Method

from .conftest import OTHER, TENANT, Services, a_run

type Client = tuple[httpx.AsyncClient, Services, str]

CHAT = "channel.chat"
CONVERSATION = "D0000000001"


def message(text: str, event: str) -> Intake:
    return Intake.model_validate(
        {
            "event_id": event,
            "event": "message.posted",
            "channel": CHAT,
            "sender": {"account": "U0000000001", "kind": "person"},
            "intent": {"raw": text},
            "context": {"conversation": CONVERSATION},
            "reply_to": {"channel": CHAT, "address": CONVERSATION, "thread": event},
            "occurred_at": "2026-10-10T09:00:00Z",
        }
    )


async def test_the_owner_s_chat_receives_the_run_level_s_text_and_a_link_to_it_live(
    client: Client,
) -> None:
    http, given, base = client
    run = await a_run(given)
    now = given.clock.now()
    ran = run.model_copy(
        update={
            "step_runs": (
                StepRun(
                    step_id="a",
                    index=0,
                    method=Method.RULE,
                    state=StepState.SUCCEEDED,
                    consumption=Consumption(compute_seconds=1.5, resource_class="cpu.small"),
                    started_at=now,
                    finished_at=now + timedelta(seconds=2),
                ),
            )
        }
    )
    async with given.persistence.transaction(TENANT):
        await given.runs.put(TENANT, ran)
    who, key = await given.identity.person(TENANT, "idn_owner")
    owner = who.identity
    control_plane = f"http://taktus.test{base}"
    await given.owner.configure.execute(
        ConfigureChannel(
            tenant=TENANT,
            document={
                "owner": owner,
                "channel": CHAT,
                "address": CONVERSATION,
                "language": "en",
                "view_base": control_plane,
            },
            actor="operator",
        )
    )
    answer = await http.get(f"{base}/levels/runs/run_1", headers={"Authorization": f"Bearer {key}"})
    assert answer.status_code == 200
    level = answer.json()

    taken = await given.owner.answers.take(
        TENANT, message("show run run_1", "Ev1"), owner, who.roles
    )

    assert taken is not None and taken.outcome == "shown" and taken.replied
    [said] = given.deliveries.said
    assert said.text.splitlines() == [
        level["run"]["text"],
        *(f"• {step['text']}" for step in level["steps"]),
        "",
        f"Live: {control_plane}/app/#/runs/run_1",
    ]
    assert [s["state"] for s in level["steps"]] == ["succeeded"]
    for figure in (*level["run"]["consumed"], *level["steps"][0]["consumption"]):
        assert figure["name"] in said.text
    assert "compute_seconds.cpu.small 1.5" in said.text

    elsewhere = run.model_copy(update={"id": "run_2", "tenant": OTHER})
    async with given.persistence.transaction(OTHER):
        await given.runs.put(OTHER, elsewhere)
    unseen = await given.owner.answers.take(
        TENANT, message("show run run_2", "Ev2"), owner, who.roles
    )
    missing = await given.owner.answers.take(
        TENANT, message("show run run_9", "Ev3"), owner, who.roles
    )
    assert unseen is not None and missing is not None
    assert unseen.outcome == missing.outcome == "not_shown"
    assert given.deliveries.said[1].text == given.deliveries.said[2].text
    assert "run_2" not in given.deliveries.said[1].text
