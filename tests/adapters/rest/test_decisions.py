"""Decision requests on the control plane's own surface (ADR-0042): the decider's list with
what is overdue, an answer read back and confirmed, and response times only the decider reads
under their name."""

from __future__ import annotations

from datetime import timedelta

import httpx

from taktus.components.decision.application.service import RaiseRequest

from .conftest import TENANT, Services
from .test_surface import is_problem

type Client = tuple[httpx.AsyncClient, Services, str]


async def raised(given: Services, request_id: str = "dr_1") -> str:
    await given.decisions.requests._raising.execute(
        RaiseRequest(
            tenant=TENANT,
            id=request_id,
            run="run_1",
            step="write",
            class_="legal",
            situation="Run run_1 has reached step write, whose act is anchored.",
            question="Does Taktus go ahead with step write?",
            options=[
                {"id": "A", "proposal": "Go ahead.", "recommended": True, "reason": "proposed"},
                {"id": "B", "proposal": "Do not.", "recommended": False},
            ],
            blocking=["run_1"],
            due=given.clock.now().date() + timedelta(days=1),
            decider="finance.lead",
            anchor="anc-write",
        )
    )
    return request_id


async def key_of(given: Services, name: str, *roles: str) -> dict[str, str]:
    _, key = await given.identities.add(TENANT, name, (TENANT, "finance"), roles=roles)
    return {"Authorization": f"Bearer {key}"}


async def test_every_decision_route_needs_an_account_key(client: Client) -> None:
    http, given, base = client
    request_id = await raised(given)
    is_problem(await http.get(f"{base}/decisions"), 401)
    is_problem(await http.get(f"{base}/decisions/response-times"), 401)
    is_problem(await http.get(f"{base}/decisions/{request_id}"), 401)
    is_problem(await http.post(f"{base}/decisions/{request_id}/answer", json={"option": "A"}), 401)
    is_problem(
        await http.post(f"{base}/decisions/{request_id}/confirm", json={"confirmed": True}), 401
    )


async def test_the_decider_lists_answers_and_confirms_and_the_run_is_handed_on(
    client: Client,
) -> None:
    http, given, base = client
    request_id = await raised(given)
    ada = await key_of(given, "idn_ada", "finance.lead")
    outsider = await key_of(given, "idn_cy")

    listed = (await http.get(f"{base}/decisions", headers=ada)).json()
    assert [r["id"] for r in listed["requests"]] == [request_id]
    assert listed["requests"][0]["overdue"] is False and listed["overdue"] == 0
    assert (await http.get(f"{base}/decisions", headers=outsider)).json()["requests"] == []
    is_problem(await http.get(f"{base}/decisions/{request_id}", headers=outsider), 403)
    is_problem(
        await http.post(
            f"{base}/decisions/{request_id}/answer", json={"option": "A"}, headers=outsider
        ),
        403,
    )

    answered = await http.post(
        f"{base}/decisions/{request_id}/answer", json={"text": "A, after lunch"}, headers=ada
    )
    assert answered.status_code == 200, answered.text
    assert "option A" in answered.json()["message"]
    assert answered.json()["request"]["request"]["status"] == "interpreted"
    assert given.continued == [], "an answer read back takes no effect"

    confirmed = await http.post(
        f"{base}/decisions/{request_id}/confirm", json={"confirmed": True}, headers=ada
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["applied"] is True and confirmed.json()["entry"]
    assert given.continued == [(TENANT, "run_1", "idn_ada")]
    is_problem(
        await http.post(f"{base}/decisions/{request_id}/answer", json={"option": "B"}, headers=ada),
        409,
    )


async def test_a_request_past_its_due_date_is_shown_as_such(client: Client) -> None:
    http, given, base = client
    await raised(given)
    ada = await key_of(given, "idn_ada", "finance.lead")
    given.clock.current += timedelta(days=3)
    listed = (await http.get(f"{base}/decisions", headers=ada)).json()
    assert listed["overdue"] == 1 and listed["requests"][0]["overdue"] is True


async def test_nobody_reads_a_deciders_response_time_under_their_name(client: Client) -> None:
    http, given, base = client
    request_id = await raised(given)
    ada = await key_of(given, "idn_ada", "finance.lead")
    bo = await key_of(given, "idn_bo", "finance.lead")
    await http.post(f"{base}/decisions/{request_id}/answer", json={"option": "A"}, headers=ada)

    seen_by_bo = (await http.get(f"{base}/decisions/{request_id}", headers=bo)).json()
    assert "idn_ada" not in str(seen_by_bo) and "reflection" not in seen_by_bo
    await http.post(f"{base}/decisions/{request_id}/confirm", json={"confirmed": True}, headers=ada)

    own = (await http.get(f"{base}/decisions/response-times", headers=ada)).json()
    assert [o["request_id"] for o in own["own"]] == [request_id]
    theirs = (await http.get(f"{base}/decisions/response-times", headers=bo)).json()
    assert theirs.get("own", []) == [] and "idn_ada" not in str(theirs)
    assert all("withheld" in a for a in theirs["by_role"] + theirs["by_department"])
