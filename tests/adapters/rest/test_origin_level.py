"""The origin of a result on the HTTP surface (ADR-0068, issue #192).

A step's result is found with the path back to what produced it, from the provenance records
the run left; a result in another tenant, of a step without a record, or of a step that produced
none is answered alike; a key is needed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from taktus.adapters.driven.memory import MemoryProvenanceStore
from taktus.shared.v1 import Provenance

from .conftest import TENANT, Services, a_run

type Client = tuple[httpx.AsyncClient, Services, str]

AT = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)
DIGEST = "sha256:" + "2" * 64


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def record(step: str, seq: int, *inputs: dict[str, Any], method: str = "rule") -> Provenance:
    exactness = None if method == "human" else "exact"
    return Provenance.model_validate(
        {
            "id": f"prv_{step}",
            "run_id": "run_1",
            "step_id": step,
            "process_version": "p@1",
            "method": method,
            "exactness": exactness,
            "inputs": list(inputs),
            "outputs": [],
            "result_digest": DIGEST if exactness else None,
            "ledger_seq": seq,
            "recorded_at": AT,
        }
    )


async def recorded(given: Services, tenant: str = TENANT) -> None:
    store = MemoryProvenanceStore(given.persistence)
    source = {
        "kind": "source",
        "capability": "repository.files",
        "ref": "main:a.txt",
        "digest": DIGEST,
        "observed_at": AT,
    }
    earlier = {
        "kind": "result",
        "run_id": "run_1",
        "step_id": "a",
        "digest": DIGEST,
        "observed_at": AT,
    }
    async with given.persistence.transaction(tenant):
        await store.append(tenant, record("a", 2, source))
        await store.append(tenant, record("b", 3, earlier))
        await store.append(tenant, record("c", 4, method="human"))


async def test_a_result_is_found_with_the_path_back_to_what_produced_it(client: Client) -> None:
    http, given, base = client
    await a_run(given)
    await recorded(given)
    _, key = await given.identity.person(TENANT, "idn_ada")
    answer = await http.get(f"{base}/levels/origins/run_1/b", headers=bearer(key))
    assert answer.status_code == 200, answer.text
    level = answer.json()
    assert level["result"]["exactness"] == "exact" and level["result"]["digest"] == DIGEST
    assert [s["id"] for s in level["steps"]] == ["run_1/b", "run_1/a"]
    assert level["steps"][1]["depends_on"] == ["source:repository.files:main:a.txt"]
    assert [s["ref"] for s in level["sources"]] == ["main:a.txt"]


async def test_no_result_answers_alike(client: Client) -> None:
    http, given, base = client
    await a_run(given)
    await recorded(given)
    await recorded(given, tenant="other")
    _, key = await given.identity.person(TENANT, "idn_ada")
    for path in ("run_1/c", "run_1/z", "run_9/a"):
        answer = await http.get(f"{base}/levels/origins/{path}", headers=bearer(key))
        assert answer.status_code == 404, path
        assert answer.json()["detail"] == f"no result of {path} you may see"


async def test_the_origin_needs_a_key(client: Client) -> None:
    http, given, base = client
    await recorded(given)
    assert (await http.get(f"{base}/levels/origins/run_1/b")).status_code == 401
