"""Where a run and a process spend, per step, two runs side by side, and model trials, on the
HTTP surface (#449, #448; ADR-0148, ADR-0149).

A run's spend is read by step, from its own ledger entries; another run is set beside it; a
process's spend is summed over a window. A run of another tenant is not found. A trial is
started for the key's identity, read with its report, and offered; a refusal keeps its kind.
A key is needed for all of it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from taktus.components.accounting.application.service import (
    Offer,
    Trial,
    TrialError,
    TrialRead,
    TrialReport,
)
from taktus.ports.ledger import Fact
from taktus.shared.v1 import Consumption, LedgerRefs, Method

from .conftest import OTHER, TENANT, Services, a_run

type Client = tuple[httpx.AsyncClient, Services, str]

AT = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def finished(
    given: Services, run_id: str, step: str, tokens: dict[str, int], digest: str
) -> None:
    async with given.persistence.transaction(TENANT):
        await given.ledger.record(
            TENANT,
            Fact(
                kind="step.finished",
                refs=LedgerRefs(tenant=TENANT, run_id=run_id, step_id=step, process_version="p@1"),
                method=Method.LLM,
                adapter="model.fake",
                consumption=Consumption(tokens_by_model={"fake-model@1": tokens}, turns=2),
                outcome="succeeded",
                content_digest=digest,
            ),
        )


async def test_a_run_s_spend_is_read_by_step_and_another_set_beside_it(client: Client) -> None:
    http, given, base = client
    key = await given.linked()
    for run_id, output, digest in (("run_1", 5, "a" * 64), ("run_2", 9, "b" * 64)):
        await a_run(given, run_id)
        await finished(given, run_id, "a", {"input": 10, "output": output}, f"sha256:{digest}")
    one = await http.get(f"{base}/runs/run_1/spend", headers=bearer(key))
    assert one.status_code == 200
    (step,) = one.json()["steps"]
    assert step["step_id"] == "a" and step["meter"]["turns"] == 2
    assert "amount" not in step, "a run held without a price table is not priced"
    both = await http.get(f"{base}/runs/run_1/spend?against=run_2", headers=bearer(key))
    (difference,) = both.json()["steps"]
    assert difference["tokens_out"] == 4 and difference["same_result"] is False
    assert both.json()["left"]["run_id"] == "run_1"
    assert (await http.get(f"{base}/runs/run_1/spend")).status_code == 401


async def test_a_run_of_another_tenant_has_no_spend_to_show(client: Client) -> None:
    http, given, base = client
    key = await given.linked()
    await a_run(given, "run_9", tenant=OTHER)
    missing = await http.get(f"{base}/runs/run_9/spend", headers=bearer(key))
    assert missing.status_code == 404
    await a_run(given, "run_1")
    beside = await http.get(f"{base}/runs/run_1/spend?against=run_9", headers=bearer(key))
    assert beside.status_code == 404


async def test_a_process_s_spend_is_summed_per_step_over_a_window(client: Client) -> None:
    http, given, base = client
    key = await given.linked()
    for run_id in ("run_1", "run_2"):
        await a_run(given, run_id)
        await finished(given, run_id, "a", {"input": 10, "output": 5}, "sha256:" + "c" * 64)
    answer = await http.get(f"{base}/processes/p/spend?days=7", headers=bearer(key))
    assert answer.status_code == 200
    assert answer.json()["runs"] == 2
    (step,) = answer.json()["steps"]
    assert step["finished"] == 2
    refused = await http.get(f"{base}/processes/p/spend?days=0", headers=bearer(key))
    assert refused.status_code == 422


class Trials:
    def __init__(self) -> None:
        self.started: list[tuple[Any, ...]] = []

    def trial(self) -> Trial:
        return Trial(
            id="trl_1",
            purpose="drafting",
            candidates=("model.fake", "model.other"),
            occasion="asked",
            started_at=AT,
            runs={"model.fake": {"replies/late": "trl_1-0-0"}},
        )

    async def start(
        self, tenant: str, purpose: str, candidates: list[str], by: str, occasion: str = "asked"
    ) -> Trial:
        if purpose == "summarising":
            raise TrialError("empty", "no process asks for summarising")
        if "model.absent" in candidates:
            raise TrialError("invalid", "'model.absent' is no model of this instance")
        self.started.append((tenant, purpose, tuple(candidates), by, occasion))
        return self.trial()

    async def of_tenant(self, tenant: str) -> list[Trial]:
        return [self.trial()]

    async def read(self, tenant: str, trial_id: str) -> TrialRead:
        if trial_id != "trl_1":
            raise TrialError("unknown", f"no trial {trial_id!r}")
        return TrialRead(trial=self.trial(), report=TrialReport(purpose="drafting"), settled=False)

    async def offers(self, tenant: str) -> list[Offer]:
        return [
            Offer(
                purpose="drafting",
                occasion="introduced",
                model="model.fake",
                candidates=("model.fake", "model.other"),
                reason="model.fake serves drafting and has answered no step yet",
            )
        ]


async def test_a_trial_is_started_for_the_key_s_identity_read_and_offered(
    client: Client,
) -> None:
    http, given, base = client
    given.tried = Trials()
    key = await given.linked()
    started = await http.post(
        f"{base}/trials",
        json={"purpose": "drafting", "candidates": ["model.fake", "model.other"]},
        headers=bearer(key),
    )
    assert started.status_code == 201 and started.json()["id"] == "trl_1"
    ((tenant, purpose, candidates, by, occasion),) = given.tried.started
    assert (tenant, purpose, candidates, occasion) == (
        TENANT,
        "drafting",
        ("model.fake", "model.other"),
        "asked",
    )
    assert by.startswith("idn_")
    listed = (await http.get(f"{base}/trials", headers=bearer(key))).json()
    assert [t["id"] for t in listed["trials"]] == ["trl_1"]
    assert [o["occasion"] for o in listed["offers"]] == ["introduced"]
    offered = (await http.get(f"{base}/trials/offers", headers=bearer(key))).json()
    assert offered["offers"][0]["model"] == "model.fake"
    read = await http.get(f"{base}/trials/trl_1", headers=bearer(key))
    assert read.json()["settled"] is False and read.json()["report"]["purpose"] == "drafting"
    assert (await http.get(f"{base}/trials/trl_9", headers=bearer(key))).status_code == 404
    assert (await http.get(f"{base}/trials")).status_code == 401


async def test_a_trial_that_cannot_start_says_why(client: Client) -> None:
    http, given, base = client
    given.tried = Trials()
    key = await given.linked()
    empty = await http.post(
        f"{base}/trials",
        json={"purpose": "summarising", "candidates": ["model.fake"]},
        headers=bearer(key),
    )
    assert empty.status_code == 409 and empty.json()["kind"] == "empty"
    unknown = await http.post(
        f"{base}/trials",
        json={"purpose": "drafting", "candidates": ["model.absent"]},
        headers=bearer(key),
    )
    assert unknown.status_code == 422
    none = await http.post(
        f"{base}/trials", json={"purpose": "drafting", "candidates": []}, headers=bearer(key)
    )
    assert none.status_code == 422
