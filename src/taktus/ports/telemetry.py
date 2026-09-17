"""Telemetry: spans around units of work, emitted as OpenTelemetry signals by the adapter.

Every control-plane event is emitted from day one (docs/architecture/control-plane.md §8). A
span carries attributes — plain names and values — and records whether the work inside it
failed. Nothing collected here is about a person and nothing is a secret: attributes name
runs, steps, methods, adapters and measured quantities. `tests/adapters/telemetry` holds the
engine to that the way `tests/composition` holds the log.

The trace identifier is what joins a ledger entry, a log line and a trace: every entry the
engine records carries the identifier of the trace it was recorded in (`LedgerRefs.trace_id`),
and every log line written inside a span carries the same. `current_trace_id()` is how the
engine learns it; the no-op adapter has none.
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
        """A span that opens on entry and closes on exit, nested in the span that is open in
        the calling context. An exception inside it marks it failed and propagates."""
        ...

    def current_trace_id(self) -> str | None:
        """The identifier of the trace the innermost open span belongs to — 32 lowercase hex
        characters — or None when no span is open or the adapter keeps none."""
        ...
