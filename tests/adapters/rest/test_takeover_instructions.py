"""A process's takeover instructions and the trials of them, on the HTTP surface (ADR-0180,
UC-6.3).

The active version's instructions are read with each step's six elements; a trial is recorded
naming a role and the version; a version at level 3 without a passed trial says it is untried,
on the takeover read, the process level and the overview, and no longer once one passed. A
process of another tenant is answered as one that does not exist; a key is needed; a trial
that names a person instead of a role is refused.
"""

from __future__ import annotations

from typing import Any

import httpx
from fakes.takeover import instructed

from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import Process, ProcessVersion

from .conftest import OTHER, TENANT, Services

type Client = tuple[httpx.AsyncClient, Services, str]


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


BUNDLE: dict[str, Any] = instructed(
    {
        "id": "invoices",
        "version": "1",
        "name": "Invoices",
        "autonomy": {"level": 3, "reason": "a rule checks it", "toward_next": "a year"},
        "steps": [
            {
                "id": "read",
                "method": "rule",
                "reason": "fixed fields",
                "rejected": [],
                "exactness": "exact",
                "checks": [{"kind": "recomputation"}],
                "work": {"rule": "constant", "value": 1},
            }
        ],
    }
)


async def register(given: Services, tenant: str = TENANT) -> None:
    await RegisterProcessVersionHandler(
        MemoryRepository(given.persistence, ProcessVersion),
        given.persistence,
        MemoryRepository(given.persistence, Process),
        ledger=given.ledger,
    ).execute(RegisterProcessVersion(BUNDLE, tenant=tenant))


async def test_the_instructions_are_read_and_a_trial_makes_the_version_tried(
    client: Client,
) -> None:
    http, given, base = client
    await register(given)
    _, key = await given.identity.person(TENANT, "idn_ada")
    path = f"{base}/processes/invoices/takeover"

    read = await http.get(path, headers=bearer(key))
    assert read.status_code == 200, read.text
    body = read.json()
    assert body["process_version"] == "invoices@1" and body["untried"] is True
    (step,) = body["instructions"]["steps"]
    assert {"step", "system", "do", "expertise", "credentials", "done", "skills"} <= set(step)
    level = (await http.get(f"{base}/levels/processes/invoices", headers=bearer(key))).json()
    assert level["process"]["untried"] is True
    assert "No person has yet run this version by hand" in level["process"]["autonomy_text"]
    overview = (await http.get(f"{base}/levels/overview", headers=bearer(key))).json()
    (listed,) = [p for a in overview["areas"] for p in a["processes"]]
    assert listed["untried"] is True and "untried by hand" in listed["text"]

    trial = await http.post(
        f"{path}/trials",
        json={"role": "owner", "passed": True, "missing": []},
        headers=bearer(key),
    )
    assert trial.status_code == 201, trial.text
    assert trial.json()["process_version"] == "invoices@1" and trial.json()["role"] == "owner"
    assert "idn_ada" not in trial.text, "a trial names a role, never a person"
    after = (await http.get(path, headers=bearer(key))).json()
    assert after["untried"] is False and len(after["trials"]) == 1
    level = (await http.get(f"{base}/levels/processes/invoices", headers=bearer(key))).json()
    assert level["process"]["untried"] is False


async def test_a_trial_names_a_role_never_a_person(client: Client) -> None:
    http, given, base = client
    await register(given)
    _, key = await given.identity.person(TENANT, "idn_ada")
    refused = await http.post(
        f"{base}/processes/invoices/takeover/trials",
        json={"role": "Ada Lovelace", "passed": True},
        headers=bearer(key),
    )
    assert refused.status_code == 422


async def test_another_tenants_process_is_none_and_a_key_is_needed(client: Client) -> None:
    http, given, base = client
    await register(given, tenant=OTHER)
    _, key = await given.identity.person(TENANT, "idn_ada")
    path = f"{base}/processes/invoices/takeover"
    assert (await http.get(path, headers=bearer(key))).status_code == 404
    posted = await http.post(
        f"{path}/trials", json={"role": "owner", "passed": True}, headers=bearer(key)
    )
    assert posted.status_code == 404
    assert (await http.get(path)).status_code == 401
