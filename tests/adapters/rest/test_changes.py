"""`GET /changes`: the stream of changes on the HTTP surface (ADR-0055, `contracts/changes/v1`).

The account key is read from the `Authorization` header and nowhere else; a replica at its
maximum answers `503` with `Retry-After`; the response is Server-Sent Events, the snapshot first
with its position as the event's `id`; and a stream whose key stopped proving an identity ends.
Whether changes arrive within the 5 seconds is `tests/integration/test_live_changes.py`, against
a served process: an in-process transport collects a response whole.
"""

from __future__ import annotations

import asyncio
import json

import httpx

from taktus.components.reporting.domain.model import Reader, Scope, ScopeKind

from .conftest import TENANT, Services, a_run


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def test_the_key_is_accepted_in_the_header_only(
    client: tuple[httpx.AsyncClient, Services, str],
) -> None:
    http, given, base = client
    _, key = await given.identity.person(TENANT, "idn_ada")
    for asked in (
        http.get(f"{base}/changes"),
        http.get(f"{base}/changes", params={"key": key}),
        http.get(f"{base}/changes", params={"access_token": key}),
        http.get(f"{base}/changes", headers={"Authorization": f"Basic {key}"}),
    ):
        response = await asked
        assert response.status_code == 401
        assert response.headers["content-type"] == "application/problem+json"


async def test_a_process_and_a_run_together_are_refused(
    client: tuple[httpx.AsyncClient, Services, str],
) -> None:
    http, given, base = client
    _, key = await given.identity.person(TENANT, "idn_ada")
    response = await http.get(
        f"{base}/changes", params={"process": "p", "run": "run_1"}, headers=bearer(key)
    )
    assert response.status_code == 422


async def test_a_replica_at_its_maximum_answers_503_with_retry_after(
    client: tuple[httpx.AsyncClient, Services, str],
) -> None:
    http, given, base = client
    who, key = await given.identity.person(TENANT, "idn_ada")
    held = []

    async def again() -> None:
        return None

    for _ in range(2):  # the maximum the conftest configures
        held.append(
            await given.changes.open(
                Reader(tenant=TENANT, identity=who.identity),
                Scope(kind=ScopeKind.TENANT),
                None,
                again,
            )
        )
    response = await http.get(f"{base}/changes", headers=bearer(key))
    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"
    for events in held:
        await events.aclose()


async def test_the_stream_is_server_sent_events_and_ends_when_its_key_stops_proving(
    client: tuple[httpx.AsyncClient, Services, str],
) -> None:
    http, given, base = client
    await a_run(given)
    _, key = await given.identity.person(TENANT, "idn_ada")
    asked = asyncio.create_task(
        http.get(f"{base}/changes", params={"run": "run_1"}, headers=bearer(key))
    )
    await asyncio.sleep(0.3)  # a few heartbeats with a key that proves an identity
    await given.identities.issue_key(TENANT, "idn_ada")  # the old key stops working
    async with asyncio.timeout(5):
        response = await asked
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert "content-encoding" not in response.headers, "the stream is never compressed"
    blocks = response.text.split("\n\n")
    assert blocks[0] == "retry: 1000"
    event, position, data = blocks[1].split("\n")
    assert event == "event: snapshot"
    snapshot = json.loads(data.removeprefix("data: "))
    assert position == f"id: {snapshot['position']}"
    assert snapshot["scope"] == {"kind": "run", "id": "run_1"}
    assert [r["id"] for r in snapshot["runs"]] == ["run_1"]
    assert ": heartbeat" in blocks[2:], "the connection is kept open between changes"
    assert given.changes.open_streams == 0


async def test_a_stream_asked_for_its_position_alone_opens_with_no_run(
    client: tuple[httpx.AsyncClient, Services, str],
) -> None:
    """`snapshot=position`: the first event carries the position and `listed: false`, and no
    run (ADR-0317 §2)."""
    http, given, base = client
    await a_run(given)
    _, key = await given.identity.person(TENANT, "idn_ada")
    asked = asyncio.create_task(
        http.get(f"{base}/changes", params={"snapshot": "position"}, headers=bearer(key))
    )
    await asyncio.sleep(0.2)
    await given.identities.issue_key(TENANT, "idn_ada")
    async with asyncio.timeout(5):
        response = await asked
    _, position, data = response.text.split("\n\n")[1].split("\n")
    snapshot = json.loads(data.removeprefix("data: "))
    assert snapshot == {
        "position": position.removeprefix("id: "),
        "scope": {"kind": "tenant"},
        "runs": [],
        "listed": False,
    }
    refused = await http.get(f"{base}/changes", params={"snapshot": "all"}, headers=bearer(key))
    assert refused.status_code == 422


async def test_the_recent_changes_answer_what_the_stream_would_send(
    client: tuple[httpx.AsyncClient, Services, str],
) -> None:
    http, given, base = client
    await a_run(given)
    await a_run(given, "run_9", tenant="beta")
    _, key = await given.identity.person(TENANT, "idn_ada")
    response = await http.get(f"{base}/changes/recent", headers=bearer(key))
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["minutes"] == 60 and answer["complete"] is True
    [created] = answer["changes"]
    assert created["run"] == "run_1" and created["kind"] == "run.created"
    assert created["process"] == {"id": "p", "version": "1"}
    assert "actor" not in created
    for wrong in ({"minutes": 61}, {"minutes": 0}, {"process": "p", "run": "run_1"}):
        assert (
            await http.get(f"{base}/changes/recent", params=wrong, headers=bearer(key))
        ).status_code == 422
    assert (await http.get(f"{base}/changes/recent")).status_code == 401
