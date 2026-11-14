"""A person's own agent reaches Taktus over MCP, with a key of its own and the rights of their
role (ADR-0131, UC-1.11).

The surface at `<prefix>/mcp` takes only an agent key; it lists the read tools and the tools that
act whose right a role of the person holds; a tool called without its right is refused, naming
it, and nothing changes; a run another tenant's reader may not see is answered as one that does
not exist; a process is started as the person and runs; a free-text answer to a decision request
takes effect only once confirmed; the take-over tools of ADR-0128 hand the engine what the person
asked; every call is a ledger entry `agent.<tool>` with the person as actor.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx
import httpx2
from fakes.takeover import instructed
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from taktus.adapters.driven.memory import MemoryRepository
from taktus.adapters.driving.rest import build_app
from taktus.components.identity.domain.model import Right
from taktus.components.process.application.service.proposals import Propose
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.run.application.service import ResumeRun
from taktus.components.run.domain.model import RunState

from .conftest import OTHER, TENANT, Services, a_run, services
from .test_decisions import raised
from .test_surface import is_problem

type Client_ = tuple[httpx.AsyncClient, Services, str]
type Json = dict[str, Any]

READS = {
    "list_plans",
    "get_plan",
    "list_proposals",
    "get_proposal",
    "list_processes",
    "list_runs",
    "get_run",
    "list_decisions",
    "get_decision",
    "show_takeover",
}


def bundle() -> Json:
    return {
        "id": "daily",
        "version": "1",
        "name": "Daily",
        "autonomy": {"level": 3, "reason": "a test", "toward_next": "nothing"},
        "inputs": {"target": {"description": "what to read", "example": "a"}},
        "steps": [
            {
                "id": "one",
                "method": "rule",
                "reason": "a fixed value",
                "rejected": [],
                "exactness": "exact",
                "checks": [{"kind": "recomputation"}],
                "work": {"rule": "constant", "value": {"$input": "target"}},
            }
        ],
        "limits": {"quota": {"units": 5}},
    }


async def registered(given: Services) -> None:
    await RegisterProcessVersionHandler(
        MemoryRepository(given.persistence, ProcessVersion),
        given.persistence,
        MemoryRepository(given.persistence, Process),
        ledger=given.ledger,
    ).execute(RegisterProcessVersion(instructed(bundle()), tenant=TENANT, by="idn_admin"))


async def agent(given: Services, name: str, *roles: str, tenant: str = TENANT) -> str:
    """An identity holding the roles, and the agent key it gives its own agent."""
    await given.identities.add(tenant, name, (tenant, "ops"), roles=roles)
    return await given.identities.issue_agent_key(tenant, name)


async def rpc(
    http: httpx.AsyncClient, base: str, key: str | None, method: str, params: Json
) -> Any:
    headers = {"Accept": "application/json, text/event-stream"}
    if key is not None:
        headers["Authorization"] = f"Bearer {key}"
    return await http.post(
        f"{base}/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        headers=headers,
    )


async def tools(http: httpx.AsyncClient, base: str, key: str) -> set[str]:
    response = await rpc(http, base, key, "tools/list", {})
    assert response.status_code == 200, response.text
    return {t["name"] for t in response.json()["result"]["tools"]}


async def call(http: httpx.AsyncClient, base: str, key: str, name: str, **arguments: Any) -> Json:
    """The tool's answer: its structured content, and whether it is an error."""
    response = await rpc(http, base, key, "tools/call", {"name": name, "arguments": arguments})
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    return {"error": result.get("isError", False), **(result.get("structuredContent") or {})}


async def entries(given: Services, kind_prefix: str = "agent.") -> list[tuple[str, str, str]]:
    async with given.persistence.transaction(TENANT):
        listed = await given.ledger.entries(TENANT)
    return [
        (e.kind, str(e.outcome), str(e.refs.actor))
        for e in listed
        if e.kind.startswith(kind_prefix)
    ]


async def test_only_an_agent_key_opens_the_surface(client: Client_) -> None:
    http, given, base = client
    _, account_key = await given.identity.person(TENANT, "idn_ada")
    key = await given.identities.issue_agent_key(TENANT, "idn_ada")

    is_problem(await rpc(http, base, None, "tools/list", {}), 401)
    is_problem(await rpc(http, base, account_key, "tools/list", {}), 401)
    is_problem(await rpc(http, base, "tkg_" + "0" * 64, "tools/list", {}), 401)
    assert (await rpc(http, base, key, "tools/list", {})).status_code == 200

    # The HTTP surface never takes the agent key: the agent has no way round its rights.
    is_problem(await http.get(f"{base}/runs", headers={"Authorization": f"Bearer {key}"}), 401)

    replaced = await given.identities.issue_agent_key(TENANT, "idn_ada")
    is_problem(await rpc(http, base, key, "tools/list", {}), 401)
    assert (await rpc(http, base, replaced, "tools/list", {})).status_code == 200


