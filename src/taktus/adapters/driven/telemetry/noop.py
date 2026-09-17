from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from taktus.ports.telemetry import Attributes, AttributeValue, Span


class NoSpan:
    def set_attribute(self, name: str, value: AttributeValue) -> None:
        return None

    def record_failure(self, description: str) -> None:
        return None


class NoTelemetry:
    @asynccontextmanager
    async def span(self, name: str, attributes: Attributes | None = None) -> AsyncIterator[Span]:
        yield NoSpan()

    def current_trace_id(self) -> str | None:
        return None
