"""A process's evaluations and its proposed cases on the HTTP surface (UC-4.18, ADR-0134 §9).

The evaluations are read with their scores; a proposed case is confirmed with a target of the
person's own, or rejected, acting for the key's identity; an unknown one is not found, a closed
one a conflict; a key is needed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from taktus.components.process.application.service.proposals import ProposalError
from taktus.components.process.domain.model import CorrectedCase, Evaluation, EvaluationCase

from .conftest import TENANT, Services

type Client = tuple[httpx.AsyncClient, Services, str]

AT = datetime(2026, 10, 23, 9, 0, tzinfo=UTC)


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def case(state: str = "proposed") -> CorrectedCase:
    return CorrectedCase.model_validate(
        {
            "id": "cor-1",
            "tenant": "acme",
            "process_id": "replies",
            "case": EvaluationCase(
                id="cor-1", inputs={"message": "late"}, targets={"draft": "Sorry."}
            ).document(),
            "state": state,
            "source_run": "run_1",
            "source_step": "draft",
            "proposed_at": AT.isoformat(),
        }
    )


class Evaluations:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def of_process(self, tenant: str, process_id: str) -> list[Evaluation]:
        return [await self.get(tenant, process_id, "evl_1")]

    async def get(self, tenant: str, process_id: str, evaluation_id: str) -> Evaluation:
        if evaluation_id != "evl_1":
            raise ProposalError("unknown", f"no evaluation {evaluation_id!r}")
        return Evaluation.model_validate(
            {
                "id": "evl_1",
                "tenant": tenant,
                "process_id": process_id,
                "purpose": "drift",
                "version": f"{process_id}@1",
                "acting_for": "idn_ada",
                "state": "scored",
                "verdict": "steady",
                "sides": [
                    {
                        "side": "active",
                        "version": f"{process_id}@1",
                        "score": 0.9,
                        "cases": 1,
                        "unscored": 0,
                    }
                ],
                "started_at": AT.isoformat(),
            }
        )

    async def cases_of(self, tenant: str, process_id: str) -> list[CorrectedCase]:
        return [case()]

    async def confirm(
        self, tenant: str, process_id: str, case_id: str, by: str, target: Any = None
    ) -> CorrectedCase:
        self.calls.append(("confirm", (tenant, process_id, case_id, by, target)))
        if case_id != "cor-1":
            raise ProposalError("closed", f"the case {case_id} is confirmed")
        return case("confirmed")

    async def reject(self, tenant: str, process_id: str, case_id: str, by: str) -> CorrectedCase:
        self.calls.append(("reject", (tenant, process_id, case_id, by)))
        return case("rejected")


async def test_the_evaluations_are_read_with_their_scores(client: Client) -> None:
    http, given, base = client
    given.evaluated = Evaluations()
    key = await given.linked()
    listed = await http.get(f"{base}/processes/replies/evaluations", headers=bearer(key))
    assert [e["verdict"] for e in listed.json()["evaluations"]] == ["steady"]
    one = await http.get(f"{base}/processes/replies/evaluations/evl_1", headers=bearer(key))
    assert one.json()["sides"][0]["score"] == 0.9
    missing = await http.get(f"{base}/processes/replies/evaluations/evl_9", headers=bearer(key))
    assert missing.status_code == 404
    assert (await http.get(f"{base}/processes/replies/evaluations")).status_code == 401


async def test_a_proposed_case_is_confirmed_or_rejected_for_the_keys_identity(
    client: Client,
) -> None:
    http, given, base = client
    given.evaluated = evaluations = Evaluations()
    key = await given.linked()
    cases = await http.get(f"{base}/processes/replies/evaluation-cases", headers=bearer(key))
    assert [c["state"] for c in cases.json()["cases"]] == ["proposed"]
    confirmed = await http.post(
        f"{base}/processes/replies/evaluation-cases/cor-1/confirm",
        json={"target": "We are sorry."},
        headers=bearer(key),
    )
    assert confirmed.status_code == 200 and confirmed.json()["state"] == "confirmed"
    rejected = await http.post(
        f"{base}/processes/replies/evaluation-cases/cor-1/reject", headers=bearer(key)
    )
    assert rejected.json()["state"] == "rejected"
    assert evaluations.calls[0] == (
        "confirm",
        (TENANT, "replies", "cor-1", "idn_ada", "We are sorry."),
    )
    closed = await http.post(
        f"{base}/processes/replies/evaluation-cases/cor-2/confirm", json={}, headers=bearer(key)
    )
    assert closed.status_code == 409
