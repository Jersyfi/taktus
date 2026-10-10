"""The process level on the HTTP surface (ADR-0064, issue #190).

A registered process version is found as its graph, with its autonomy statement; a new version
changes the graph with nothing else edited; an earlier version is still read by name; a process
the reader may not see, or one that does not exist, is answered alike; a key is needed.
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
from taktus.components.reporting.domain.service.drawing import Glyph, Step, check

from .conftest import TENANT, Services

type Client = tuple[httpx.AsyncClient, Services, str]


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def bundle(version: str, *, review: bool = False) -> dict[str, Any]:
    steps: list[dict[str, Any]] = [
        {
            "id": "read",
            "method": "rule",
            "reason": "fixed fields",
            "rejected": [],
            "exactness": "exact",
        },
        {
            "id": "draft",
            "method": "llm",
            "reason": "free text",
            "rejected": [{"method": "rule", "why": "too varied"}],
            "exactness": "free",
            "fallback": {"when": "unclear", "to": "human"},
            "model": "m@1",
            "depends_on": ["read"],
        },
    ]
    work: dict[str, Any] = {"read": {"rule": "constant", "value": 1}, "draft": {"prompt": "x"}}
    if review:
        steps.append(
            {
                "id": "review",
                "method": "human",
                "reason": "a person signs",
                "rejected": [],
                "depends_on": ["draft"],
            }
        )
        work["review"] = {"ask": "sign"}
    return {
        "id": "invoices",
        "version": version,
        "name": "Invoices",
        "autonomy": {"level": 2, "reason": "a person confirms", "toward_next": "twenty runs"},
        "steps": steps,
        "work": work,
    }


async def register(given: Services, document: dict[str, Any], tenant: str = TENANT) -> None:
    handler = RegisterProcessVersionHandler(
        MemoryRepository(given.persistence, ProcessVersion),
        given.persistence,
        MemoryRepository(given.persistence, Process),
        ledger=given.ledger,
    )
    await handler.execute(RegisterProcessVersion(document, tenant=tenant))


def drawn(level: dict[str, Any], key: str) -> list[tuple[Step, Glyph]]:
    return [
        (
            Step(
                name=s["id"],
                method=s["method"],
                exactness=s.get("exactness"),
                state="running" if s.get("running_in") else "planned",
            ),
            Glyph.model_validate(s["drawn"][key]),
        )
        for s in level["steps"]
    ]


async def test_a_registered_version_is_found_as_its_graph_with_its_autonomy_statement(
    client: Client,
) -> None:
    http, given, base = client
    await register(given, bundle("1"))
    _, key = await given.identity.person(TENANT, "idn_ada")
    answer = await http.get(f"{base}/levels/processes/invoices", headers=bearer(key))
    assert answer.status_code == 200, answer.text
    level = answer.json()
    assert level["process"]["version"] == "1"
    assert level["process"]["autonomy"]["level"] == 2
    assert "a person confirms" in level["process"]["autonomy_text"]
    assert [s["id"] for s in level["steps"]] == ["read", "draft"]
    assert level["steps"][1]["depends_on"] == ["read"]
    assert check(drawn(level, "moving"), motion=True) == ()
    assert check(drawn(level, "still"), motion=False) == ()


async def test_a_new_version_changes_the_graph_with_nothing_else_edited(client: Client) -> None:
    http, given, base = client
    await register(given, bundle("1"))
    _, key = await given.identity.person(TENANT, "idn_ada")
    before = (await http.get(f"{base}/levels/processes/invoices", headers=bearer(key))).json()
    await register(given, bundle("2", review=True))
    after = (await http.get(f"{base}/levels/processes/invoices", headers=bearer(key))).json()
    assert [s["id"] for s in before["steps"]] == ["read", "draft"]
    assert [s["id"] for s in after["steps"]] == ["read", "draft", "review"]
    assert [(v["version"], v.get("active", False)) for v in after["process"]["versions"]] == [
        ("1", False),
        ("2", True),
    ]
    earlier = await http.get(
        f"{base}/levels/processes/invoices", params={"version": "1"}, headers=bearer(key)
    )
    assert [s["id"] for s in earlier.json()["steps"]] == ["read", "draft"]


async def test_a_process_the_reader_may_not_see_is_answered_as_one_that_does_not_exist(
    client: Client,
) -> None:
    http, given, base = client
    await register(given, bundle("1"), tenant="other")
    _, key = await given.identity.person(TENANT, "idn_ada")
    unseen = await http.get(f"{base}/levels/processes/invoices", headers=bearer(key))
    missing = await http.get(f"{base}/levels/processes/nothing", headers=bearer(key))
    assert unseen.status_code == missing.status_code == 404
    assert unseen.json()["detail"] == "no process 'invoices' you may see"
    no_version = await http.get(
        f"{base}/levels/processes/invoices", params={"version": "9"}, headers=bearer(key)
    )
    assert no_version.status_code == 404


async def test_the_process_level_needs_a_key(client: Client) -> None:
    http, given, base = client
    await register(given, bundle("1"))
    assert (await http.get(f"{base}/levels/processes/invoices")).status_code == 401
