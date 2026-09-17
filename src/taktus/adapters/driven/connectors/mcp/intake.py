"""The intake half of the connector port over MCP.

One call, one session: the adapter opens the MCP client, calls the `intake` tool with the
delivery as the contract's `IntakeArguments`, reads the structured content as an
`IntakeResult`, and closes. A connector that cannot be reached, answers with an error, or
answers with a shape the contract does not allow is a `ConnectorError` naming the endpoint —
the raw body of the delivery is never part of the message.
"""

from __future__ import annotations

from typing import Any

from mcp import Client
from pydantic import ValidationError

from taktus.ports.connector import ConnectorError, Delivery, IntakeConnector, IntakeResult


class McpIntakeConnector(IntakeConnector):
    def __init__(self, endpoint: Any, *, timeout: float = 30.0) -> None:
        """`endpoint` is what the MCP client accepts: the URL of a connector that runs as a
        service (`http://connector:9100/mcp`), or an in-process server, for a test."""
        self._endpoint = endpoint
        self._timeout = timeout

    @property
    def endpoint(self) -> str:
        return self._endpoint if isinstance(self._endpoint, str) else "in-process"

    async def intake(self, delivery: Delivery) -> IntakeResult:
        arguments = {
            "headers": dict(delivery.headers),
            "body": delivery.body,
            "received_at": delivery.document()["received_at"],
        }
        try:
            async with Client(self._endpoint, read_timeout_seconds=self._timeout) as client:
                result = await client.call_tool("intake", arguments)
        except Exception as error:
            raise ConnectorError(
                f"the connector at {self.endpoint} did not answer intake: {type(error).__name__}"
            ) from error
        if result.is_error:
            raise ConnectorError(f"the connector at {self.endpoint} answered intake with an error")
        content = result.structured_content
        if not isinstance(content, dict):
            raise ConnectorError(
                f"the connector at {self.endpoint} answered intake without structured content"
            )
        try:
            return IntakeResult.model_validate(content)
        except ValidationError as error:
            raise ConnectorError(
                f"the connector at {self.endpoint} answered intake with a result that does not "
                f"validate: {error.errors()[0].get('msg', 'invalid')}"
            ) from error
