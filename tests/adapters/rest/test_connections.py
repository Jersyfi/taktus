"""Writing on a connection, and the queries a step sent, on the HTTP surface (UC-5.6, ADR-0262).

A new connection reads only; the owner grants writing and withdraws it, and anyone else is
refused with 403; a capability that needs no grant is not found. A step's queries are read, with
their text, by a reader who may see the run, and by nobody else.
"""

from __future__ import annotations

import httpx

from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerRefs

from .conftest import OTHER, TENANT, Services, a_run

type Client = tuple[httpx.AsyncClient, Services, str]

WAREHOUSE = "warehouse.queries"


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def test_the_owner_grants_and_withdraws_writing_and_nobody_else_may(client: Client) -> None:
    http, given, base = client
    _, owner = await given.identity.person(TENANT, "idn_owner")
    await given.identity.directory.set_roles(TENANT, "idn_owner", ["owner"])
    _, analyst = await given.identity.person(TENANT, "idn_analyst")
    url = f"{base}/connections/{WAREHOUSE}/grant"

    fresh = (await http.get(url, headers=bearer(analyst))).json()
    assert fresh == {"capability": WAREHOUSE, "granted": False, "changed_at": None}

    refused = await http.put(url, headers=bearer(analyst))
    assert refused.status_code == 403, refused.text
    assert (await http.get(url, headers=bearer(owner))).json()["granted"] is False

    granted = await http.put(url, headers=bearer(owner))
    assert granted.status_code == 200, granted.text
    assert granted.json()["granted"] is True
    assert await given.decisions.connections.granted(TENANT, WAREHOUSE)

    withdrawn = await http.delete(url, headers=bearer(owner))
    assert withdrawn.status_code == 200 and withdrawn.json()["granted"] is False
    assert not await given.decisions.connections.granted(TENANT, WAREHOUSE)

    async with given.persistence.transaction(TENANT):
        kinds = [(e.kind, e.outcome, e.refs.actor) for e in await given.ledger.entries(TENANT)]
    assert ("connection.refused", "role", "idn_analyst") in kinds
    assert ("connection.granted", "granted", "idn_owner") in kinds
    assert ("connection.withdrawn", "withdrawn", "idn_owner") in kinds


async def test_a_connection_that_needs_no_grant_is_not_found_and_a_key_is_needed(
    client: Client,
) -> None:
    http, given, base = client
    _, owner = await given.identity.person(TENANT, "idn_owner")
    await given.identity.directory.set_roles(TENANT, "idn_owner", ["owner"])
    other = await http.put(f"{base}/connections/chat.threads/grant", headers=bearer(owner))
    assert other.status_code == 404
    assert (await http.put(f"{base}/connections/{WAREHOUSE}/grant")).status_code == 401


async def test_a_steps_queries_are_read_with_their_text_where_the_run_is_seen(
    client: Client,
) -> None:
    http, given, base = client
    await a_run(given)
    query = "SELECT step, users FROM signups_funnel"
    digest = await given.objects.put(
        b'{"input":{"limit":10,"query":"'
        + query.encode()
        + b'"},"operation":"warehouse.queries.run"}'
    )
    async with given.persistence.transaction(TENANT):
        await given.ledger.record(
            TENANT,
            Fact(
                kind="query.sent",
                refs=LedgerRefs(tenant=TENANT, run_id="run_1", step_id="a"),
                outcome="sent",
                content_digest=digest,
            ),
        )
    _, reader = await given.identity.person(TENANT, "idn_reader")
    url = f"{base}/levels/runs/run_1/steps/a/queries"
    answer = await http.get(url, headers=bearer(reader))
    assert answer.status_code == 200, answer.text
    [sent] = answer.json()["queries"]
    assert sent["query"] == query and sent["operation"] == "warehouse.queries.run"
    assert sent["digest"] == digest

    _, stranger = await given.identity.person(OTHER, "idn_stranger")
    assert (await http.get(url, headers=bearer(stranger))).status_code == 404
    missing = await http.get(f"{base}/levels/runs/run_1/steps/zz/queries", headers=bearer(reader))
    assert missing.status_code == 404
    assert (await http.get(url)).status_code == 401
