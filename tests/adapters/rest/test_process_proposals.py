"""The processes Taktus proposes, on the HTTP surface (UC-4.4, ADR-0270): a person reads the
proposals drawn from their own work and those that concern nobody, never another person's, and
accepts or declines each on its own. What the list finds is held by
`tests/composition/test_process_proposals.py`; here, what the surface shows and to whom."""

from __future__ import annotations

from datetime import timedelta

import httpx

from taktus.components.run.domain.model import Run
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerRefs

from .conftest import TENANT, Services, a_run

type Client = tuple[httpx.AsyncClient, Services, str]


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def started_by_hand(given: Services, identity: str, process: str, times: int) -> None:
    """`times` runs of `process` started by `identity` a week apart, no trigger among them."""
    for n in range(times):
        async with given.persistence.transaction(TENANT):
            await given.ledger.record(
                TENANT,
                Fact(
                    kind="run.created",
                    refs=LedgerRefs(
                        tenant=TENANT,
                        actor=identity,
                        run_id=f"run_{process}_{n}",
                        process_version=f"{process}@1",
                    ),
                ),
            )
        given.clock.current += timedelta(days=7)


class Asked:
    def __init__(self, given: Services) -> None:
        self.given = given
        self.asked: list[tuple[str, str, str]] = []

    async def ask(self, tenant: str, process_id: str, request: str, by: str) -> Run:
        self.asked.append((process_id, request, by))
        return await a_run(self.given, "run_building")


async def test_a_person_sees_their_own_proposal_and_nobody_else_does(client: Client) -> None:
    http, given, base = client
    _, bob_key = await given.identity.person(TENANT, "idn_bob")
    ann_key = await given.linked("idn_ada")
    await started_by_hand(given, "idn_ada", "weekly-report", 4)

    mine = await http.get(f"{base}/process-proposals", headers=bearer(ann_key))
    assert mine.status_code == 200, mine.text
    body = mine.json()
    assert body["order"] == "how often the work recurs per 30 days"
    (proposal,) = body["proposals"]
    assert proposal["process_id"] == "weekly-report" and proposal["yours"] is True
    assert proposal["order"].startswith("recurs ")
    assert {"takes_over", "cost", "why_now"} <= proposal.keys()
    assert "idn_ada" not in mine.text, "a proposal never names whom it is drawn from"

    theirs = await http.get(f"{base}/process-proposals", headers=bearer(bob_key))
    assert theirs.json()["proposals"] == [], "shown to the person whose work it is, only"


async def test_only_a_person_s_key_reads_it_and_an_agent_s_key_proves_nothing(
    client: Client,
) -> None:
    http, given, base = client
    key = await given.linked("idn_ada")
    agent = await http.post(f"{base}/identity/agent-key", headers=bearer(key))
    assert agent.status_code == 201, agent.text
    agent_key = agent.json()["agent_key"]
    assert (await http.get(f"{base}/process-proposals")).status_code == 401
    refused = await http.get(f"{base}/process-proposals", headers=bearer(agent_key))
    assert refused.status_code == 401, "an agent's key is not a person's account key"


async def test_each_is_accepted_or_declined_on_its_own_and_only_once(client: Client) -> None:
    http, given, base = client
    key = await given.linked("idn_ada")
    _, bob_key = await given.identity.person(TENANT, "idn_bob")
    asked = Asked(given)
    given.asking = asked
    await started_by_hand(given, "idn_ada", "weekly-report", 4)
    await started_by_hand(given, "idn_ada", "monthly-close", 3)
    listed = (await http.get(f"{base}/process-proposals", headers=bearer(key))).json()
    first, second = (p["id"] for p in listed["proposals"])

    foreign = await http.post(f"{base}/process-proposals/{first}/accept", headers=bearer(bob_key))
    assert foreign.status_code == 404, "only the person it is shown to decides it"

    accepted = await http.post(f"{base}/process-proposals/{first}/accept", headers=bearer(key))
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["run_id"] == "run_building"
    assert [(p, by) for p, _, by in asked.asked] == [
        (listed["proposals"][0]["process_id"], "idn_ada")
    ]

    declined = await http.post(f"{base}/process-proposals/{second}/decline", headers=bearer(key))
    assert declined.status_code == 200, declined.text
    again = await http.post(f"{base}/process-proposals/{second}/decline", headers=bearer(key))
    assert again.status_code == 404, "a decided proposal is decided once"
    left = (await http.get(f"{base}/process-proposals", headers=bearer(key))).json()
    assert left["proposals"] == []


async def test_accepting_where_no_request_path_builds_a_process_is_refused(client: Client) -> None:
    http, given, base = client
    key = await given.linked("idn_ada")
    await started_by_hand(given, "idn_ada", "weekly-report", 4)
    (proposal,) = (await http.get(f"{base}/process-proposals", headers=bearer(key))).json()[
        "proposals"
    ]
    refused = await http.post(
        f"{base}/process-proposals/{proposal['id']}/accept", headers=bearer(key)
    )
    assert refused.status_code == 400
    assert "no request path" in refused.json()["detail"]
    still = (await http.get(f"{base}/process-proposals", headers=bearer(key))).json()
    assert len(still["proposals"]) == 1, "nothing was decided"