async def test_without_a_right_the_agent_only_reads_and_a_write_is_refused(
    client: Client_,
) -> None:
    http, given, base = client
    await registered(given)
    key = await agent(given, "idn_ada", "ops")

    assert await tools(http, base, key) == READS
    refused = await call(http, base, key, "start_process", process="daily", inputs={"target": "x"})
    assert refused["error"] and "agent.start" in refused["refused"]
    async with given.persistence.transaction(TENANT):
        assert await given.runs.list(TENANT) == [], "a refused write changes nothing"
    assert await entries(given) == [("agent.start_process", "refused", "idn_ada")]


async def test_a_right_granted_to_a_role_lists_its_tools_and_starts_a_process_as_the_person(
    client: Client_,
) -> None:
    http, given, base = client
    await registered(given)
    key = await agent(given, "idn_ada", "ops")
    await given.identities.grant(TENANT, "ops", Right.START, by="idn_admin")

    assert await tools(http, base, key) == READS | {"start_process"}
    (process,) = (await call(http, base, key, "list_processes"))["processes"]
    assert process["process"] == "daily" and process["inputs"]["target"]["required"] is True

    missing = await call(http, base, key, "start_process", process="daily")
    assert missing["error"] and "target" in missing["refused"]
    started = await call(http, base, key, "start_process", process="daily", inputs={"target": "x"})
    assert not started["error"], started
    async with given.persistence.transaction(TENANT):
        run = await given.runs.get(TENANT, started["run_id"])
        assert run is not None and run.identity == "idn_ada"
        assert given.queue is not None
        (job,) = await given.queue.claim(TENANT, "runner-a", 5)
    finished = await given.agent._engine.resume(
        ResumeRun(run_id=run.id, actor="runner-a", tenant=TENANT, on_claim=True)
    )
    assert finished.state is RunState.FINISHED and job.payload == {"run_id": run.id}

    seen = await call(http, base, key, "get_run", run_id=run.id)
    assert seen["id"] == run.id and seen["state"] == "finished"
    assert [r["id"] for r in (await call(http, base, key, "list_runs"))["runs"]] == [run.id]

    await given.identities.withdraw(TENANT, "ops", Right.START, by="idn_admin")
    assert await tools(http, base, key) == READS, "a right withdrawn holds from the next call"
    assert ("agent.start_process", "served", "idn_ada") in await entries(given)
    assert {k for k, _, _ in await entries(given, "identity.right")} == {
        "identity.right_granted",
        "identity.right_withdrawn",
    }


async def test_a_run_the_reader_may_not_see_is_answered_as_one_that_does_not_exist(
    client: Client_,
) -> None:
    http, given, base = client
    await a_run(given, "run_other", tenant=OTHER)
    await a_run(given, "run_1")
    key = await agent(given, "idn_ada", "ops")
    await given.identities.grant(TENANT, "ops", Right.TAKE_OVER, by="idn_admin")

    assert [r["id"] for r in (await call(http, base, key, "list_runs"))["runs"]] == ["run_1"]
    hidden = await call(http, base, key, "get_run", run_id="run_other")
    assert hidden["error"] and hidden["refused"] == "no run 'run_other' that you may see"
    taken = await call(http, base, key, "take_over_step", run_id="run_other", step_id="a")
    assert taken["error"] and given.takeovers.asked == []


async def test_a_free_text_answer_is_read_back_and_counts_only_once_confirmed(
    client: Client_,
) -> None:
    http, given, base = client
    request_id = await raised(given)
    key = await agent(given, "idn_ada", "finance.lead")
    outsider = await agent(given, "idn_cy", "ops")
    await given.identities.grant(TENANT, "finance.lead", Right.ANSWER, by="idn_admin")
    await given.identities.grant(TENANT, "ops", Right.ANSWER, by="idn_admin")

    listed = await call(http, base, key, "list_decisions")
    assert [r["id"] for r in listed["requests"]] == [request_id]
    assert (await call(http, base, outsider, "list_decisions"))["requests"] == []
    assert (await call(http, base, outsider, "get_decision", request_id=request_id))["error"]
    assert (await call(http, base, outsider, "answer_decision", request_id=request_id, option="A"))[
        "error"
    ]

    answered = await call(
        http, base, key, "answer_decision", request_id=request_id, text="A, after lunch"
    )
    assert not answered["error"] and "option A" in answered["message"]
    assert answered["request"]["request"]["status"] == "interpreted"
    assert given.continued == [], "an answer read back takes no effect"

    confirmed = await call(
        http, base, key, "confirm_decision", request_id=request_id, confirmed=True
    )
    assert confirmed["applied"] is True and confirmed["entry"]
    assert given.continued == [(TENANT, "run_1", "idn_ada")]


