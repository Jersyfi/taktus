"""A unit limit's harm report in the views of the administrator, management and the team
affected, and in the export (UC-8.10 §2, ADR-0299 §2, ADR-0241).

The report is the incident `limit.harmful` the governance component raised to the limit's role
(ADR-0282 §4). The views read it as the figure `limit.held_seconds` of the limit's unit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from fakes.takeover import instructed

from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.governance.domain.model.incident import Incident, IncidentKind
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import Process, ProcessVersion

from .conftest import TENANT, Services
from .test_process_level import bearer
from .test_roles import BUNDLE

type Client = tuple[httpx.AsyncClient, Services, str]

FACTS: dict[str, str | float | None] = {
    "unit": "sales/field",
    "role": "finance-lead",
    "period": "2026-11",
    "held_runs": 3.0,
    "held_seconds": 5400.0,
    "processes": "invoice",
    "window_days": 7.0,
    "exceeded": "runs",
    "benefit": "3 run(s) and 5400 s held in 7 day(s) would have gone on",
    "decision": "a person's; Taktus never changes the limit (ADR-0282 §4)",
    "limit": "field_month",
    "individually": "no",
    "amount_money.usd": 100.0,
    "recommended_money.usd": 160.0,
    "cost_money.usd": 60.0,
    "held_seconds.invoice": 5400.0,
}


async def reported(given: Services) -> None:
    register = RegisterProcessVersionHandler(
        MemoryRepository(given.persistence, ProcessVersion),
        given.persistence,
        MemoryRepository(given.persistence, Process),
        ledger=given.ledger,
    )
    await register.execute(
        RegisterProcessVersion(instructed(BUNDLE), tenant=TENANT, by="idn_owner")
    )
    incidents = MemoryRepository(given.persistence, Incident)
    async with given.persistence.transaction(TENANT):
        await incidents.put(
            TENANT,
            Incident(
                id="inc_limit",
                tenant=TENANT,
                kind=IncidentKind.LIMIT_HARMFUL,
                process_id="limit:field_month",
                process_version="invoice@1",
                rule="limit.harmful",
                facts=FACTS,
                raised_at=datetime(2026, 11, 12, 9, 0, tzinfo=UTC),
            ),
        )


def held(figures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [f for f in figures if f["id"] == "limit.held_seconds"]


async def test_a_limit_s_harm_report_is_in_the_views_of_administration_management_and_team(
    client: Client,
) -> None:
    http, given, base = client
    _, owner = await given.identities.add(TENANT, "idn_owner", (TENANT,), roles=("owner",))
    _, ada = await given.identities.add(TENANT, "idn_ada", (TENANT,), roles=("accounting",))
    await reported(given)

    views = (await http.get(f"{base}/views", headers=bearer(owner))).json()
    by_view = {v["id"]: held(v["figures"]) for v in views["views"]}
    for name, scope, subject in (
        ("administration", "unit", "sales/field"),
        ("management", "process", "invoice"),
        ("team", "process", "invoice"),
    ):
        (figure,) = by_view[name]
        assert (figure["scope"], figure["subject"], figure["value"]) == (
            scope,
            subject,
            5400.0,
        ), name
    basis = by_view["administration"][0]["basis"]
    assert basis["limit"] == "field_month" and basis["held_runs"] == 3.0
    assert basis["recommended_money.usd"] == 160.0 and basis["cost_money.usd"] == 60.0
    assert "would have gone on" in basis["benefit"]
    assert "idn_" not in str(basis), "the report names a role, never a person"

    export = (await http.get(f"{base}/figures", headers=bearer(owner))).json()
    exported = held(export["figures"])
    assert {(f["scope"], f["subject"]) for f in exported} == {
        ("unit", "sales/field"),
        ("process", "invoice"),
    }
    assert all(f["value"] == 5400.0 and f["component"] == "governance" for f in exported)

    nothing = (await http.get(f"{base}/figures", headers=bearer(ada))).json()
    assert held(nothing["figures"]) == [], "a role not entitled to it does not see it"
