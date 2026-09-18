"""The action half of the connector port over MCP.

One call, one session: the adapter opens the MCP client, calls the operation's tool with the
contract's `Arguments` — the call context and the operation's input — and reads the structured
content back as a `Result`, or as an `Error` when the tool answered `isError`. The declaration
is the resource `taktus://connector/v1/capabilities`, read the same way.

What the adapter refuses to guess: a tool that answers with an error and no classified error
body is a `ConnectorError`, not a failure with a made-up cause — the contract says every error
is classified (C-06), and a connector that does not classify has broken it. Nothing of a
credential travels here: the context names credentials, the connector's runtime holds the
values.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from mcp import Client
from pydantic import ValidationError

from taktus.ports.connector import (
    ActionConnector,
    Arguments,
    CallContext,
    CallFailed,
    Capabilities,
    ConnectorError,
    Error,
    Result,
)

CAPABILITIES_URI = "taktus://connector/v1/capabilities"


class McpActionConnector(ActionConnector):
    def __init__(self, endpoint: Any, *, timeout: float = 60.0) -> None:
        """`endpoint` is what the MCP client accepts: the URL of a connector that runs as a
        service (`http://connector:9100/mcp`), or an in-process server, for a test."""
        self._endpoint = endpoint
        self._timeout = timeout

    @property
    def endpoint(self) -> str:
        return self._endpoint if isinstance(self._endpoint, str) else "in-process"

    async def capabilities(self) -> Capabilities:
        try:
            async with Client(self._endpoint, read_timeout_seconds=self._timeout) as client:
                resource = await client.read_resource(CAPABILITIES_URI)
        except Exception as error:
            raise ConnectorError(
                f"the connector at {self.endpoint} did not serve its declaration: "
                f"{type(error).__name__}"
            ) from error
        text = getattr(resource.contents[0], "text", None) if resource.contents else None
        if not isinstance(text, str):
            raise ConnectorError(f"the connector at {self.endpoint} served an empty declaration")
        try:
            return Capabilities.model_validate(json.loads(text))
        except (ValueError, ValidationError) as error:
            raise ConnectorError(
                f"the connector at {self.endpoint} served a declaration that does not validate: "
                f"{_first(error)}"
            ) from error

    async def call(self, operation: str, context: CallContext, input: Mapping[str, Any]) -> Result:
        arguments = Arguments(context=context, input=dict(input)).document()
        try:
            async with Client(self._endpoint, read_timeout_seconds=self._timeout) as client:
                answer = await client.call_tool(operation, arguments)
        except Exception as error:
            raise ConnectorError(
                f"the connector at {self.endpoint} did not answer {operation}: "
                f"{type(error).__name__}"
            ) from error
        content = answer.structured_content
        if answer.is_error:
            # An error without a classified body is the connector's fault, not a failure of
            # the step with a made-up cause (C-06).
            try:
                classified = Error.model_validate(content)
            except ValidationError as invalid:
                raise ConnectorError(
                    f"the connector at {self.endpoint} answered {operation} with an error that is "
                    f"not classified: {_first(invalid)}"
                ) from invalid
            raise CallFailed(operation, classified)
        if not isinstance(content, dict):
            raise ConnectorError(
                f"the connector at {self.endpoint} answered {operation} without structured content"
            )
        try:
            return Result.model_validate(content)
        except ValidationError as invalid:
            raise ConnectorError(
                f"the connector at {self.endpoint} answered {operation} with a result that does "
                f"not validate: {_first(invalid)}"
            ) from invalid


def _first(error: Exception) -> str:
    if isinstance(error, ValidationError):
        first = error.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        return f"{where}: {first['msg']}" if where else str(first["msg"])
    return str(error)
