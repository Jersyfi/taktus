"""What the connectors over open standards share: the MCP server around their operations.

The mail, metrics and check connectors (ADR-0111) differ in what they reach and agree in how
they serve the contract (`contracts/connector/v1`). So does the vendor connector, which puts a
vendor's MCP server behind it (ADR-0117). This module holds the agreement: the
declaration as a resource, one tool per operation, the intake tool where there is an intake,
`GET /health`, and the faults the conformance suite is proven against. Each connector supplies
its declaration, its operations and, for the mail connector, its intake.

Every tool does the same four things. It finds the requesting identity's credential by the name
the context carries, and refuses when there is none, because the connector has no credential of
its own. It runs the operation. It wraps what came back in the contract's Result or Error
envelope. It logs one line that names the operation and the outcome and never a value.

A credential is read at the moment of the call, **from a file and never from the environment**.
A reference `injected_as: file` is read from the path it names. A reference `injected_as: env`
is read from the file that `TAKTUS_CREDENTIAL_<NAME>_FILE` names (`CREDENTIALS.md`). A variable
holding the value itself is not read: a process listing shows variables.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent
from starlette.requests import Request
from starlette.responses import JSONResponse

type Json = dict[str, Any]

CAPABILITIES_URI = "taktus://connector/v1/capabilities"
META_KEY = "taktus.eu/connector/v1"

COMMON_FAULTS: dict[str, str] = {
    "C-01": "the declaration omits its first operation, which is still served as a tool",
    "C-02": "a result claims an effect other than the one declared",
    "C-03": "a call without a credential is served with the actions credential anyway",
    "C-04-result": "the credential value is copied into every result's output",
    "C-04-log": "the credential value is written to the log",
    "C-06": "an error is returned as bare text without the Error envelope",
    "C-09": "results report no consumption",
}
"""The faults every connector here offers. `C-05` is offered only where an operation leaves
the system, and the intake faults only where there is an intake."""


@dataclass(eq=False)
class TargetError(Exception):
    """The target refused, failed or vanished. `cause`, `effect` and `retryable` are the
    contract's (`Connector.json#/$defs/Error`). Not frozen: an exception raised inside a
    session's `with` block gets its traceback set as it leaves the block."""

    cause: str
    effect: str
    retryable: bool
    detail: str

    def envelope(self, requests: int) -> Json:
        error: Json = {
            "class": "failure",
            "cause": self.cause,
            "effect": self.effect,
            "retryable": self.retryable,
            "detail": self.detail,
        }
        if requests:
            error["consumption"] = {"quota_units": requests}
        return error


def invalid(detail: str) -> TargetError:
    return TargetError("invalid", "none", False, detail)


def unavailable(detail: str) -> TargetError:
    return TargetError("unavailable", "none", True, detail)


@dataclass(frozen=True)
class Outcome:
    """What an operation produced: its own output and the contract's effect report."""

    output: Json
    effect: Json


@dataclass
class Call:
    """One call of one operation: the requesting identity's credential, the key, and the count
    of requests made to the target, which the result reports as its consumption."""

    token: str
    key: str
    requests: int = 0

    def count(self, n: int = 1) -> None:
        self.requests += n


type Operation = Callable[[Any, Call, Json], Awaitable[Outcome]]
"""An operation: the connector's configuration, the call, the input."""
type Intake = Callable[[Mapping[str, str], str, str, str | None], Json]
"""The intake: the headers, the raw body, the moment it arrived, the intake secret."""
type Signer = Callable[[str, str], dict[str, str]]
"""The headers that sign a body with a secret, as the intake expects them."""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def secret_named(name: str) -> str | None:
    """The value of the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names, read now, kept nowhere."""
    path = os.environ.get(f"TAKTUS_CREDENTIAL_{name.upper()}_FILE")
    return _read(path) if path else None


