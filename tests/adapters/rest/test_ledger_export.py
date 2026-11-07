"""The tenant's ledger exported on the HTTP surface (UC-6.1, ADR-0253 §1).

The owner receives every entry of the tenant, one JSON document per line, exactly as the hash
rule covers it, so that the file verifies without Taktus; a reader without the role `owner` is
refused, and a key is needed.
"""

from __future__ import annotations

import json

import httpx

from taktus.components.ledger.domain.model import exported

from .conftest import TENANT, Services, a_run

type Client = tuple[httpx.AsyncClient, Services, str]


async def test_the_owner_exports_every_entry_one_per_line_as_its_hash_covers_it(
    client: Client,
) -> None:
    http, given, base = client
    await a_run(given)
    _, key = await given.identities.add(TENANT, "idn_owner", (TENANT,), roles=("owner",))
    answer = await http.get(f"{base}/ledger/export", headers={"Authorization": f"Bearer {key}"})
    assert answer.status_code == 200, answer.text
    assert answer.headers["content-type"].startswith("application/x-ndjson")
    async with given.persistence.transaction(TENANT):
        entries = await given.ledger.entries(TENANT)
    assert answer.content == exported(entries)
    lines = answer.text.splitlines()
    assert len(lines) == len(entries) and all(json.loads(line)["hash"] for line in lines)


async def test_a_reader_without_the_owner_role_is_refused_and_a_key_is_needed(
    client: Client,
) -> None:
    http, given, base = client
    _, key = await given.identities.add(TENANT, "idn_reader", (TENANT,))
    refused = await http.get(f"{base}/ledger/export", headers={"Authorization": f"Bearer {key}"})
    assert refused.status_code == 403
    assert (await http.get(f"{base}/ledger/export")).status_code == 401
