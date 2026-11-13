"""A run started from the web app that needs much shows its estimated demand first, and starts
once the person accepts it (UC-8.10 §2, ADR-0299 §1). What `RunEngine.demand` estimates is held
by `tests/components/run/test_run_demand.py`; here the engine says the run needs much."""

from __future__ import annotations

from typing import Any

import httpx

from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.identity.domain.model import Right
from taktus.shared.v1 import Command

from .conftest import TENANT, Services
from .test_agent_surface import agent, registered
from .test_process_level import bearer
from .test_surface import is_problem

type Client = tuple[httpx.AsyncClient, Services, str]

MUCH: dict[str, Any] = {
    "process": "daily",
    "unit": "ops",
    "estimate": {"money.eur": 40.0},
    "basis": "the mean of the process's 3 finished run(s) since 2026-10-16",
    "mean": {"money.eur": 40.0},
    "most": {"money.eur": 55.0},
    "runs": 3,
    "at_most": {},
    "limits": [
        {
            "limit": "ops_month",
            "unit": "ops",
            "period": "2026-11",
            "remaining": {"money.eur": 60.0},
            "reaches": ["money.eur"],
        }
    ],
    "share": 0.5,
    "much": True,
}


async def test_a_web_start_that_needs_much_shows_its_demand_and_starts_once_accepted(
    client: Client,
) -> None:
    http, given, base = client
    await registered(given)
    await agent(given, "idn_ada", "ops")
    await given.identities.grant(TENANT, "ops", Right.START, by="idn_admin")
    account = await given.identities.issue_key(TENANT, "idn_ada")

    async def much(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return MUCH

    given.agent._engine.demand = much  # type: ignore[method-assign]
    asked = {"inputs": {"target": "x"}}
    refused = await http.post(f"{base}/catalogue/daily/start", json=asked, headers=bearer(account))
    assert is_problem(refused, 409)
    assert refused.json()["demand"]["limits"][0]["limit"] == "ops_month"
    assert "ops_month" in refused.json()["detail"]
    async with given.persistence.transaction(TENANT):
        assert await MemoryRepository(given.persistence, Command).list(TENANT) == [], (
            "nothing is commissioned before the demand is accepted"
        )

    accepted = await http.post(
        f"{base}/catalogue/daily/start",
        json={**asked, "accept_demand": True},
        headers=bearer(account),
    )
    assert accepted.status_code == 201, accepted.text
