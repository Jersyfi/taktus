"""The whole HTTP surface, under the root and under a non-root prefix: health, readiness,
intake through the connector port, the read API for runs and ledger entries, and RFC 9457
problem details for every error."""

from __future__ import annotations

import httpx

from taktus.adapters.driving.rest import build_app
from taktus.ports.connector import ConnectorError

from .conftest import TENANT, ScriptedConnector, Services, a_run, refused, services

type Client = tuple[httpx.AsyncClient, Services, str]


def is_problem(response: httpx.Response, status: int) -> dict[str, object]:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    body: dict[str, object] = response.json()
    assert body["status"] == status and body["type"] == "about:blank"
    assert isinstance(body["title"], str) and isinstance(body["detail"], str)
    return body


async def test_health_says_alive_and_readiness_asks_the_services(client: Client) -> None:
    http, given, base = client
    assert (await http.get(f"{base}/health")).json() == {"status": "alive"}
    ready = await http.get(f"{base}/ready")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "roles": ["api", "runner"], "leading": False}
    given.not_ready_reason = "the database at postgresql://db/taktus did not answer"
    given.leading = True
    problem = is_problem(await http.get(f"{base}/ready"), 503)
    assert problem["title"] == "Not ready" and "did not answer" in str(problem["detail"])
    assert (await http.get(f"{base}/health")).status_code == 200, "not ready is not unhealthy"


async def test_nothing_answers_outside_the_prefix(prefix: str, client: Client) -> None:
    http, _, base = client
    if prefix == "/":
        return
    for path in ("/health", "/ready", "/runs", "/intake/channel.repo"):
        assert (await http.get(path)).status_code == 404, f"{path} outside the prefix"
    assert (await http.get(f"{base}/health")).status_code == 200


async def test_an_unknown_path_and_a_wrong_method_are_problems(client: Client) -> None:
    http, _, base = client
    is_problem(await http.get(f"{base}/nothing"), 404)
    is_problem(await http.delete(f"{base}/health"), 405)


async def test_runs_are_read_newest_first_and_a_missing_one_is_a_problem(client: Client) -> None:
    http, given, base = client
    assert (await http.get(f"{base}/runs")).json() == {"tenant": TENANT, "runs": []}
    first = await a_run(given, "run_1")
    second = await a_run(given, "run_2")
    listed = (await http.get(f"{base}/runs")).json()
    assert [r["id"] for r in listed["runs"]] == ["run_2", "run_1"]
    assert listed["runs"][1] == first.document() and listed["runs"][0] == second.document()
    one = await http.get(f"{base}/runs/run_1")
    assert one.status_code == 200 and one.json() == first.document()
    problem = is_problem(await http.get(f"{base}/runs/run_9"), 404)
    assert "run_9" in str(problem["detail"])
    assert (await http.get(f"{base}/runs", params={"tenant": "other"})).json()["runs"] == []


async def test_the_ledger_of_a_run_comes_with_the_chain_s_verification(client: Client) -> None:
    http, given, base = client
    await a_run(given, "run_1")
    ledger = (await http.get(f"{base}/runs/run_1/ledger")).json()
    assert ledger["run_id"] == "run_1"
    assert [e["kind"] for e in ledger["entries"]] == ["run.created"]
    assert ledger["entries"][0]["refs"]["run_id"] == "run_1"
    assert ledger["chain"] == {"intact": True, "entries": 1}
    is_problem(await http.get(f"{base}/runs/run_9/ledger"), 404)


async def test_an_accepted_delivery_is_kept_awaiting_identity(client: Client) -> None:
    http, given, base = client
    response = await http.post(
        f"{base}/intake/channel.repo",
        content=b'{"action": "created"}',
        headers={"X-Hub-Signature-256": "sha256=abc", "X-GitHub-Event": "issue_comment"},
    )
    assert response.status_code == 202, response.text
    accepted = response.json()["accepted"]
    assert accepted["id"] == "dlv_1" and accepted["status"] == "awaiting_identity"
    assert accepted["sender_account"] == "100200" and accepted["tenant"] == TENANT
    delivery = given.connector.deliveries[0]
    assert delivery.body == '{"action": "created"}', "the raw body, byte for byte"
    assert delivery.headers["x-hub-signature-256"] == "sha256=abc"
    async with given.persistence.transaction(TENANT):
        stored = await given.events.get(TENANT, "dlv_1")
    assert stored is not None and stored.intent == "@taktus turn this into a pull request"
    again = await http.post(f"{base}/intake/channel.repo", content=b"{}")
    assert again.status_code == 202
    async with given.persistence.transaction(TENANT):
        assert len(await given.events.list(TENANT)) == 1, "a redelivery replaces, never doubles"


async def test_refusals_answer_with_the_status_that_says_who_should_act(prefix: str) -> None:
    cases = {
        "unsigned": 401,
        "bad_signature": 401,
        "malformed": 400,
        "unsupported_event": 202,
        "own_action": 202,
    }
    base = "" if prefix == "/" else prefix
    for reason, status in cases.items():
        given = services(ScriptedConnector(refused(reason, f"because {reason}")))
        app_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=__import__("taktus.adapters.driving.rest", fromlist=["build_app"]).build_app(
                    given, prefix=prefix
                )
            ),
            base_url="http://taktus.test",
        )
        async with app_client as http:
            response = await http.post(f"{base}/intake/channel.repo", content=b"x")
            assert response.status_code == status, reason
            if status == 202:
                assert response.json() == {
                    "refused": {"reason": reason, "detail": f"because {reason}"}
                }
            else:
                problem = is_problem(response, status)
                assert problem["reason"] == reason and problem["title"] == "Refused"
        async with given.persistence.transaction(TENANT):
            assert await given.events.list(TENANT) == [], "a refusal leaves nothing behind"


async def test_an_unknown_channel_and_a_silent_connector_are_problems(prefix: str) -> None:
    base = "" if prefix == "/" else prefix
    given = services(ScriptedConnector(ConnectorError("the connector at x did not answer")))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=build_app(given, prefix=prefix)),
        base_url="http://taktus.test",
    ) as http:
        problem = is_problem(await http.post(f"{base}/intake/channel.chat", content=b"x"), 404)
        assert "channel.chat" in str(problem["detail"])
        problem = is_problem(await http.post(f"{base}/intake/channel.repo", content=b"x"), 503)
        assert "did not answer" in str(problem["detail"])


async def test_without_the_api_role_only_health_and_readiness_are_served(prefix: str) -> None:
    base = "" if prefix == "/" else prefix
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=build_app(services(), prefix=prefix, full=False)),
        base_url="http://taktus.test",
    ) as http:
        assert (await http.get(f"{base}/health")).status_code == 200
        assert (await http.get(f"{base}/ready")).status_code == 200
        assert (await http.get(f"{base}/runs")).status_code == 404
        assert (await http.post(f"{base}/intake/channel.repo", content=b"x")).status_code == 404