async def test_a_step_is_taken_over_shown_and_handed_back_by_the_agent_as_the_person(
    client: Client_,
) -> None:
    http, given, base = client
    await a_run(given, "run_1")
    key = await agent(given, "idn_ada", "ops")
    await given.identities.grant(TENANT, "ops", Right.TAKE_OVER, by="idn_admin")
    assert {"take_over_step", "hand_back"} <= await tools(http, base, key)

    asked = await call(http, base, key, "take_over_step", run_id="run_1", step_id="a")
    assert asked == {
        "error": False,
        "takeover": "tko_1",
        "run_id": "run_1",
        "step_id": "a",
        "state": "asked",
    }
    (command,) = given.takeovers.asked
    assert (command.actor, command.tenant) == ("idn_ada", TENANT)

    assert (await call(http, base, key, "show_takeover", run_id="run_1", takeover_id="tko_1"))[
        "error"
    ], "asked, not yet served"
    given.takeovers.states["tko_1"] = {"kind": "takeover.state", "goal": "g"}
    shown = await call(http, base, key, "show_takeover", run_id="run_1", takeover_id="tko_1")
    assert shown["state"]["goal"] == "g"

    handed = await call(
        http, base, key, "hand_back", run_id="run_1", takeover_id="tko_1", result={"answer": 42}
    )
    assert not handed["error"] and handed["run_id"] == "run_1"
    (back,) = given.takeovers.handed
    assert (back.result, back.actor) == ({"answer": 42}, "idn_ada")
    recorded = await entries(given)
    assert ("agent.take_over_step", "served", "idn_ada") in recorded
    assert ("agent.hand_back", "served", "idn_ada") in recorded


async def test_every_call_is_in_the_ledger_with_the_person_and_no_argument(
    client: Client_,
) -> None:
    http, given, base = client
    key = await agent(given, "idn_ada", "ops")
    await call(http, base, key, "list_runs")
    await call(http, base, key, "get_run", run_id="run_secret-name")
    await call(http, base, key, "no_such_tool")
    async with given.persistence.transaction(TENANT):
        listed = [e for e in await given.ledger.entries(TENANT) if e.kind.startswith("agent.")]
    assert [(e.kind, e.outcome, e.refs.actor) for e in listed] == [
        ("agent.list_runs", "served", "idn_ada"),
        ("agent.get_run", "refused", "idn_ada"),
        ("agent.unknown", "refused", "idn_ada"),
    ]
    assert listed[1].refs.run_id == "run_secret-name"
    assert all("secret" not in str(e.content_digest) for e in listed)


async def test_an_agent_of_the_protocols_own_client_reaches_the_tools() -> None:
    given = services()
    await registered(given)
    key = await agent(given, "idn_ada", "ops")
    app = build_app(given, prefix="/taktus")
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        base_url="http://taktus.test",
        headers={"Authorization": f"Bearer {key}"},
    ) as http:
        transport = streamable_http_client("http://taktus.test/taktus/mcp", http_client=http)
        async with Client(transport) as session:
            listed = await session.list_tools()
            assert {t.name for t in listed.tools} == READS
            answer = await session.call_tool("list_processes", {})
    assert not answer.is_error
    assert answer.structured_content is not None
    assert [p["process"] for p in answer.structured_content["processes"]] == ["daily"]


