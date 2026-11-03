"""The vendor's MCP server, reached as a client (ADR-0117).

The connector does not run the vendor's server. It reaches it where the operator says it
answers: an MCP URL over streamable HTTP, or, in a test, a server object in the same process.
The requesting identity's credential travels as a bearer token on every request of one call
and is kept nowhere.

What the vendor says about a tool is read from its listing: its name, its description, and
two of the hints MCP offers — whether it only reads, and whether it may destroy. They are the
vendor's own claims. The connector believes a hint only where it narrows what may happen.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from mcp_types import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    CallToolResult,
    TextContent,
    Tool,
)

MAX_PAGES = 20
"""The most pages of a tool listing read; a server that pages further is refused."""


@dataclass(frozen=True)
class VendorTool:
    """One tool as the vendor's server lists it."""

    name: str
    description: str | None
    read_only: bool | None
    """`readOnlyHint`: True when the vendor says the tool only reads; None when it says nothing."""
    destructive: bool | None
    """`destructiveHint`: True when the vendor says the tool may destroy."""

    @property
    def marked_as_reading(self) -> bool:
        """The vendor says the tool only reads, and does not say it may destroy."""
        return self.read_only is True and self.destructive is not True

    @property
    def marked_as_acting(self) -> bool:
        """The vendor says the tool does more than read: it denies reading only, or says it may
        destroy. A manifest that calls such a tool a read contradicts its vendor."""
        return self.read_only is False or self.destructive is True

    @classmethod
    def of(cls, tool: Tool) -> VendorTool:
        hints = tool.annotations
        return cls(
            name=tool.name,
            description=tool.description,
            read_only=None if hints is None else hints.read_only_hint,
            destructive=None if hints is None else hints.destructive_hint,
        )


@dataclass(frozen=True)
class Answer:
    """What one call of a vendor's tool came to."""

    is_error: bool
    structured: Any
    text: str


@dataclass
class Exchange:
    """The HTTP statuses one session was answered with. The MCP client reports a refused
    request as a protocol error without its status, so the statuses are seen where they
    arrive."""

    statuses: list[int] = field(default_factory=list)

    async def saw(self, response: httpx2.Response) -> None:
        self.statuses.append(response.status_code)

    @property
    def refused(self) -> int | None:
        """401 or 403, where the vendor's server answered one."""
        return next((s for s in self.statuses if s in (401, 403)), None)


class Upstream:
    """Where the vendor's server answers, and how long one request may take."""

    def __init__(self, endpoint: Any, *, timeout: float) -> None:
        """`endpoint`: the MCP URL of the vendor's server, or a server object in a test."""
        self._endpoint = endpoint
        self._timeout = timeout

    @property
    def where(self) -> str:
        return self._endpoint if isinstance(self._endpoint, str) else "in-process"

    @asynccontextmanager
    async def session(
        self, token: str | None, exchange: Exchange | None = None
    ) -> AsyncIterator[Session]:
        """One session with the vendor's server; `token` goes as a bearer token, when given.
        `exchange` collects the statuses the server answered with."""
        if not isinstance(self._endpoint, str):
            async with Client(self._endpoint, read_timeout_seconds=self._timeout) as client:
                yield Session(client)
            return
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        hooks = {"response": [(exchange or Exchange()).saw]}
        async with (
            httpx2.AsyncClient(
                headers=headers, timeout=httpx2.Timeout(self._timeout), event_hooks=hooks
            ) as http,
            Client(
                streamable_http_client(self._endpoint, http_client=http),
                read_timeout_seconds=self._timeout,
            ) as client,
        ):
            yield Session(client)


class Session:
    def __init__(self, client: Client) -> None:
        self._client = client

    async def tools(self) -> list[VendorTool]:
        found: list[VendorTool] = []
        cursor: str | None = None
        for _ in range(MAX_PAGES):
            listed = await self._client.list_tools(cursor=cursor, cache_mode="bypass")
            found.extend(VendorTool.of(tool) for tool in listed.tools)
            cursor = listed.next_cursor
            if not cursor:
                return found
        raise ValueError(f"the tool listing runs past {MAX_PAGES} pages")

    async def call(self, tool: str, arguments: dict[str, Any]) -> Answer:
        result: CallToolResult = await self._client.call_tool(tool, arguments)
        texts = [c.text for c in result.content if isinstance(c, TextContent)]
        return Answer(bool(result.is_error), result.structured_content, "\n".join(texts))


def causes(error: BaseException) -> list[BaseException]:
    """The error, its causes, its contexts and the members of every group among them."""
    seen: set[int] = set()
    found: list[BaseException] = []
    pending: list[BaseException] = [error]
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        found.append(current)
        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions)
        for linked in (current.__cause__, current.__context__):
            if linked is not None:
                pending.append(linked)
    return found


REFUSALS = frozenset({INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS})
"""The protocol errors that say the server refused the request itself, before acting."""


def refusal(error: BaseException) -> MCPError | None:
    """The protocol error with which the vendor's server refused the request, where there is
    one: nothing was done. Any other protocol error says nothing of what was done."""
    for current in causes(error):
        if isinstance(current, MCPError) and current.error.code in REFUSALS:
            return current
    return None
