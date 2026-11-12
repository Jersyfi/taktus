"""The structure, its projects and sessions, and the tenant's administrative acts on the HTTP
surface (ADR-0275 to ADR-0277, ADR-0279; UC-1.4, UC-1.6, UC-1.8, UC-10.2)."""

from __future__ import annotations

import httpx

from taktus.components.identity.domain.model import Right

from .conftest import TENANT, Services

type Client = tuple[httpx.AsyncClient, Services, str]


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def admin(given: Services) -> str:
    """An identity whose role holds every administrative right."""
    _, key = await given.identities.add(TENANT, "idn_admin", (TENANT,), roles=("admin",))
    await given.identities.grant(TENANT, "admin", Right.ADMINISTER)
    await given.identities.grant(TENANT, "admin", Right.SHAPE_STRUCTURE)
    return key


async def test_a_moved_process_is_seen_in_its_new_team_and_not_its_old(client: Client) -> None:
    http, given, base = client
    key = await admin(given)
    for unit, parent in (("ops", TENANT), ("web", "ops"), ("data", "ops")):
        made = await http.post(
            f"{base}/structure/units",
            json={"id": unit, "name": unit, "parent": parent},
            headers=bearer(key),
        )
        assert made.status_code == 201, made.text
    _, wendy = await given.identities.add(TENANT, "idn_wendy", (TENANT, "ops", "web"))
    _, dana = await given.identities.add(TENANT, "idn_dana", (TENANT, "ops", "data"))
    placed = await http.put(
        f"{base}/structure/placements/process/invoices", json={"unit": "web"}, headers=bearer(key)
    )
    assert placed.status_code == 200, placed.text

    async def placements(who: str) -> list[str]:
        shown = (await http.get(f"{base}/structure", headers=bearer(who))).json()
        return [p["object"] for p in shown["placements"]]

    assert "invoices" in await placements(wendy) and "invoices" not in await placements(dana)
    await http.put(
        f"{base}/structure/placements/process/invoices", json={"unit": "data"}, headers=bearer(key)
    )
    assert "invoices" not in await placements(wendy) and "invoices" in await placements(dana)
    refused = await http.put(
        f"{base}/structure/placements/process/x", json={"unit": "web"}, headers=bearer(wendy)
    )
    assert refused.status_code == 403, "shaping the structure needs structure.shape"


async def test_a_project_is_created_referred_to_and_holds_one_session(client: Client) -> None:
    http, given, base = client
    key = await given.linked()
    made = await http.post(
        f"{base}/projects",
        json={"id": "notes", "name": "Notes", "circle": "alone"},
        headers=bearer(key),
    )
    assert made.status_code == 201, made.text
    assert made.json()["private"] is True
    referred = await http.post(
        f"{base}/projects/notes/references",
        json={"kind": "document", "link": "https://wiki.example.org/release", "title": "Release"},
        headers=bearer(key),
    )
    assert referred.status_code == 200, referred.text
    first = await http.post(f"{base}/projects/notes/session", headers=bearer(key))
    session = first.json()["id"]
    said = await http.post(
        f"{base}/sessions/{session}/turns",
        json={"text": "how do we release?"},
        headers=bearer(key),
    )
    assert said.status_code == 200, said.text
    assert "[source: Release — https://wiki.example.org/release]" in said.json()["shown"][0]
    await http.post(f"{base}/sessions/{session}/close", headers=bearer(key))
    again = await http.post(f"{base}/projects/notes/session", headers=bearer(key))
    assert again.json()["id"] == session and len(again.json()["turns"]) == 2
    planned = await http.post(
        f"{base}/sessions/{session}/plan",
        json={"goal": "release on Thursdays"},
        headers=bearer(key),
    )
    assert planned.status_code == 200 and planned.json()["kind"] == "plan"
    _, eve = await given.identities.add(TENANT, "idn_eve", (TENANT,))
    foreign = await http.post(f"{base}/projects/notes/session", headers=bearer(eve))
    assert foreign.status_code == 400, "a private project is its owner's alone"


async def test_the_administrative_acts_need_the_right_and_each_is_in_the_ledger(
    client: Client,
) -> None:
    http, given, base = client
    plain = await given.linked()
    assert (
        await http.get(f"{base}/administration/links", headers=bearer(plain))
    ).status_code == 403
    key = await admin(given)
    added = await http.post(
        f"{base}/administration/identities",
        json={"identity": "idn_new", "org_path": [], "roles": ["clerk"]},
        headers=bearer(key),
    )
    assert added.status_code == 201 and added.json()["key"].startswith("tka_")
    roles = await http.put(
        f"{base}/administration/identities/idn_new/roles",
        json={"roles": ["lead"]},
        headers=bearer(key),
    )
    assert roles.json()["roles"] == ["lead"]
    issued = await http.post(f"{base}/administration/identities/idn_new/key", headers=bearer(key))
    assert issued.status_code == 200
    granted = await http.put(
        f"{base}/administration/rights/lead/project.company", headers=bearer(key)
    )
    assert granted.json()["rights"] == ["project.company"]
    links = (await http.get(f"{base}/administration/links", headers=bearer(key))).json()["links"]
    (link,) = links
    revoked = await http.delete(f"{base}/administration/links/{link['id']}", headers=bearer(key))
    assert revoked.status_code == 200 and revoked.json()["revoked_by"] == "idn_admin"
    quota = await http.put(
        f"{base}/administration/units/sales",
        json={"concurrent_runs": 2, "budget": ["250eur"]},
        headers=bearer(key),
    )
    assert quota.status_code == 200, quota.text
    shown = (await http.get(f"{base}/administration/units", headers=bearer(key))).json()
    assert [q["org_unit"] for q in shown["quotas"]] == ["sales"]
    async with given.persistence.transaction(TENANT):
        entries = [e for e in await given.ledger.entries(TENANT) if e.refs.actor == "idn_admin"]
    kinds = {e.kind for e in entries}
    assert {
        "identity.created",
        "identity.roles_set",
        "identity.key_issued",
        "identity.right_granted",
        "identity.unlinked",
    } <= kinds, kinds
