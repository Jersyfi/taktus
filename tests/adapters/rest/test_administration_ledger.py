"""UC-10.2 §2: every administrative act, by whatever path, is a ledger entry naming the identity
that did it and the act (NTC-0273). The test walks the inventory: it does each act on the HTTP
surface and finds its entry. An act that reads leaves `administration.read` with the act's name;
an act that changes something leaves the entry of the use case it calls."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest

from taktus.adapters.driving.inventory import ACTS, READ, READS
from taktus.components.identity.domain.model import Right
from taktus.components.reporting.application.service import ConfigureChannel
from taktus.components.reporting.domain.model.acting import Register
from taktus.ports.configuration import Secret

from .conftest import TENANT, Services

type Client = tuple[httpx.AsyncClient, Services, str]

ADMIN = "idn_admin"
INSTANCE_KEY = "adm-key-for-the-walk"

ELSEWHERE: dict[str, str] = {
    "tenant.export": "tests/integration/test_tenant_export.py::"
    "test_an_export_imported_into_a_fresh_instance_verifies_there_and_runs_on",
    "tenant.import": "tests/integration/test_tenant_export.py::"
    "test_an_export_imported_into_a_fresh_instance_verifies_there_and_runs_on",
    "adapter.stop": "tests/components/run/test_adapter_stop.py::"
    "test_a_stop_of_one_worker_halts_every_run_it_serves_and_the_others_go_on",
}
"""Acts whose entry needs what this world has not — the database, the run engine — each with the
test that finds it there."""

WRITES: dict[str, str] = {
    "tenant.create": "tenant.created",
    "tenant.rename": "tenant.renamed",
    "identity.add": "identity.created",
    "identity.key": "identity.key_issued",
    "identity.agent-key": "identity.agent_key_issued",
    "identity.roles": "identity.roles_set",
    "identity.revoke": "identity.unlinked",
    "identity.grant": "identity.right_granted",
    "identity.withdraw": "identity.right_withdrawn",
    "units.set": "units.configured",
    "units.clear": "units.configured",
    "structure.levels": "structure.levels_named",
    "structure.unit": "structure.unit_added",
    "structure.place": "structure.placed",
    "structure.knowledge": "structure.knowledge_configured",
    "project.create": "project.created",
    "instance.update": "administration.prepared",
}
"""The entry each act that changes something leaves, by the use case it calls."""


class Views:
    """The register as the acting reads give it; what they gather is held by
    `tests/composition/test_acting.py`."""

    async def register(self, tenant: str, visible: frozenset[str]) -> Register:
        return Register(tenant=tenant, permitted="anywhere", rows=(), summary="Nothing acts.")


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def world(given: Services) -> dict[str, str]:
    """An administrator holding every administrative right, the instance's key, a linked
    account, and the administrator as the owner who reads the backup."""
    _, key = await given.identities.add(TENANT, ADMIN, (TENANT,), roles=("admin",))
    for right in (Right.ADMINISTER, Right.SHAPE_STRUCTURE):
        await given.identities.grant(TENANT, "admin", right)
    await given.identities.add(TENANT, "idn_new", (TENANT,), roles=("clerk",))
    await given.linked()
    given.administration_key = Secret(INSTANCE_KEY)
    given.views = Views()
    await given.owner.configure.execute(
        ConfigureChannel(
            tenant=TENANT,
            document={
                "owner": ADMIN,
                "named": [],
                "channel": "channel.repo",
                "address": "acme/taktus#1",
                "language": "en",
            },
            actor="operator",
        )
    )
    return {"key": key}


type Call = Callable[[httpx.AsyncClient, str, Services, str], Awaitable[httpx.Response]]


def call(method: str, path: str, body: Any = None, *, instance: bool = False) -> Call:
    async def made(http: httpx.AsyncClient, base: str, given: Services, key: str) -> Any:
        if "{link}" in path:
            [link] = [x.id for x in await given.identities.links(TENANT) if x.active]
            resolved = path.replace("{link}", link)
        else:
            resolved = path.replace("{tenant}", TENANT)
        headers = bearer(INSTANCE_KEY if instance else key)
        return await http.request(method, f"{base}{resolved}", json=body, headers=headers)

    return made


CALLS: dict[str, Call] = {
    "tenant.list": call("GET", "/administration/tenants", instance=True),
    "tenant.create": call("POST", "/administration/tenants", {"name": "Beta", "by": ADMIN},
                          instance=True),
    "tenant.rename": call("PATCH", "/administration/tenants/{tenant}",
                          {"name": "Acme", "by": ADMIN}, instance=True),
    "identity.add": call("POST", "/administration/identities", {"identity": "idn_two"}),
    "identity.key": call("POST", "/administration/identities/idn_new/key"),
    "identity.agent-key": call("POST", "/administration/identities/idn_new/agent-key"),
    "identity.roles": call("PUT", "/administration/identities/idn_new/roles", {"roles": ["lead"]}),
    "identity.links": call("GET", "/administration/links"),
    "identity.revoke": call("DELETE", "/administration/links/{link}"),
    "identity.rights": call("GET", "/administration/rights"),
    "identity.grant": call("PUT", "/administration/rights/lead/process.create"),
    "identity.withdraw": call("DELETE", "/administration/rights/admin/process.steer"),
    "units.show": call("GET", "/administration/units"),
    "units.set": call("PUT", "/administration/units/ops", {"concurrent_runs": 2}),
    "units.clear": call("DELETE", "/administration/units/ops"),
    "structure.show": call("GET", "/structure"),
    "structure.levels": call("PUT", "/structure/levels", {"levels": ["company", "team"]}),
    "structure.unit": call("POST", "/structure/units", {"id": "ops", "name": "Ops",
                                                        "parent": TENANT}),
    "structure.place": call("PUT", "/structure/placements/process/invoices", {"unit": TENANT}),
    "structure.knowledge": call("PUT", f"/structure/knowledge/{TENANT}",
                                {"base": "https://wiki.example.org/acme"}),
    "structure.where": call("GET", "/structure/filings/process/invoices"),
    "project.create": call("POST", "/projects", {"id": "notes", "name": "Notes",
                                                  "circle": "alone"}),
    "adapter.list": call("GET", "/register"),
    "backup.list": call("GET", "/backup"),
    "instance.health": call("GET", "/administration/health"),
    "instance.update": call("POST", "/administration/update", {"to": "1.0.1"}),
}  # fmt: skip


def test_the_walk_covers_the_inventory() -> None:
    named = {a.name for a in ACTS}
    assert set(CALLS) | set(ELSEWHERE) == named
    assert not set(CALLS) & set(ELSEWHERE)
    assert set(WRITES) | READS == set(CALLS)


async def entries(given: Services) -> list[Any]:
    found = []
    for tenant in [e.id for e in await given.tenants.every()]:
        async with given.persistence.transaction(tenant):
            found += list(await given.ledger.entries(tenant))
    return found


@pytest.mark.parametrize("act", sorted(CALLS))
async def test_every_administrative_act_is_a_ledger_entry_naming_who_did_it(
    client: Client, act: str
) -> None:
    http, given, base = client
    keys = await world(given)
    if act == "identity.withdraw":
        await given.identities.grant(TENANT, "admin", Right.PROCESS_STEER)
    if act == "units.clear":
        await CALLS["units.set"](http, base, given, keys["key"])
    if act == "structure.knowledge":
        await CALLS["structure.levels"](http, base, given, keys["key"])
    before = len(await entries(given))
    answered = await CALLS[act](http, base, given, keys["key"])
    answer = answered.status_code < 400 or (
        act == "structure.where" and answered.status_code == 404
    )
    assert answer, f"{act}: {answered.status_code} {answered.text}"  # nothing filed is an answer
    new = (await entries(given))[before:]
    expected = "administrator" if act == "tenant.list" else ADMIN
    if act in READS:
        found = [e for e in new if e.kind == READ and e.refs.action == act]
    else:
        found = [e for e in new if e.kind == WRITES[act]]
    assert found, f"{act} left no entry: {[e.kind for e in new]}"
    assert {e.refs.actor for e in found} == {expected}, f"{act} names who did it"
    assert all(e.content_digest is None for e in found if e.kind == READ), "nothing read"
