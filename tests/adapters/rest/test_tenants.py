"""The administration of tenants on the HTTP surface (ADR-0104): only for the holder of the
instance's administration key, an identifier Taktus generates, a name that may change, and a
tenant the instance serves from the moment it was created."""

from __future__ import annotations

import httpx

from taktus.ports.configuration import Secret

from .conftest import OTHER, TENANT, Services
from .test_surface import is_problem

type Client = tuple[httpx.AsyncClient, Services, str]

KEY = "adm-a-random-value-for-this-test"
ADMIN = {"Authorization": f"Bearer {KEY}"}


async def test_without_a_key_configured_the_routes_say_how_to_enable_them(client: Client) -> None:
    http, _, base = client
    problem = is_problem(await http.get(f"{base}/administration/tenants", headers=ADMIN), 404)
    assert "TAKTUS_ADMINISTRATION_KEY_FILE" in str(problem["detail"])
    refused = await http.post(f"{base}/administration/tenants", json={"name": "Acme"})
    is_problem(refused, 404)


async def test_only_the_administration_key_is_admitted(client: Client) -> None:
    http, given, base = client
    given.administration_key = Secret(KEY)
    for headers in ({}, {"Authorization": "Bearer another"}, {"Authorization": KEY}):
        is_problem(await http.get(f"{base}/administration/tenants", headers=headers), 401)
    key = await given.linked()
    person = {"Authorization": f"Bearer {key}"}
    is_problem(await http.get(f"{base}/administration/tenants", headers=person), 401)


async def test_a_tenant_is_created_with_a_generated_identifier_and_served_at_once(
    client: Client,
) -> None:
    http, given, base = client
    given.administration_key = Secret(KEY)
    listed = await http.get(f"{base}/administration/tenants", headers=ADMIN)
    assert [t["id"] for t in listed.json()["tenants"]] == [TENANT, OTHER]

    created = await http.post(
        f"{base}/administration/tenants",
        json={"name": "Acme Software", "by": "idn_admin", "id": "acme"},
        headers=ADMIN,
    )
    assert created.status_code == 422, "a request never names the identifier"
    created = await http.post(
        f"{base}/administration/tenants",
        json={"name": "Acme Software", "by": "idn_admin"},
        headers=ADMIN,
    )
    assert created.status_code == 201, created.text
    tenant = created.json()["id"]
    assert tenant.startswith("tnt_") and created.json()["name"] == "Acme Software"

    assert await given.tenants.served() == (TENANT, OTHER, tenant)
    added, _ = await given.identities.add(tenant, "idn_ada", (tenant,))
    assert added.tenant == tenant, "the identity component serves it without a restart"
    async with given.persistence.transaction(tenant):
        [first, *_] = await given.ledger.entries(tenant)
    assert (first.kind, first.refs.actor) == ("tenant.created", "idn_admin")
    assert "Acme" not in first.model_dump_json(), "the entry carries a digest, never the name"


async def test_a_tenant_is_renamed_and_keeps_its_identifier(client: Client) -> None:
    http, given, base = client
    given.administration_key = Secret(KEY)
    renamed = await http.patch(
        f"{base}/administration/tenants/{OTHER}", json={"name": "Other GmbH"}, headers=ADMIN
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["id"] == OTHER and renamed.json()["name"] == "Other GmbH"
    names = {t.id: t.name for t in await given.tenants.every()}
    assert names[OTHER] == "Other GmbH"
    async with given.persistence.transaction(OTHER):
        kinds = [entry.kind for entry in await given.ledger.entries(OTHER)]
    assert kinds[-1] == "tenant.renamed"

    missing = await http.patch(
        f"{base}/administration/tenants/tnt_nobody", json={"name": "x"}, headers=ADMIN
    )
    is_problem(missing, 404)
    blank = await http.patch(
        f"{base}/administration/tenants/{OTHER}", json={"name": "   "}, headers=ADMIN
    )
    is_problem(blank, 422)
