"""A person's conversation with Taktus on the HTTP surface (UC-1.14, ADR-0325).

A key is needed; without a conversation process a turn is refused, saying which setting names
one; an act read back is done only on its person's yes, once, and nobody else settles it.
`tests/composition/test_conversation.py` runs a turn end to end.
"""

from __future__ import annotations

import httpx

from .conftest import TENANT, Services

type Client = tuple[httpx.AsyncClient, Services, str]


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def test_without_a_conversation_process_a_turn_is_refused_and_a_key_is_needed(
    client: Client,
) -> None:
    http, given, base = client
    assert (await http.get(f"{base}/conversation")).status_code == 401
    key = await given.linked()
    view = await http.get(f"{base}/conversation", headers=bearer(key))
    assert view.status_code == 200
    assert view.json()["available"] is False and view.json()["turns"] == []
    assert "open_plan" in view.json()["acts_offered"]
    said = await http.post(f"{base}/conversation", json={"text": "hello"}, headers=bearer(key))
    assert said.status_code == 400 and "TAKTUS_CONVERSATION_PROCESS" in said.json()["detail"]


async def test_an_act_read_back_is_done_only_on_its_persons_yes_and_once(client: Client) -> None:
    http, given, base = client
    key = await given.linked()
    who = await given.identities.authenticate(key)
    assert who is not None
    conversation = await given.conversations.said(TENANT, who.identity, "channel.web", "plan it")
    _, act = await given.conversations.answered(
        TENANT,
        conversation.id,
        "I can open a plan.",
        run=None,
        act=("open_plan", {"said": "answer invoices"}, "Open a plan draft for “answer invoices”."),
    )
    assert act is not None

    _, other = await given.identity.directory.add(TENANT, "idn_eve", (TENANT,))
    foreign = await http.post(
        f"{base}/conversation/acts/{act.id}", json={"yes": True}, headers=bearer(other)
    )
    assert foreign.status_code == 400 and "no act" in foreign.json()["detail"]

    path = f"{base}/conversation/acts/{act.id}"
    done = await http.post(path, json={"yes": True}, headers=bearer(key))
    assert done.status_code == 200, done.text
    assert done.json()["state"] == "done" and done.json()["links"]["draft"]
    drafts = (await http.get(f"{base}/plans", headers=bearer(key))).json()["plans"]
    assert [d["draft"]["goal"] for d in drafts] == ["answer invoices"]
    again = await http.post(path, json={"yes": True}, headers=bearer(key))
    assert again.status_code == 400 and "done already" in again.json()["detail"]

    view = (await http.get(f"{base}/conversation", headers=bearer(key))).json()
    assert [t["speaker"] for t in view["turns"]] == ["person", "taktus", "taktus"]
    assert view["acts"][0]["state"] == "done"
