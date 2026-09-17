"""The MCP side of the connector suite: how it talks to a connector.

Nothing here knows what the checks mean. It reads the declaration, lists the tools and calls
them, and returns what came back — the structured content, whether the call was an error, the
raw text — so that the suite can judge it. A connector written with any MCP library sees exactly
what Taktus would send: `tools/call` with `{"context": …, "input": …}` and nothing else.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Self

from mcp import Client
from mcp_types import TextContent

type Json = dict[str, Any]


@dataclass
class Answer:
    """What one tool call returned."""

    tool: str
    is_error: bool
    structured: Any
    text: str
    transport_error: str | None = None

    @property
    def json(self) -> Json | None:
        return self.structured if isinstance(self.structured, dict) else None


@dataclass
class Declaration:
    """The capabilities resource as served: its text, its parsed form, its media type."""

    text: str
    mime_type: str | None
    json: Json | None
    problem: str | None = None


@dataclass
class ToolList:
    names: list[str] = field(default_factory=list)
    text: str = ""


class ConnectorClient:
    def __init__(self, endpoint: str, *, timeout: float) -> None:
        self.endpoint = endpoint
        self._client = Client(endpoint, read_timeout_seconds=timeout)

    async def __aenter__(self) -> Self:
        await self._client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.__aexit__(exc_type, exc, tb)

    async def declaration(self, uri: str) -> Declaration:
        try:
            result = await self._client.read_resource(uri)
        except Exception as error:
            return Declaration("", None, None, f"reading {uri} failed: {error!r}")
        if not result.contents:
            return Declaration("", None, None, f"{uri} has no contents")
        content = result.contents[0]
        text = getattr(content, "text", None)
        mime = getattr(content, "mime_type", None)
        if not isinstance(text, str):
            return Declaration("", mime, None, f"{uri} is not text")
        try:
            parsed = json.loads(text)
        except ValueError as error:
            return Declaration(text, mime, None, f"{uri} is not JSON: {error}")
        return Declaration(text, mime, parsed if isinstance(parsed, dict) else None)

    async def tools(self) -> ToolList:
        listed = await self._client.list_tools()
        names = [tool.name for tool in listed.tools]
        text = json.dumps([tool.model_dump(mode="json") for tool in listed.tools])
        return ToolList(names, text)

    async def call(self, tool: str, arguments: Json) -> Answer:
        try:
            result = await self._client.call_tool(tool, arguments)
        except Exception as error:
            return Answer(tool, True, None, "", transport_error=repr(error))
        texts = [c.text for c in result.content if isinstance(c, TextContent)]
        raw = json.dumps(result.structured_content) if result.structured_content else ""
        return Answer(
            tool, bool(result.is_error), result.structured_content, raw + "\n".join(texts)
        )
