"""The MCP server of the reference connector: the declaration as a resource, one tool per
operation, the intake tool, and `GET /health`.

Every tool does the same four things: find the requesting identity's credential by the name the
context carries — and refuse when there is none, because the connector has no credential of its
own — run the operation against the service, wrap what came back in the contract's Result or
Error envelope, and log one line that names the operation and the outcome and never a value.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent
from starlette.requests import Request
from starlette.responses import JSONResponse

from taktus.adapters.driven.connectors.github import declaration, operations
from taktus.adapters.driven.connectors.github.api import Api, TargetError

type Json = dict[str, Any]

CAPABILITIES_URI = "taktus://connector/v1/capabilities"
META_KEY = "taktus.eu/connector/v1"


@dataclass(frozen=True)
class Config:
    target: str
    repository: str
    host: str = "127.0.0.1"
    port: int = 9100
    path: str = "/mcp"
    timeout: float = 30.0  # seconds to wait for the service's answer


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def log(message: str) -> None:
    sys.stderr.write(f"{now()} repository-connector {message}\n")
    sys.stderr.flush()


def credential_value(context: Json) -> str | None:
    """The first referenced credential whose value the runtime made available, or None. Read at
    the moment of the call, used for the call, kept nowhere."""
    for reference in context.get("credentials") or []:
        if not isinstance(reference, dict):
            continue
        name = str(reference.get("name", ""))
        value: str | None = None
        if reference.get("injected_as") == "env":
            value = os.environ.get(name)
        elif reference.get("injected_as") == "file" and reference.get("path"):
            try:
                value = Path(str(reference["path"])).read_text(encoding="utf-8").strip()
            except OSError:
                value = None
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

    async def call(self, name: str, context: Json, input: Json) -> CallToolResult:
        step = str(context.get("step_id", "?"))
        key = context.get("idempotency_key")
        if not isinstance(key, str) or not key:
            error = TargetError("invalid", "none", False, "the context carries no idempotency_key")
            log(f"{name} step={step}: invalid context")
            return envelope(error.envelope(0), is_error=True)
        token = credential_value(context)
        if token is None:
            error = TargetError(
                "unauthenticated",
                "none",
                False,
                "no credential of the requesting identity was referenced, or none is available "
                "under the referenced name; the connector has none of its own",
            )
            log(f"{name} step={step}: unauthenticated")
            return envelope(error.envelope(0), is_error=True)
        api = Api(self.config.target, self.config.repository, token, timeout=self.config.timeout)
        try:
            outcome = await operations.OPERATIONS[name](api, input, key)
        except TargetError as error:
            log(f"{name} step={step}: {error.cause} after {api.requests} request(s)")
            return envelope(error.envelope(api.requests), is_error=True)
        finally:
            await api.close()
        result: Json = {
            "output": outcome.output,
            "effect": outcome.effect,
            "consumption": {"quota_units": api.requests},
        }
        replayed = " (replayed)" if outcome.effect.get("replayed") else ""
        log(f"{name} step={step}: {outcome.effect['kind']}{replayed}, {api.requests} request(s)")
        return envelope(result)


def build_server(config: Config) -> MCPServer[None]:
    connector = Connector(config)
    server: MCPServer[None] = MCPServer(
        name="taktus-repository-connector",
        version=declaration.VERSION,
        instructions="A Taktus connector (contracts/connector/v1). Every tool takes "
        "{context, input}; the declaration is the resource " + CAPABILITIES_URI + ".",
    )

    @server.resource(CAPABILITIES_URI, mime_type="application/json", name="capabilities")
    def capabilities() -> str:
        return json.dumps(declaration.capabilities())

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
