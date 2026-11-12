"""Data-protection requests and the processing evidence on the HTTP surface (UC-11.2, ADR-0176).

The routes reach the same service `taktusctl subject` reaches, over this world's stores. What a
request finds and erases is held by `tests/composition/test_subjects.py`; here: a request is
prepared, shown and listed with the caller as its actor; it is carried out only with the
identity check stated; an export is in the answer; another tenant's request is not found; a
withdrawn request cannot be confirmed; a key is needed; the evidence is read.
"""

from __future__ import annotations

from typing import Any

import httpx
from fakes import FakeIdentifiers

from taktus.adapters.driven.memory import (
    MemoryObjectStore,
    MemoryProvenanceStore,
    MemoryRepository,
    MemoryTraceStore,
)
from taktus.adapters.driven.memory.tenant_store import MemoryTenantStore
from taktus.components.governance.application.service import SubjectRequests
from taktus.components.governance.domain.model import SubjectRequest
from taktus.composition.subjects import RunHoldings

from .conftest import OTHER, TENANT, Services, a_run

type Client = tuple[httpx.AsyncClient, Services, str]


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


class Evidence:
    async def evidence(self, tenant: str) -> dict[str, Any]:
        return {"tenant": tenant, "legally_reviewed": False, "processing": []}


def wire(given: Services) -> None:
    async def locations(tenant: str) -> dict[str, str | None]:
        return {}

    given.requested = SubjectRequests(
        MemoryRepository(given.persistence, SubjectRequest),
        RunHoldings(
            runs=given.runs,
            provenance=MemoryProvenanceStore(given.persistence),
            ledger=given.ledger,
            objects=MemoryObjectStore(),
            work=given.persistence,
            tenants=MemoryTenantStore(given.persistence),
            traces=MemoryTraceStore(given.persistence),
            locations=locations,
        ),
        given.ledger,
        given.persistence,
        given.clock,
        FakeIdentifiers(),
    )
    given.evidenced = Evidence()


async def test_a_request_is_prepared_and_carried_out_only_with_the_identity_check(
    client: Client,
) -> None:
    http, given, base = client
    wire(given)
    await a_run(given)
    _, key = await given.identity.person(TENANT, "idn_dpo")

    prepared = await http.post(
        f"{base}/subjects/requests",
        json={"kind": "erasure", "subject": "cust-1"},
        headers=bearer(key),
    )
    assert prepared.status_code == 201, prepared.text
    body = prepared.json()
    request = body["id"]
    assert body["state"] == "prepared" and body["prepared_by"] == "idn_dpo"
    assert body["holds"] == {"runs": 0, "objects": 0, "kept": 0, "in_flight": []}

    listed = (await http.get(f"{base}/subjects/requests", headers=bearer(key))).json()
    assert [r["id"] for r in listed["requests"]] == [request]

    unchecked = await http.post(
        f"{base}/subjects/requests/{request}/confirm",
        json={"identity_checked": False},
        headers=bearer(key),
    )
    assert unchecked.status_code == 409, unchecked.text
    shown = (await http.get(f"{base}/subjects/requests/{request}", headers=bearer(key))).json()
    assert shown["state"] == "prepared"

    done = await http.post(
        f"{base}/subjects/requests/{request}/confirm",
        json={"identity_checked": True},
        headers=bearer(key),
    )
    assert done.status_code == 200, done.text
    assert done.json()["state"] == "carried_out" and done.json()["carried_out_by"] == "idn_dpo"
    async with given.persistence.transaction(TENANT):
        recorded = await given.ledger.entries(TENANT)
    kinds = [e.kind for e in recorded]
    assert "subject.request_prepared" in kinds and "subject.erased" in kinds
    assert "cust-1" not in str([e.document() for e in recorded])


async def test_an_access_export_is_in_the_answer_and_a_withdrawn_request_stays_withdrawn(
    client: Client,
) -> None:
    http, given, base = client
    wire(given)
    _, key = await given.identity.person(TENANT, "idn_dpo")
    access = (
        await http.post(
            f"{base}/subjects/requests",
            json={"kind": "access", "subject": "cust-2"},
            headers=bearer(key),
        )
    ).json()
    exported = await http.post(
        f"{base}/subjects/requests/{access['id']}/confirm",
        json={"identity_checked": True},
        headers=bearer(key),
    )
    assert exported.status_code == 200, exported.text
    assert exported.json()["export"]["subject"] == "cust-2"

    ended = (
        await http.post(
            f"{base}/subjects/requests",
            json={"kind": "erasure", "subject": "cust-2"},
            headers=bearer(key),
        )
    ).json()
    withdrawn = await http.post(
        f"{base}/subjects/requests/{ended['id']}/withdraw", headers=bearer(key)
    )
    assert withdrawn.status_code == 200 and withdrawn.json()["state"] == "withdrawn"
    again = await http.post(
        f"{base}/subjects/requests/{ended['id']}/confirm",
        json={"identity_checked": True},
        headers=bearer(key),
    )
    assert again.status_code == 409, again.text


async def test_another_tenant_s_request_is_not_found_and_a_key_is_needed(client: Client) -> None:
    http, given, base = client
    wire(given)
    _, key = await given.identity.person(TENANT, "idn_dpo")
    _, stranger = await given.identity.person(OTHER, "idn_eve")
    mine = (
        await http.post(
            f"{base}/subjects/requests",
            json={"kind": "access", "subject": "cust-1"},
            headers=bearer(key),
        )
    ).json()
    theirs = await http.get(f"{base}/subjects/requests/{mine['id']}", headers=bearer(stranger))
    assert theirs.status_code == 404
    confirm = await http.post(
        f"{base}/subjects/requests/{mine['id']}/confirm",
        json={"identity_checked": True},
        headers=bearer(stranger),
    )
    assert confirm.status_code == 404
    assert (await http.get(f"{base}/subjects/requests")).status_code == 401
    assert (await http.get(f"{base}/evidence")).status_code == 401


async def test_the_evidence_is_read_for_the_caller_s_tenant(client: Client) -> None:
    http, given, base = client
    wire(given)
    _, key = await given.identity.person(TENANT, "idn_dpo")
    read = await http.get(f"{base}/evidence", headers=bearer(key))
    assert read.status_code == 200, read.text
    assert read.json() == {"tenant": TENANT, "legally_reviewed": False, "processing": []}
