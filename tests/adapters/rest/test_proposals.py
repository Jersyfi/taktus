"""Proposals on the HTTP surface (UC-4.15, ADR-0091 §1 and §6, issue #294).

A changed bundle becomes a proposal with its difference; the active version is unchanged; a
bundle that would not register gives every finding; a process of another tenant, or none, is
answered alike; a key is needed; an open proposal is discarded once.
"""

from __future__ import annotations

from typing import Any

import httpx

from taktus.components.process.application.service.proposals import ProposalError
from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.process.domain.model import ProcessVersion

from .conftest import OTHER, TENANT, Services
from .test_process_level import bundle, register

type Client = tuple[httpx.AsyncClient, Services, str]


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def test_a_changed_bundle_becomes_a_proposal_and_the_active_version_is_unchanged(
    client: Client,
) -> None:
    http, given, base = client
    await register(given, bundle("1"))
    key = await given.linked()
    response = await http.post(
        f"{base}/processes/invoices/proposals",
        json={"bundle": bundle("2", review=True), "request": "a person signs the draft"},
        headers=bearer(key),
    )
    assert response.status_code == 201, response.text
    proposal = response.json()
    assert (proposal["base_version"], proposal["version"], proposal["state"]) == (
        "1",
        "2",
        "proposed",
    )
    assert [(c["id"], c["change"]) for c in proposal["difference"]["steps"]] == [
        ("review", "added")
    ]
    level = (await http.get(f"{base}/levels/processes/invoices", headers=bearer(key))).json()
    assert level["process"]["version"] == "1", "nothing was registered"
    listed = (await http.get(f"{base}/processes/invoices/proposals", headers=bearer(key))).json()
    assert [p["id"] for p in listed["proposals"]] == [proposal["id"]]
    one = await http.get(
        f"{base}/processes/invoices/proposals/{proposal['id']}", headers=bearer(key)
    )
    assert one.json() == proposal


async def test_a_bundle_that_would_not_register_gives_every_finding(client: Client) -> None:
    http, given, base = client
    await register(given, bundle("1"))
    key = await given.linked()
    broken = bundle("2")
    del broken["steps"][0]["checks"]
    response = await http.post(
        f"{base}/processes/invoices/proposals", json={"bundle": broken}, headers=bearer(key)
    )
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["findings"]
    listed = (await http.get(f"{base}/processes/invoices/proposals", headers=bearer(key))).json()
    assert listed["proposals"] == []


async def test_another_tenants_process_or_none_is_answered_alike_and_a_key_is_needed(
    client: Client,
) -> None:
    http, given, base = client
    await register(given, bundle("1"), tenant=OTHER)
    key = await given.linked()
    for process in ("invoices", "nothing"):
        response = await http.post(
            f"{base}/processes/{process}/proposals",
            json={"bundle": {**bundle("2"), "id": process}},
            headers=bearer(key),
        )
        assert response.status_code == 404, process
    missing = await http.post(f"{base}/processes/invoices/proposals", json={"bundle": bundle("2")})
    assert missing.status_code == 401
    assert TENANT != OTHER


async def test_an_open_proposal_is_discarded_once(client: Client) -> None:
    http, given, base = client
    await register(given, bundle("1"))
    key = await given.linked()
    made = await http.post(
        f"{base}/processes/invoices/proposals", json={"bundle": bundle("2")}, headers=bearer(key)
    )
    path = f"{base}/processes/invoices/proposals/{made.json()['id']}/discard"
    first = await http.post(path, headers=bearer(key))
    assert first.status_code == 200 and first.json()["state"] == "discarded"
    assert (await http.post(path, headers=bearer(key))).status_code == 409


class Acts:
    """The acts as the surface reaches them: what was asked, and a refusal or a version back."""

    def __init__(self, refusal: ProposalError | None = None) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.refusal = refusal

    def _answer(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((name, args, kwargs))
        if self.refusal is not None:
            raise self.refusal

    async def rehearse(self, *args: Any, **kwargs: Any) -> Any:
        self._answer("rehearse", *args, **kwargs)
        raise AssertionError("not reached in these tests")

    async def commission(self, *args: Any, **kwargs: Any) -> ProcessVersion:
        self._answer("commission", *args, **kwargs)
        return parse_bundle(bundle("2"))

    async def rollback(self, *args: Any, **kwargs: Any) -> ProcessVersion:
        self._answer("rollback", *args, **kwargs)
        return parse_bundle(bundle("3"))


async def test_commission_and_rollback_act_for_the_key_s_identity(client: Client) -> None:
    http, given, base = client
    given.acts = acts = Acts()
    key = await given.linked()
    done = await http.post(
        f"{base}/processes/invoices/proposals/prp_1/commission",
        json={"approve_raise": True},
        headers=bearer(key),
    )
    assert done.json() == {"process": "invoices", "version": "2"}
    back = await http.post(
        f"{base}/processes/invoices/rollback", json={"version": "1"}, headers=bearer(key)
    )
    assert back.json() == {"process": "invoices", "version": "3"}
    (commissioned, rolled) = acts.calls
    assert commissioned[1][2:4] == ("prp_1", "idn_ada")
    assert commissioned[2] == {"approved_by": "idn_ada"}, "the raise approved by who asks"
    assert rolled[1][1:4] == ("invoices", "1", "idn_ada") and rolled[2]["approved_by"] is None
    missing = await http.post(f"{base}/processes/invoices/rollback", json={"version": "1"})
    assert missing.status_code == 401


async def test_a_refused_act_is_a_conflict_and_an_unknown_one_is_not_found(client: Client) -> None:
    http, given, base = client
    key = await given.linked()
    for kind, status in (("unrehearsed", 409), ("stale", 409), ("unknown", 404)):
        given.acts = Acts(ProposalError(kind, f"refused: {kind}"))
        refused = await http.post(
            f"{base}/processes/invoices/proposals/prp_1/commission", json={}, headers=bearer(key)
        )
        assert refused.status_code == status, kind
        assert refused.json()["kind"] == kind
