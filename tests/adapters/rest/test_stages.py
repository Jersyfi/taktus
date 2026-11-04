"""A tenant's introduction in stages on the HTTP surface (UC-9.6, ADR-0137, ADR-0191).

The view is read with each stage's state, condition in words, figures, what is missing and the
processes it adds; a stage is opened for the key's identity; both are for the holders of the
plan's responsible role alone; a refusal is a conflict with its reason. What the view computes
is held by `tests/governance/test_stages.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from taktus.components.governance.application.service import StagesRefused
from taktus.components.governance.domain.model import (
    ProcessEvidence,
    Stage,
    StagePlan,
    StageState,
    StageView,
)

from .conftest import TENANT, Services

type Client = tuple[httpx.AsyncClient, Services, str]

AT = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
ROLE = "operations"
STAGE = Stage.model_validate(
    {
        "id": "control-loop",
        "name": "The control loop",
        "processes": {"b-7-01": 2},
        "condition": {"weeks": 4, "reports_missed": 0},
    }
)


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


class FakeStages:
    def __init__(self) -> None:
        self.opened: list[tuple[str, str, str | None]] = []

    async def plan(self, tenant: str) -> StagePlan:
        return StagePlan(
            id=tenant, tenant=tenant, responsible=ROLE, stages=(STAGE,), configured_at=AT
        )

    def _view(self, state: StageState) -> StageView:
        return StageView(
            stage=STAGE,
            position=0,
            state=state,
            holds=False,
            missing=("t runs no version of b-7-01", "a person's approval"),
            processes=(ProcessEvidence(process="b-7-01", granted=2),),
        )

    async def view(self, tenant: str) -> list[StageView]:
        return [self._view(StageState.CLOSED)]

    async def open(self, tenant: str, stage_id: str, *, by: str | None) -> StageView:
        self.opened.append((tenant, stage_id, by))
        if stage_id == "control-loop":
            raise StagesRefused("not_run", "t runs no version of b-7-01")
        raise StagesRefused("unknown", f"no stage {stage_id!r}")


async def responsible(given: Services) -> str:
    _, key = await given.identity.directory.add(TENANT, "idn_op", (TENANT,), roles=(ROLE,))
    return key


async def test_the_stages_are_read_with_their_evidence_by_the_responsible_role(
    client: Client,
) -> None:
    http, given, base = client
    given.stages = FakeStages()
    key = await responsible(given)
    answer = await http.get(f"{base}/stages", headers=bearer(key))
    assert answer.status_code == 200
    body = answer.json()
    assert body["summary"] == "1 stages declared; none is open yet."
    [stage] = body["stages"]
    assert stage["state"] == "closed"
    assert stage["condition"] == [
        "open for at least 4 week(s)",
        "at most 0 day(s) without the daily report",
    ]
    assert stage["processes"][0] == {
        "process": "b-7-01",
        "granted": 2,
        "runs": 0,
        "missed": 0,
        "incidents": 0,
    }, "a process the tenant runs no version of has no version and no level"
    assert "Missing: t runs no version of b-7-01" in stage["text"]


async def test_only_the_responsible_role_reads_and_opens_and_a_key_is_needed(
    client: Client,
) -> None:
    http, given, base = client
    given.stages = FakeStages()
    other = await given.linked()
    assert (await http.get(f"{base}/stages")).status_code == 401
    refused = await http.get(f"{base}/stages", headers=bearer(other))
    assert refused.status_code == 403 and "'operations'" in refused.json()["detail"]
    opened = await http.post(f"{base}/stages/control-loop/open", headers=bearer(other))
    assert opened.status_code == 403 and given.stages.opened == []


async def test_a_stage_is_opened_for_the_keys_identity_and_a_refusal_says_why(
    client: Client,
) -> None:
    http, given, base = client
    given.stages = stages = FakeStages()
    key = await responsible(given)
    refused = await http.post(f"{base}/stages/control-loop/open", headers=bearer(key))
    assert refused.status_code == 409
    assert refused.json()["detail"] == "refused (not_run): t runs no version of b-7-01"
    unknown = await http.post(f"{base}/stages/nowhere/open", headers=bearer(key))
    assert unknown.status_code == 404
    assert stages.opened[0] == (TENANT, "control-loop", "idn_op")
