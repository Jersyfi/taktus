"""A role's profile, on the HTTP surface (UC-15.7, ADR-0167 §3 to §5).

The profile is read from the records of the processes on each request and stores nothing; a
figure that persons' work produced is withheld where one identity holds the role; the export is
a draft that says it is unreviewed and names no person; another tenant sees none of it.
"""

from __future__ import annotations

from typing import Any

import httpx

from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import Process, ProcessVersion

from .conftest import OTHER, TENANT, Services
from .test_process_level import bearer
from .test_surface import is_problem

type Client = tuple[httpx.AsyncClient, Services, str]

BUNDLE: dict[str, Any] = {
    "id": "invoice",
    "version": "1",
    "name": "Invoice",
    "autonomy": {"level": 2, "reason": "a test", "toward_next": "nothing"},
    "steps": [
        {
            "id": "total",
            "method": "rule",
            "reason": "a fixed sum",
            "rejected": [],
            "exactness": "exact",
            "checks": [{"kind": "approval", "threshold": 1000, "role": "controlling"}],
            "work": {"rule": "constant", "value": 1},
        },
        {
            "id": "book",
            "method": "human",
            "reason": "it binds the organisation",
            "rejected": [],
            "role": "accounting",
            "expertise": ["double entry"],
            "depends_on": ["total"],
            "work": {"task": "book the invoice"},
        },
    ],
    "limits": {"quota": {"units": 5}},
}


def stored(given: Services) -> tuple[str, int]:
    """Everything the memory persistence holds, to show that a read writes nothing. A table a
    read only looked into holds nothing, and is left out."""
    tables = sorted((k, repr(v)) for k, v in given.persistence._tables.items() if any(v.values()))
    return repr(tables), sum(len(e) for e in given.persistence._ledger.values())


async def world(given: Services) -> dict[str, str]:
    keys: dict[str, str] = {}
    for name, path, roles in [
        ("idn_owner", (TENANT,), ("owner",)),
        ("idn_ada", (TENANT, "finance"), ("accounting",)),
        ("idn_bo", (TENANT, "finance"), ("accounting",)),
        ("idn_cy", (TENANT, "control"), ("controlling",)),
    ]:
        _, keys[name] = await given.identities.add(TENANT, name, path, roles=roles)
    register = RegisterProcessVersionHandler(
        MemoryRepository(given.persistence, ProcessVersion),
        given.persistence,
        MemoryRepository(given.persistence, Process),
        ledger=given.ledger,
    )
    await register.execute(RegisterProcessVersion(BUNDLE, tenant=TENANT, by="idn_owner"))
    return keys


async def test_a_profile_is_read_from_the_records_and_stores_nothing(client: Client) -> None:
    http, given, base = client
    keys = await world(given)
    assert is_problem(await http.get(f"{base}/roles/accounting"), 401)
    before = stored(given)

    listed = (await http.get(f"{base}/roles", headers=bearer(keys["idn_ada"]))).json()
    assert [r["role"] for r in listed["roles"]] == ["accounting", "controlling", "owner"]
    assert "DEC-0029" in listed["review"]

    profile = (await http.get(f"{base}/roles/accounting", headers=bearer(keys["idn_ada"]))).json()
    (book,) = profile["performs"]
    assert (book["step"], book["task"], book["expertise"]) == (
        "book",
        "book the invoice",
        ["double entry"],
    )
    assert profile["units"] == [f"{TENANT}/finance"]
    assert profile["load"]["performed"] == {"value": 0.0}, "two hold it: shown"
    assert profile["waiting"]["own_seconds"] == 0, "a holder sees their own beside it"
    assert "strategic anchor" in profile["workforce"]

    controlling = (
        await http.get(f"{base}/roles/controlling", headers=bearer(keys["idn_ada"]))
    ).json()
    assert [(s["step"], s["check"]) for s in controlling["supervises"]] == [("total", "approval")]
    assert "withheld" in controlling["load"]["performed"]["withheld"], "one holds it"
    assert "withheld" in controlling["waiting"]["seconds"]["withheld"]
    assert "own_seconds" not in controlling["waiting"], "the reader does not hold it"
    assert stored(given) == before, "the profile stores nothing of its own"
    for key in ("idn_ada", "idn_bo", "idn_cy"):
        assert key not in repr(profile) + repr(controlling), "no person in a profile"

    missing = await http.get(f"{base}/roles/nobody", headers=bearer(keys["idn_ada"]))
    assert is_problem(missing, 404)


async def test_the_export_is_a_draft_that_names_no_person(client: Client) -> None:
    http, given, base = client
    keys = await world(given)
    drafted = await http.get(
        f"{base}/roles/accounting/description", headers=bearer(keys["idn_ada"])
    )
    assert drafted.status_code == 200
    assert drafted.headers["content-type"].startswith("text/markdown")
    text = drafted.text
    assert text.startswith("# Draft position description: role `accounting`")
    assert "Not to be used before that review" in text
    assert "`invoice/book`: book the invoice; needs double entry" in text
    for key in ("idn_ada", "idn_bo", "seconds"):
        assert key not in text


async def test_another_tenant_sees_no_profile_of_this_one(client: Client) -> None:
    http, given, base = client
    await world(given)
    _, elsewhere = await given.identity.person(OTHER, "idn_zed")
    listed = (await http.get(f"{base}/roles", headers=bearer(elsewhere))).json()
    assert "accounting" not in [r["role"] for r in listed["roles"]]
    assert is_problem(await http.get(f"{base}/roles/accounting", headers=bearer(elsewhere)), 404)
