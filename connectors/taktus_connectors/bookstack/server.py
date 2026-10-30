"""The MCP server of the wiki connector: the declaration as a resource, one tool per operation,
and `GET /health`. It has no intake: a wiki sends Taktus nothing.

Every tool does the same four things: find the requesting identity's credential by the name the
context carries — and refuse when there is none, because the connector has no credential of its
own to fall back on — run the operation against the wiki, wrap what came back in the contract's
Result or Error envelope, and log one line that names the operation and the outcome and never a
value.

A credential is read at the moment of the call, **from a file and never from the environment**.
A reference `injected_as: file` is read from the path it names. A reference `injected_as: env`
is read from the file that `TAKTUS_CREDENTIAL_<NAME>_FILE` names — the one pattern every secret
of this repository follows (`CREDENTIALS.md`). A variable holding the value itself is not read:
a process listing shows variables.

The faults of `faults.py` are applied here, around that behaviour, and nowhere else.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent
from starlette.requests import Request
from starlette.responses import JSONResponse

from taktus_connectors.bookstack import declaration, operations
from taktus_connectors.bookstack.api import Api, TargetError
from taktus_connectors.bookstack.faults import validate

type Json = dict[str, Any]

CAPABILITIES_URI = "taktus://connector/v1/capabilities"
META_KEY = "taktus.eu/connector/v1"


@dataclass(frozen=True)
class Config:
    target: str
    """The wiki's base address; its interface for programs is under `/api`."""
    host: str = "127.0.0.1"
    port: int = 9102
    path: str = "/mcp"
    timeout: float = 30.0  # seconds to wait for the wiki's answer
    fault: str | None = None  # one of faults.FAULTS, for the meta-test only


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def log(message: str) -> None:
    sys.stderr.write(f"{now()} knowledge-connector {message}\n")
    sys.stderr.flush()


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def secret_named(name: str) -> str | None:
    """The value under a credential's name, from the file `TAKTUS_CREDENTIAL_<NAME>_FILE`
    names. Read now, kept nowhere; None without the variable or the file."""
    path = os.environ.get(f"TAKTUS_CREDENTIAL_{name.upper()}_FILE")
    return _read(path) if path else None


def credential_value(context: Json) -> str | None:
    """The first referenced credential whose value the runtime made available, or None."""
    for reference in context.get("credentials") or []:
        if not isinstance(reference, dict):
            continue
        value: str | None = None
        if reference.get("injected_as") == "env":
            value = secret_named(str(reference.get("name", "")))
        elif reference.get("injected_as") == "file" and reference.get("path"):
            value = _read(str(reference["path"]))
        if value:
            return value
    return None


def envelope(body: Json, *, is_error: bool = False) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(body))],
        structured_content=body,
        is_error=is_error,
    )


class Connector:
    """The behaviour behind the tools, separated from their registration so that it can be
    called in-process by tests."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.faults = validate(config.fault)

    def declaration(self) -> Json:
        capabilities = declaration.capabilities()
        if "C-01" in self.faults:
            capabilities["operations"] = [
                op for op in capabilities["operations"] if op["name"] != declaration.READ
            ]
        return capabilities

    async def call(self, name: str, context: Json, input: Json) -> CallToolResult:
        step = str(context.get("step_id", "?"))
        key = context.get("idempotency_key")
        if not isinstance(key, str) or not key:
            error = TargetError("invalid", "none", False, "the context carries no idempotency_key")
            log(f"{name} step={step}: invalid context")
            return self._error(error, 0)
        if "C-05" in self.faults:
            key = "fault-" + secrets.token_hex(12)
        token = credential_value(context)
        if token is None and "C-03" in self.faults:
            token = secret_named(declaration.ACTIONS_CREDENTIAL)
        if token is None:
            error = TargetError(
                "unauthenticated",
                "none",
                False,
                "no credential of the requesting identity was referenced, or no file holds one "
                "under the referenced name; the connector has none of its own",
            )
            log(f"{name} step={step}: unauthenticated")
            return self._error(error, 0)
        api = Api(self.config.target, token, timeout=self.config.timeout)
        try:
            outcome = await operations.OPERATIONS[name](api, input, key)
        except TargetError as error:
            log(f"{name} step={step}: {error.cause} after {api.requests} request(s)")
            return self._error(error, api.requests)
        finally:
            await api.close()
        result: Json = {
            "output": outcome.output,
            "effect": outcome.effect,
            "consumption": {"quota_units": api.requests},
        }
        replayed = " (replayed)" if outcome.effect.get("replayed") else ""
        log(f"{name} step={step}: {outcome.effect['kind']}{replayed}, {api.requests} request(s)")
        self._break_result(result, token)
        return envelope(result)

    def _error(self, error: TargetError, requests: int) -> CallToolResult:
        if "C-06" in self.faults:
            return CallToolResult(
                content=[TextContent(type="text", text=error.detail)], is_error=True
            )
        return envelope(error.envelope(requests), is_error=True)

    def _break_result(self, result: Json, token: str) -> None:
        if "C-02" in self.faults and result["effect"]["kind"] != "read":
            result["effect"] = {"kind": "read"}
        if "C-04-result" in self.faults:
            result["output"]["token"] = token
        if "C-04-log" in self.faults:
            log(f"using token {token}")
        if "C-09" in self.faults:
            del result["consumption"]


def build_server(config: Config) -> MCPServer[None]:
    connector = Connector(config)
    server: MCPServer[None] = MCPServer(
        name="taktus-knowledge-connector",
        version=declaration.VERSION,
        instructions="A Taktus connector (contracts/connector/v1). Every tool takes "
        "{context, input}; the declaration is the resource " + CAPABILITIES_URI + ".",
    )

    @server.resource(CAPABILITIES_URI, mime_type="application/json", name="capabilities")
    def capabilities() -> str:
        return json.dumps(connector.declaration())

    for op in declaration.OPERATIONS:
        server.add_tool(
            _tool_for(connector, str(op["name"])),
            name=str(op["name"]),
            description=str(op["summary"]),
            meta={META_KEY: dict(op)},
        )

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ready"})

    server.custom_route("/health", methods=["GET"])(health)
    return server


def _tool_for(connector: Connector, name: str) -> Any:
    async def tool(context: dict[str, Any], input: dict[str, Any]) -> CallToolResult:
        return await connector.call(name, context, input)

    tool.__name__ = name.replace(".", "_")
    return tool
