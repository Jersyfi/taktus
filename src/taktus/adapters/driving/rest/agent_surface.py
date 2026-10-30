"""The MCP surface: a person's own agent reaches Taktus over the Model Context Protocol (ADR-0131,
UC-1.11).

The `api` role serves it at `<prefix>/mcp`, over MCP's streamable HTTP transport, stateless and
answered as JSON. Every HTTP request stands alone:

1. its `Authorization: Bearer` must carry an **agent key**, which the identity component proves
   (ADR-0131 §2). An account key, the web app's session and no credential are answered `401`
   before any message is read;
2. the rights the person's roles hold are read for this request (§3);
3. a server is built for this person and these rights, and answers the request's message.

A client lists the read tools, and each tool that acts whose right the person holds. A tool
called without its right is refused, naming the right, and changes nothing. Every read asks
the visibility predicate the HTTP surface asks; a run the reader may not see is answered as one
that does not exist. Every call is recorded in the ledger as `agent.<tool>`, with the person as
actor and its outcome: `served`, `refused` or `failed` (§6).

The tools call the application services the HTTP surface calls. Answering a decision request
never takes effect alone: the reading comes back, and only `confirm_decision` makes it count
(ADR-0008). The take-over tools are those of ADR-0128; `steer_step` sends a running step a
message (ADR-0156). The surface offers no resources and no prompts, and passes nothing on to
another MCP server.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

import mcp_types as types
import structlog
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.types import Receive, Scope, Send

from taktus.adapters.driving.rest.problems import problem
from taktus.adapters.driving.rest.views import decision_view
from taktus.adapters.driving.rest.wiring import RestServices, StartRefused
from taktus.components.decision.application.query import Addressed
from taktus.components.decision.application.service import (
    AnswerRequest,
    ConfirmRequest,
    DecisionError,
)
from taktus.components.identity.domain.model import Right
from taktus.components.reporting.domain.model import Reader, RunRef
from taktus.components.reporting.domain.service import visibility
from taktus.components.run.application.service import HandBack, SteerStep, TakeOver
from taktus.components.run.domain.model import RunError
from taktus.ports.identity import Resolution

log = structlog.get_logger("taktusd")

type Json = dict[str, Any]

SERVED = "served"
REFUSED = "refused"
FAILED = "failed"
LIST_DEFAULT = 20
LIST_MAXIMUM = 100
NEEDS_KEY = "an agent key is needed: Authorization: Bearer <agent key> (ADR-0131 §2)"


class Refused(Exception):
    """The call is declined; the message says why, and nothing changed."""


@dataclass(frozen=True)
class Call:
    """One call of a tool, by one person holding some rights."""

    services: RestServices
    who: Resolution
    arguments: Mapping[str, Any]

    def text(self, name: str) -> str:
        value = self.arguments.get(name)
        if not isinstance(value, str) or not value:
            raise Refused(f"`{name}` is needed, as a text")
        return value

    async def visible_run(self, run_id: str) -> Any:
        reader = Reader(tenant=self.who.tenant, identity=self.who.identity, roles=self.who.roles)
        async with self.services.work.transaction(self.who.tenant):
            run = await self.services.runs.get(self.who.tenant, run_id)
        if run is None or not visibility.may_see(
            reader, RunRef(id=run.id, tenant=run.tenant, process_version=run.process_version)
        ):
            raise Refused(f"no run {run_id!r} that you may see")
        return run


type Act = Callable[[Call], Awaitable[Json]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: Json
    act: Act
    right: Right | None = None
    """None: the tool reads, and needs no right beyond the agent key."""

    def listed(self) -> types.Tool:
        return types.Tool(
            name=self.name,
            description=self.description
            + ("" if self.right is None else f" Needs the right `{self.right.value}`."),
            input_schema=self.schema,
            annotations=types.ToolAnnotations(
                read_only_hint=self.right is None, open_world_hint=False
            ),
        )


def _object(properties: Json, required: tuple[str, ...] = ()) -> Json:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


TEXT: Json = {"type": "string", "minLength": 1}


# --- the acts --------------------------------------------------------------------------------


async def _list_processes(call: Call) -> Json:
    return {"processes": list(await call.services.agent.processes(call.who))}


async def _start_process(call: Call) -> Json:
    inputs = call.arguments.get("inputs") or {}
    if not isinstance(inputs, Mapping):
        raise Refused("`inputs` is an object of the process's inputs by name")
    try:
        run = await call.services.agent.start(call.who, call.text("process"), inputs)
    except StartRefused as error:
        raise Refused(str(error)) from error
    return {"run_id": run.id, "process_version": run.process_version, "state": run.state}


async def _list_runs(call: Call) -> Json:
    limit = call.arguments.get("limit", LIST_DEFAULT)
    if not isinstance(limit, int) or not 1 <= limit <= LIST_MAXIMUM:
        raise Refused(f"`limit` is a whole number from 1 to {LIST_MAXIMUM}")
    who = call.who
    reader = Reader(tenant=who.tenant, identity=who.identity, roles=who.roles)
    async with call.services.work.transaction(who.tenant):
        read = await call.services.runs.newest(who.tenant, limit=limit)
    return {
        "runs": [
            {
                "id": run.id,
                "process_version": run.process_version,
                "state": run.state,
                "created_at": run.created_at.isoformat(),
                "updated_at": run.updated_at.isoformat(),
            }
            for run in read
            if visibility.may_see(
                reader, RunRef(id=run.id, tenant=run.tenant, process_version=run.process_version)
            )
        ]
    }


async def _get_run(call: Call) -> Json:
    run = await call.visible_run(call.text("run_id"))
    document: Json = run.document()
    return document


async def _list_decisions(call: Call) -> Json:
    waiting = await call.services.decision_queries.addressed_to(call.who.tenant, call.who.identity)
    return {"requests": [decision_view(a, call.who.identity) for a in waiting]}


async def _get_decision(call: Call) -> Json:
    request_id = call.text("request_id")
    found = await call.services.decision_queries.one(call.who.tenant, request_id)
    if found is None or found.request.decider not in call.who.roles:
        raise Refused(f"no decision request {request_id!r} addressed to you")
    return decision_view(found, call.who.identity)


async def _answer_decision(call: Call) -> Json:
    option = call.arguments.get("option")
    text = call.arguments.get("text")
    if (option is None) == (text is None):
        raise Refused("give either `option` or `text`")
    try:
        answered = await call.services.answer_decision.execute(
            AnswerRequest(
                tenant=call.who.tenant,
                request_id=call.text("request_id"),
                identity=call.who.identity,
                text=text,
                option=option,
            )
        )
    except (DecisionError, ValueError) as error:
        raise Refused(str(error)) from error
    return {
        "message": answered.message,
        "request": decision_view(Addressed(answered.request, overdue=False), call.who.identity),
        "takes_effect": "only once confirm_decision confirms this reading",
    }


async def _confirm_decision(call: Call) -> Json:
    confirmed = call.arguments.get("confirmed")
    if not isinstance(confirmed, bool):
        raise Refused("`confirmed` is true or false")
    who = call.who
    try:
        done = await call.services.confirm_decision.execute(
            ConfirmRequest(
                tenant=who.tenant,
                request_id=call.text("request_id"),
                identity=who.identity,
                confirmed=confirmed,
            )
        )
    except DecisionError as error:
        raise Refused(str(error)) from error
    if done.entry is not None:
        await call.services.decided(
            who.tenant, done.entry.run_id, who.identity, done.entry.request_id
        )
    return {
        "applied": done.entry is not None,
        "entry": None if done.entry is None else done.entry.id,
        "request": decision_view(Addressed(done.request, overdue=False), who.identity),
    }


async def _take_over_step(call: Call) -> Json:
    run_id, step_id = call.text("run_id"), call.text("step_id")
    await call.visible_run(run_id)
    try:
        takeover = await call.services.takeovers.take_over(
            TakeOver(
                run_id=run_id, step_id=step_id, actor=call.who.identity, tenant=call.who.tenant
            )
        )
    except RunError as error:
        raise Refused(str(error)) from error
    return {"takeover": takeover, "run_id": run_id, "step_id": step_id, "state": "asked"}


async def _steer_step(call: Call) -> Json:
    run_id, step_id, text = call.text("run_id"), call.text("step_id"), call.text("text")
    await call.visible_run(run_id)
    try:
        message = await call.services.takeovers.steer(
            SteerStep(
                run_id=run_id,
                step_id=step_id,
                text=text,
                actor=call.who.identity,
                tenant=call.who.tenant,
            )
        )
    except RunError as error:
        raise Refused(str(error)) from error
    return {"message": message, "run_id": run_id, "step_id": step_id, "state": "asked"}


async def _show_takeover(call: Call) -> Json:
    run_id, takeover = call.text("run_id"), call.text("takeover_id")
    await call.visible_run(run_id)
    try:
        state = await call.services.takeovers.takeover_state(call.who.tenant, run_id, takeover)
    except RunError as error:
        raise Refused(str(error)) from error
    return {"takeover": takeover, "state": state}


async def _hand_back(call: Call) -> Json:
    run_id, takeover = call.text("run_id"), call.text("takeover_id")
    if "result" not in call.arguments:
        raise Refused("`result` is needed: the step's result, as one JSON value")
    await call.visible_run(run_id)
    try:
        run = await call.services.takeovers.hand_back(
            HandBack(
                run_id=run_id,
                takeover=takeover,
                result=call.arguments["result"],
                actor=call.who.identity,
                tenant=call.who.tenant,
            )
        )
    except RunError as error:
        raise Refused(str(error)) from error
    return {"run_id": run.id, "state": run.state}


TOOLS: tuple[Tool, ...] = (
    Tool(
        "list_processes",
        "The processes you may start: each with its active version and the inputs it takes.",
        _object({}),
        _list_processes,
    ),
    Tool(
        "start_process",
        "Start a process's active version with its inputs. The run acts as you; a runner "
        "executes it, and get_run shows where it got to.",
        _object({"process": TEXT, "inputs": {"type": "object"}}, ("process",)),
        _start_process,
        Right.START,
    ),
    Tool(
        "list_runs",
        "The runs you may see, newest first.",
        _object({"limit": {"type": "integer", "minimum": 1, "maximum": LIST_MAXIMUM}}),
        _list_runs,
    ),
    Tool(
        "get_run",
        "One run you may see, with its steps and their state.",
        _object({"run_id": TEXT}, ("run_id",)),
        _get_run,
    ),
    Tool(
        "list_decisions",
        "The decision requests addressed to you, not yet applied, the oldest due first.",
        _object({}),
        _list_decisions,
    ),
    Tool(
        "get_decision",
        "One decision request addressed to you, with its options.",
        _object({"request_id": TEXT}, ("request_id",)),
        _get_decision,
    ),
    Tool(
        "answer_decision",
        "Answer a decision request addressed to you: one option by its letter, or free text. "
        "Nothing takes effect: the answer comes back as it was read, and only "
        "confirm_decision makes it count.",
        _object(
            {"request_id": TEXT, "option": {"type": "string", "pattern": "^[A-Z]$"}, "text": TEXT},
            ("request_id",),
        ),
        _answer_decision,
        Right.ANSWER,
    ),
    Tool(
        "confirm_decision",
        "Confirm, or reject, how your answer was read. Confirmed, it takes effect; rejected, "
        "nothing does and the request is open again.",
        _object(
            {"request_id": TEXT, "confirmed": {"type": "boolean"}}, ("request_id", "confirmed")
        ),
        _confirm_decision,
        Right.ANSWER,
    ),
    Tool(
        "take_over_step",
        "Ask to take over a running worker step. Its worker stops at its next boundary and the "
        "run passes to you; show_takeover then shows the state the step reached.",
        _object({"run_id": TEXT, "step_id": TEXT}, ("run_id", "step_id")),
        _take_over_step,
        Right.TAKE_OVER,
    ),
    Tool(
        "steer_step",
        "Send a message to a running worker step. Its worker receives it at its next boundary, "
        "and the steps after it take it as an input; it never widens what the step may do.",
        _object(
            {"run_id": TEXT, "step_id": TEXT, "text": {"type": "string", "maxLength": 8000}},
            ("run_id", "step_id", "text"),
        ),
        _steer_step,
        Right.STEER,
    ),
    Tool(
        "show_takeover",
        "The state a step was taken over in: its goal, inputs, the worker's checkpoint and what "
        "it produced so far, and until when it is held.",
        _object({"run_id": TEXT, "takeover_id": TEXT}, ("run_id", "takeover_id")),
        _show_takeover,
    ),
    Tool(
        "hand_back",
        "Hand back the result of a step you took over, as one JSON value. It becomes the "
        "step's result, produced by you, and the run continues.",
        _object(
            {"run_id": TEXT, "takeover_id": TEXT, "result": {}},
            ("run_id", "takeover_id", "result"),
        ),
        _hand_back,
        Right.TAKE_OVER,
    ),
)
BY_NAME = {tool.name: tool for tool in TOOLS}


def _result(body: Json, *, error: bool = False) -> types.CallToolResult:
    return types.CallToolResult(
        content=[
            types.TextContent(type="text", text=json.dumps(body, ensure_ascii=False, default=str))
        ],
        structured_content=body,
        is_error=error,
    )


def _run_named(arguments: Mapping[str, Any], answer: Json | None) -> str | None:
    named = arguments.get("run_id")
    if isinstance(named, str) and named:
        return named
    started = None if answer is None else answer.get("run_id")
    return started if isinstance(started, str) else None


def server_for(services: RestServices, who: Resolution, rights: frozenset[Right]) -> Server[Any]:
    """The MCP server of one request: the tools `who` may use, served as `who`."""

    async def list_tools(
        ctx: ServerRequestContext[Any], params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[t.listed() for t in TOOLS if t.right is None or t.right in rights]
        )

    async def call_tool(
        ctx: ServerRequestContext[Any], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        arguments: Mapping[str, Any] = params.arguments or {}
        tool = BY_NAME.get(params.name)
        name = params.name if tool is not None else "unknown"
        answer: Json | None = None
        try:
            if tool is None:
                raise Refused(f"no tool {params.name!r}")
            if tool.right is not None and tool.right not in rights:
                raise Refused(
                    f"{tool.name} needs the right `{tool.right.value}`, which none of your "
                    "roles holds; an administrator grants it to a role"
                )
            answer = await tool.act(Call(services, who, arguments))
        except Refused as refused:
            outcome, result = REFUSED, _result({"refused": str(refused)}, error=True)
        except Exception as error:
            log.error("an MCP tool call failed", tool=name, error=type(error).__name__)
            outcome, result = FAILED, _result({"failed": "the call failed"}, error=True)
        else:
            outcome, result = SERVED, _result(answer)
        await services.agent.called(who, name, outcome, arguments, _run_named(arguments, answer))
        return result

    return Server(
        "taktus",
        instructions="Taktus, an operating layer for a business. You act as the person whose "
        "agent key you hold, and only within the rights of their roles.",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


class AgentEndpoint:
    """The ASGI application at `<prefix>/mcp`: authenticates every request by its agent key,
    then answers it with a server built for that person (ADR-0131 §1, §2)."""

    def __init__(self, services: RestServices) -> None:
        self._services = services

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        authorization = next(
            (v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"authorization"),
            "",
        )
        scheme, _, key = authorization.partition(" ")
        who = (
            await self._services.identities.authenticate_agent(key.strip())
            if scheme.lower() == "bearer"
            else None
        )
        if who is None:
            await problem(401, NEEDS_KEY)(scope, receive, send)
            return
        rights = await self._services.identities.rights(who)
        manager = StreamableHTTPSessionManager(
            app=server_for(self._services, who, rights), json_response=True, stateless=True
        )
        async with manager.run():
            await manager.handle_request(scope, receive, send)
