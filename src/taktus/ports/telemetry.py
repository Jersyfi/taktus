"""Telemetry: spans around units of work, emitted as OpenTelemetry signals by the adapter.

Every control-plane event is emitted from day one (docs/architecture/control-plane.md §8), even
while nothing collects it; the default adapter is a no-op. A span carries attributes — plain
names and values — and records whether the work inside it failed. Nothing collected here is
about a person: attributes name runs, steps, methods and adapters.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from typing import Protocol

type AttributeValue = str | int | float | bool
type Attributes = Mapping[str, AttributeValue]


class Span(Protocol):
    def set_attribute(self, name: str, value: AttributeValue) -> None: ...

    def record_failure(self, description: str) -> None:
        """Mark the span as failed. The description is a token or a short sentence, never
        content of the work."""
        ...


class Telemetry(Protocol):
    def span(
        self, name: str, attributes: Attributes | None = None
    ) -> AbstractAsyncContextManager[Span]:
        """A span that opens on entry and closes on exit. An exception inside it marks it failed
        and propagates."""
        ...