@dataclass
class Served:
    """One connector as this module serves it."""

    name: str
    """How its log lines and its MCP server are named: `mail-connector`."""
    declaration: Callable[[], Json]
    operations: Mapping[str, Operation]
    actions_credential: str
    config: Any
    fault: str | None = None
    faults: Mapping[str, str] = field(default_factory=lambda: dict(COMMON_FAULTS))
    intake: Intake | None = None
    intake_credential: str | None = None
    signer: Signer | None = None
    signature_header: str | None = None

    def __post_init__(self) -> None:
        if self.fault is not None and self.fault not in self.faults:
            raise ValueError(f"unknown fault {self.fault!r}; known: {', '.join(self.faults)}")

    def log(self, message: str) -> None:
        sys.stderr.write(f"{now()} {self.name} {message}\n")
        sys.stderr.flush()

    def _own_files(self) -> set[str]:
        if self.intake_credential is None:
            return set()
        path = os.environ.get(f"TAKTUS_CREDENTIAL_{self.intake_credential.upper()}_FILE")
        return {str(Path(path).resolve())} if path else set()

    def credential_value(self, context: Json) -> str | None:
        """The first referenced credential whose value the runtime made available, or None.
        A reference that names the intake secret, by name or by its file, is skipped: a caller
        could otherwise make the connector act with its own secret (issue #267)."""
        own = {self.intake_credential.upper()} if self.intake_credential else set()
        for reference in context.get("credentials") or []:
            if not isinstance(reference, dict):
                continue
            name = str(reference.get("name", "")).upper()
            path = reference.get("path")
            if name in own or (path and str(Path(str(path)).resolve()) in self._own_files()):
                continue
            value: str | None = None
            if reference.get("injected_as") == "env":
                value = secret_named(name)
            elif reference.get("injected_as") == "file" and path:
                value = _read(str(path))
            if value:
                return value
        return None

    def capabilities(self) -> Json:
        document = self.declaration()
        if self.fault == "C-01":
            document["operations"] = document["operations"][1:]
        return document

    async def call(self, name: str, context: Json, input: Json) -> CallToolResult:
        step = str(context.get("step_id", "?"))
        key = context.get("idempotency_key")
        if not isinstance(key, str) or not key:
            self.log(f"{name} step={step}: invalid context")
            return envelope(invalid("the context carries no idempotency_key").envelope(0), True)
        if self.fault == "C-05":
            key = "fault-" + secrets.token_hex(12)
        token = self.credential_value(context)
        if token is None and self.fault == "C-03":
            token = secret_named(self.actions_credential)
        if token is None:
            self.log(f"{name} step={step}: unauthenticated")
            refusal = TargetError(
                "unauthenticated",
                "none",
                False,
                "no credential of the requesting identity was referenced, or none is available "
                "under the referenced name; the connector has none of its own",
            )
            return envelope(refusal.envelope(0), True)
        call = Call(token=token, key=key)
        try:
            outcome = await self.operations[name](self.config, call, input)
        except TargetError as error:
            self.log(f"{name} step={step}: {error.cause} after {call.requests} request(s)")
            if self.fault == "C-06":
                return CallToolResult(
                    content=[TextContent(type="text", text=error.detail)], is_error=True
                )
            return envelope(error.envelope(call.requests), True)
        result: Json = {
            "output": outcome.output,
            "effect": outcome.effect,
            "consumption": {"quota_units": max(call.requests, 1)},
        }
        replayed = " (replayed)" if outcome.effect.get("replayed") else ""
        self.log(f"{name} step={step}: {outcome.effect['kind']}{replayed}, {call.requests} req")
        self._break(result, token)
        return envelope(result)

    def _break(self, result: Json, token: str) -> None:
        if self.fault == "C-02":
            result["effect"] = {"kind": "write" if result["effect"]["kind"] == "read" else "read"}
        if self.fault == "C-04-result":
            result["output"]["token"] = token
        if self.fault == "C-04-log":
            self.log(f"using token {token}")
        if self.fault == "C-09":
            del result["consumption"]

    async def receive(self, headers: Json, body: str, received_at: str) -> CallToolResult:
        """The intake tool. The secret is read at the moment of the delivery."""
        if self.intake is None or self.intake_credential is None:
            return envelope(invalid("this connector has no intake").envelope(0), True)
        secret = secret_named(self.intake_credential)
        given = {str(k).lower(): str(v) for k, v in headers.items()}
        header = self.signature_header or ""
        if (
            secret
            and self.signer is not None
            and (
                (self.fault == "C-08-unsigned" and header not in given)
                or (self.fault == "C-08-signature" and header in given)
            )
        ):
            given.update(self.signer(body, secret))
        result = self.intake(given, body, received_at, secret)
        if "accepted" in result and self.fault == "C-07":
            del result["accepted"]["reply_to"]
        if "accepted" in result:
            self.log(f"intake: accepted as {result['accepted']['event']}")
        else:
            self.log(f"intake: refused, {result['refused']['reason']}")
        return envelope(result)


def envelope(body: Json, is_error: bool = False) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(body))],
        structured_content=body,
        is_error=is_error,
    )


def build_server(served: Served) -> MCPServer[None]:
    """The MCP server of one connector: its declaration, its tools and its health."""
    server: MCPServer[None] = MCPServer(
        name=f"taktus-{served.name}",
        version=str(served.declaration().get("version", "1.0.0")),
        instructions="A Taktus connector (contracts/connector/v1). Every tool takes "
        "{context, input}; the declaration is the resource " + CAPABILITIES_URI + ".",
    )

    @server.resource(CAPABILITIES_URI, mime_type="application/json", name="capabilities")
    def capabilities() -> str:
        return json.dumps(served.capabilities())

    for op in served.declaration()["operations"]:
        server.add_tool(
            _tool_for(served, str(op["name"])),
            name=str(op["name"]),
            description=str(op["summary"]),
            meta={META_KEY: dict(op)},
        )

    if served.intake is not None:

        async def intake_tool(
            headers: dict[str, str], body: str, received_at: str
        ) -> CallToolResult:
            return await served.receive(headers, body, received_at)

        server.add_tool(
            intake_tool,
            name="intake",
            description="One delivery as it arrived: headers, the raw body, when. Verified, "
            "then normalised into an intake command, or refused.",
        )

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ready"})

    server.custom_route("/health", methods=["GET"])(health)
    return server


def _tool_for(served: Served, name: str) -> Any:
    async def tool(context: dict[str, Any], input: dict[str, Any]) -> CallToolResult:
        return await served.call(name, context, input)

    tool.__name__ = name.replace(".", "_")
    return tool


def arguments(description: str, port: int) -> argparse.ArgumentParser:
    """The arguments every connector here takes; each adds its own target."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=port)
    parser.add_argument("--path", default="/mcp", help="where MCP is served")
    parser.add_argument("--timeout", type=float, default=30.0, help="seconds to wait")
    parser.add_argument("--fault", help="violate exactly one check (--list-faults)")
    parser.add_argument(
        "--list-faults", action="store_true", help="print every fault with the check it breaks"
    )
    return parser


def serve(served: Served, args: argparse.Namespace) -> int:
    """Print the faults, or serve MCP over streamable HTTP until stopped."""
    if args.list_faults:
        for fault, what in served.faults.items():
            sys.stdout.write(f"{fault}\t{fault[:4]}\t{what}\n")
        return 0
    if served.fault:
        served.log(f"FAULT {served.fault}: {served.faults[served.fault]}")
    served.log(f"serving at http://{args.host}:{args.port}{args.path}")
    build_server(served).run(
        "streamable-http", host=args.host, port=args.port, streamable_http_path=args.path
    )
    return 0
