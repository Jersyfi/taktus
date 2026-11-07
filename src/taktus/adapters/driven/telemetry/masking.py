"""Spans masked by the organisation's policy before they leave for an observability platform
(UC-5.8, ADR-0286).

The trace inside Taktus stays as it was. What leaves is a copy: every attribute whose name
matches a pattern of the policy is replaced whole, and every text value is searched for the
kinds of personal content the policy names, each occurrence replaced. The masking is a rule —
a pattern per kind — so that the same span is always masked the same way.

The kinds are `email` (an address), `iban` (an international bank account number) and `phone`
(a number written with a leading `+` and at least eight digits).
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Collection, Mapping, Sequence
from typing import Any

from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

MASK = "[masked]"
KINDS: Mapping[str, re.Pattern[str]] = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "iban": re.compile(r"\b[A-Z]{2}[0-9]{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b"),
    "phone": re.compile(r"\+[0-9][0-9 ()/.-]{6,}[0-9]"),
}
"""Each kind of personal content a policy may name, and the pattern that finds it."""


class MaskingPolicy:
    """Which attributes leave masked whole, and which kinds of content are masked wherever a
    text carries them."""

    def __init__(self, attributes: Collection[str] = (), kinds: Collection[str] = ()) -> None:
        unknown = sorted(set(kinds) - set(KINDS))
        if unknown:
            raise ValueError(f"no masking for {', '.join(unknown)}; known: {', '.join(KINDS)}")
        self._attributes = tuple(attributes)
        self._kinds = tuple(KINDS[kind] for kind in sorted(set(kinds)))

    def value(self, name: str, value: Any) -> Any:
        if any(fnmatch.fnmatchcase(name, pattern) for pattern in self._attributes):
            return MASK
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, Sequence) and not isinstance(value, str | bytes):
            return tuple(self.text(v) if isinstance(v, str) else v for v in value)
        return value

    def text(self, text: str) -> str:
        for pattern in self._kinds:
            text = pattern.sub(MASK, text)
        return text

    def attributes(self, attributes: Mapping[str, Any] | None) -> dict[str, Any]:
        return {name: self.value(name, value) for name, value in (attributes or {}).items()}


class MaskingExporter(SpanExporter):
    """An exporter that hands the exporter it wraps a masked copy of every span."""

    def __init__(self, exporter: SpanExporter, policy: MaskingPolicy) -> None:
        self._exporter = exporter
        self._policy = policy

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self._exporter.export([self._masked(span) for span in spans])

    def shutdown(self) -> None:
        self._exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._exporter.force_flush(timeout_millis)

    def _masked(self, span: ReadableSpan) -> ReadableSpan:
        policy = self._policy
        return ReadableSpan(
            name=span.name,
            context=span.context,
            parent=span.parent,
            resource=span.resource,
            attributes=policy.attributes(span.attributes),
            events=[
                Event(
                    name=event.name,
                    attributes=policy.attributes(event.attributes),
                    timestamp=event.timestamp,
                )
                for event in span.events
            ],
            links=span.links,
            kind=span.kind,
            status=span.status,
            start_time=span.start_time,
            end_time=span.end_time,
            instrumentation_scope=span.instrumentation_scope,
        )