async def test_the_person_creates_their_agents_key_with_their_account_key(
    client: Client_,
) -> None:
    http, given, base = client
    is_problem(await http.post(f"{base}/identity/agent-key"), 401)
    await given.identities.add(TENANT, "idn_ada", (TENANT,), roles=("ops",))
    account_key = await given.identities.issue_key(TENANT, "idn_ada")
    await given.identities.grant(TENANT, "ops", Right.ANSWER, by="idn_admin")

    created = await http.post(
        f"{base}/identity/agent-key", headers={"Authorization": f"Bearer {account_key}"}
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["identity"] == "idn_ada" and body["rights"] == ["agent.answer"]
    assert body["agent_key"].startswith("tkg_")
    assert "answer_decision" in await tools(http, base, body["agent_key"])
    as_agent = {"Authorization": f"Bearer {body['agent_key']}"}
    is_problem(await http.post(f"{base}/identity/agent-key", headers=as_agent), 401)


async def test_a_running_step_is_sent_a_message_by_the_agent_only_with_the_right(
    client: Client_,
) -> None:
    """ADR-0156 §7: `steer_step` needs the right `agent.steer`; without it the call is refused,
    naming the right, and the engine is never asked."""
    http, given, base = client
    await a_run(given, "run_1")
    key = await agent(given, "idn_ada", "ops")
    assert "steer_step" not in await tools(http, base, key)
    refused = await call(http, base, key, "steer_step", run_id="run_1", step_id="a", text="go")
    assert refused["error"] and "agent.steer" in json.dumps(refused)
    assert given.takeovers.steered == []

    await given.identities.grant(TENANT, "ops", Right.STEER, by="idn_admin")
    assert "steer_step" in await tools(http, base, key)
    sent = await call(http, base, key, "steer_step", run_id="run_1", step_id="a", text="go")
    assert sent == {
        "error": False,
        "message": "msg_0001",
        "run_id": "run_1",
        "step_id": "a",
        "state": "asked",
    }
    (command,) = given.takeovers.steered
    assert (command.text, command.actor, command.tenant) == ("go", "idn_ada", TENANT)
    recorded = await entries(given)
    assert ("agent.steer_step", "served", "idn_ada") in recorded
    assert ("agent.steer_step", "refused", "idn_ada") in recorded


# --- building (ADR-0324, DEC-0239) -------------------------------------------------------------

PLAN_TOOLS = {"open_plan", "answer_plan", "set_plan", "commission_plan", "confirm_act"}
CHANGE_TOOLS = {
    "ask_change",
    "ask_description",
    "rehearse_proposal",
    "commission_proposal",
    "discard_proposal",
    "rollback_process",
    "confirm_act",
}
A_STEP = {"id": "read", "method": "rule", "reason": "a rule", "rejected": [], "exactness": "exact"}
GUIDED: list[tuple[str, Any, str | None]] = [
    ("steps", [A_STEP], None),
    ("due", "2026-12-01T09:00:00+00:00", None),
    ("autonomy_level", 2, None),
    ("autonomy_reason", "a person confirms every reply", None),
    ("estimates", {"figure": 2, "unit": "seconds", "basis": "the last 30 runs"}, "read"),
]


class RecordingActs:
    """The acts on a proposal as the surface reaches them: what was asked, as whom."""

    def __init__(self, given: Services) -> None:
        self.given = given
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    async def ask(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(("ask", args, kwargs))
        return SimpleNamespace(id="run_7")

    async def rehearse(self, tenant: str, process: str, proposal: str, *args: Any) -> Any:
        self.calls.append(("rehearse", (tenant, process, proposal, *args), {}))
        found = await self.given.proposals.get(tenant, process, proposal)
        return found, SimpleNamespace(id="run_8")

    async def commission(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(("commission", args, kwargs))
        return SimpleNamespace(version="2")

    async def rollback(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(("rollback", args, kwargs))
        return SimpleNamespace(version="3")


async def test_an_agent_plans_and_a_commission_counts_only_once_its_reading_is_confirmed(
    client: Client_,
) -> None:
    http, given, base = client
    key = await agent(given, "idn_ada", "ops")
    await given.identities.grant(TENANT, "ops", Right.PLAN, by="idn_admin")
    assert await tools(http, base, key) == READS | PLAN_TOOLS

    opened = await call(http, base, key, "open_plan", said="answer supplier invoices")
    assert not opened["error"], opened
    draft = opened["draft"]
    for field, value, step in GUIDED:
        asked = await call(http, base, key, "get_plan", draft=draft)
        assert asked["question"]["field"] == field
        arguments: Json = {"draft": draft, "field": field, "value": value}
        if step is not None:
            arguments["step_id"] = step
        assert not (await call(http, base, key, "answer_plan", **arguments))["error"]
    assert (await call(http, base, key, "get_plan", draft=draft))["missing"] == []

    read = await call(http, base, key, "commission_plan", draft=draft)
    assert not read["error"], read
    assert draft in read["read_back"] and "answer supplier invoices" in read["read_back"]
    unchanged = await call(http, base, key, "get_plan", draft=draft)
    assert unchanged["commissioned"] is False, "a commission read back takes no effect"

    done = await call(http, base, key, "confirm_act", act=read["act"], confirmed=True)
    assert done["state"] == "done" and done["plan"] == f"{draft}@v6", done
    assert (await call(http, base, key, "get_plan", draft=draft))["commissioned"] is True
    again = await call(http, base, key, "confirm_act", act=read["act"], confirmed=True)
    assert again["error"] and "done already" in again["refused"]

    recorded = await entries(given)
    assert ("agent.commission_plan", "served", "idn_ada") in recorded
    assert ("agent.confirm_act", "served", "idn_ada") in recorded
    settled = await entries(given, "conversation.")
    assert ("conversation.act_confirmed", "done", "idn_ada") in settled
    assert [a for k, _, a in await entries(given, "plan.commissioned")] == ["idn_ada"]


async def test_an_agent_asks_rehearses_commissions_discards_and_rolls_back_as_the_person(
    client: Client_,
) -> None:
    http, given, base = client
    await registered(given)
    acts = RecordingActs(given)
    given.acts = acts
    key = await agent(given, "idn_ada", "ops")
    await given.identities.grant(TENANT, "ops", Right.CHANGE, by="idn_admin")
    assert await tools(http, base, key) == READS | CHANGE_TOOLS

    asked = await call(http, base, key, "ask_change", process="daily", request="add a step")
    assert not asked["error"] and (asked["run"], asked["process"]) == ("run_7", "daily")
    assert acts.calls[-1] == ("ask", (TENANT, "daily", "add a step", "idn_ada"), {})
    assert (await call(http, base, key, "ask_change", process="nothing", request="x"))["error"]
    exists = await call(http, base, key, "ask_description", process="daily", description="x")
    assert exists["error"] and "exists already" in exists["refused"]
    described = await call(
        http, base, key, "ask_description", process="weekly", description="a weekly report"
    )
    assert not described["error"]
    assert acts.calls[-1] == ("ask", (TENANT, "weekly", "a weekly report", "idn_ada"), {})

    changed = bundle()
    changed["version"] = "2"
    proposal = await given.proposals.propose(
        Propose(TENANT, "daily", instructed(changed), by="idn_ada", request="v2")
    )
    listed = await call(http, base, key, "list_proposals", process="daily")
    assert [p["id"] for p in listed["proposals"]] == [proposal.id]
    one = await call(http, base, key, "get_proposal", process="daily", proposal=proposal.id)
    assert one["version"] == "2"

    rehearsed = await call(
        http, base, key, "rehearse_proposal", process="daily", proposal=proposal.id
    )
    assert rehearsed["run"] == "run_8"
    assert [c for c, _, _ in acts.calls][-1] == "rehearse"

    read = await call(http, base, key, "commission_proposal", process="daily", proposal=proposal.id)
    assert "version 2 becomes the active version of daily" in read["read_back"]
    assert "commission" not in [c for c, _, _ in acts.calls], "nothing before the yes"
    done = await call(http, base, key, "confirm_act", act=read["act"], confirmed=True)
    assert done["state"] == "done" and done["version"] == "2"
    assert acts.calls[-1] == (
        "commission",
        (TENANT, "daily", proposal.id, "idn_ada"),
        {"approved_by": None, "override": None},
    )

    back = await call(http, base, key, "rollback_process", process="daily", version="1")
    assert "Make version 1 of daily current again" in back["read_back"]
    declined = await call(http, base, key, "confirm_act", act=back["act"], confirmed=False)
    assert declined["state"] == "declined"
    assert [c for c, _, _ in acts.calls].count("rollback") == 0, "a no does nothing"

    discarded = await call(
        http, base, key, "discard_proposal", process="daily", proposal=proposal.id
    )
    assert not discarded["error"]
    assert (await given.proposals.get(TENANT, "daily", proposal.id)).state == "discarded"


async def test_without_the_right_to_build_a_build_tool_or_its_confirmation_is_refused(
    client: Client_,
) -> None:
    http, given, base = client
    key = await agent(given, "idn_ada", "ops")
    refused = await call(http, base, key, "open_plan", said="x")
    assert refused["error"] and "agent.plan" in refused["refused"]
    assert (await call(http, base, key, "list_plans"))["plans"] == [], "a refusal opens nothing"
    asked = await call(http, base, key, "ask_change", process="daily", request="x")
    assert asked["error"] and "agent.change" in asked["refused"]

    await given.identities.grant(TENANT, "ops", Right.PLAN, by="idn_admin")
    draft = (await call(http, base, key, "open_plan", said="x"))["draft"]
    read = await call(http, base, key, "commission_plan", draft=draft)
    await given.identities.withdraw(TENANT, "ops", Right.PLAN, by="idn_admin")
    assert "confirm_act" not in await tools(http, base, key)
    late = await call(http, base, key, "confirm_act", act=read["act"], confirmed=True)
    assert late["error"] and "agent.plan" in late["refused"]
    assert ("agent.confirm_act", "refused", "idn_ada") in await entries(given)
