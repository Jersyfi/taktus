"""A tenant's export and import on the HTTP surface, for the administration key (ADR-0221).

The routes hand the export's bytes through unchanged and answer what an import's check found.
What an export holds and what the check proves is held by
`tests/integration/test_tenant_export.py`, against two databases. Here: only the administration
key is admitted; an instance without a database says so; a tenant that holds something is a
conflict and a document that is no export a refusal; an import whose check failed is not
answered as created.
"""

from __future__ import annotations

import httpx

from taktus.ports.configuration import Secret
from taktus.ports.persistence import TenantImported, TenantNotEmpty

from .conftest import TENANT, Services

type Client = tuple[httpx.AsyncClient, Services, str]
KEY = "adm-a-random-value-for-this-test"
ADMIN = {"Authorization": f"Bearer {KEY}"}


class Exports:
    def __init__(self, *, verified: bool = True) -> None:
        self.verified = verified
        self.imported: list[bytes] = []

    async def export(self, tenant: str, *, by: str) -> bytes:
        if tenant != TENANT:
            raise ValueError(f"this instance serves no tenant {tenant!r}")
        return b'{"format":"taktus.tenant-export/1"}'

    async def import_(self, content: bytes, *, by: str) -> TenantImported:
        if content == b"held":
            raise TenantNotEmpty(TENANT, 3)
        if not content.startswith(b"{"):
            raise ValueError("not an export")
        self.imported.append(content)
        return TenantImported(
            tenant=TENANT,
            rows=4,
            objects=1,
            entries=9,
            ledger_intact=True,
            heads_match=self.verified,
            provenance_intact=True,
            findings=() if self.verified else ("the newest entry differs on the chains tenant",),
        )


async def test_an_export_is_handed_out_as_it_is_and_only_for_the_administration_key(
    client: Client,
) -> None:
    http, given, base = client
    given.administration_key = Secret(KEY)
    given.exported = Exports()
    path = f"{base}/administration/tenants/{TENANT}/export"
    assert (await http.get(path)).status_code == 401
    answer = await http.get(path, headers=ADMIN)
    assert answer.status_code == 200 and answer.content == b'{"format":"taktus.tenant-export/1"}'
    missing = await http.get(f"{base}/administration/tenants/nobody/export", headers=ADMIN)
    assert missing.status_code == 404


async def test_an_import_answers_its_check_and_refuses_a_tenant_that_holds_something(
    client: Client,
) -> None:
    http, given, base = client
    given.administration_key = Secret(KEY)
    given.exported = Exports()
    path = f"{base}/administration/tenants/import"
    done = await http.post(path, content=b"{}", headers=ADMIN)
    assert done.status_code == 201, done.text
    assert done.json()["verified"] is True and done.json()["entries"] == 9
    assert (await http.post(path, content=b"held", headers=ADMIN)).status_code == 409
    assert (await http.post(path, content=b"nonsense", headers=ADMIN)).status_code == 422
    given.exported = Exports(verified=False)
    failed = await http.post(path, content=b"{}", headers=ADMIN)
    assert failed.status_code == 200 and failed.json()["verified"] is False


async def test_without_a_database_the_routes_say_so(client: Client) -> None:
    http, given, base = client
    given.administration_key = Secret(KEY)
    answer = await http.get(f"{base}/administration/tenants/{TENANT}/export", headers=ADMIN)
    assert answer.status_code == 409 and "database" in answer.text
