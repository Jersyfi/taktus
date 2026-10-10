"""The telemetry port over the OpenTelemetry SDK: real spans and histograms, exported where
configured.

Spans are always real — nested through the context, each with a trace identifier the engine
writes into its ledger entries and the log carries on every line — and exported only when an
OTLP endpoint is configured (`TAKTUS_OTLP_*`, `composition/settings.py`). Without one, the
provider has no exporter: the no-op is the export, not the trace, so that a ledger entry and a
log line can be joined by trace identifier whether or not anything collects the spans.

What a span may carry is the port's business: identifiers, tokens, measured quantities. This
adapter refuses an attribute whose name is not a dotted lowercase token, so that nothing is
smuggled in under a name nobody reviews, and never records an exception's traceback — a
failure is a status and a short description.

A histogram is recorded into a meter provider of this adapter's own. It is exported to the same
OTLP endpoint as the spans, every `METRIC_INTERVAL_MILLIS`, and nowhere without one.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Literal

from opentelemetry import trace
from opentelemetry.metrics import Histogram
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    MetricExporter,
    MetricReader,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.trace import Span as OtelSpan
from opentelemetry.trace import StatusCode

from taktus.ports.telemetry import Attributes, AttributeValue, Span

ATTRIBUTE_NAME = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
type Protocol = Literal["grpc", "http"]
METRIC_INTERVAL_MILLIS = 30_000


class OpenTelemetrySpan:
    def __init__(self, span: OtelSpan) -> None:
        self._span = span

    def set_attribute(self, name: str, value: AttributeValue) -> None:
        self._span.set_attribute(_checked(name), value)

    def record_failure(self, description: str) -> None:
        self._span.set_status(StatusCode.ERROR, description)


class OpenTelemetryTelemetry:
    def __init__(
        self,
        *,
        service_name: str = "taktus",
        exporter: SpanExporter | None = None,
        processor: SpanProcessor | None = None,
        metric_exporter: MetricExporter | None = None,
        metric_reader: MetricReader | None = None,
    ) -> None:
        """`exporter` is where spans go — none means nowhere; `processor` is for a test that
        wants to look at finished spans without an exporter's batching. `metric_exporter` is
        where histograms go, `metric_reader` a test's way of reading them."""
        resource = Resource.create({"service.name": service_name})
        self._provider = TracerProvider(resource=resource)
        if exporter is not None:
            self._provider.add_span_processor(BatchSpanProcessor(exporter))
        if processor is not None:
            self._provider.add_span_processor(processor)
        self._tracer = self._provider.get_tracer("taktus")
        readers: list[MetricReader] = []
        if metric_exporter is not None:
            readers.append(
                PeriodicExportingMetricReader(
                    metric_exporter, export_interval_millis=METRIC_INTERVAL_MILLIS
                )
            )
        if metric_reader is not None:
            readers.append(metric_reader)
        self._meters = MeterProvider(resource=resource, metric_readers=readers)
        self._meter = self._meters.get_meter("taktus")
        self._histograms: dict[str, Histogram] = {}

    @asynccontextmanager
    async def span(self, name: str, attributes: Attributes | None = None) -> AsyncIterator[Span]:
        checked = {_checked(key): value for key, value in (attributes or {}).items()}
        with self._tracer.start_as_current_span(
            name, attributes=checked, record_exception=False, set_status_on_exception=True
        ) as span:
            yield OpenTelemetrySpan(span)

    def current_trace_id(self) -> str | None:
        context = trace.get_current_span().get_span_context()
        if not context.is_valid:
            return None
        return format(context.trace_id, "032x")

    def observe(
        self, name: str, value: float, *, unit: str, attributes: Attributes | None = None
    ) -> None:
        histogram = self._histograms.get(name)
        if histogram is None:
            histogram = self._meter.create_histogram(_checked(name), unit=unit)
            self._histograms[name] = histogram
        checked = {_checked(key): v for key, v in (attributes or {}).items()}
        histogram.record(value, attributes=checked)

    def shutdown(self) -> None:
        """Flush what is queued and stop the exporters; the daemon calls it on the way out."""
        self._provider.shutdown()
        self._meters.shutdown()


def exporter_for(
    endpoint: str, *, protocol: Protocol, headers: Mapping[str, str] | None = None
) -> SpanExporter:
    """The OTLP exporter for the configured endpoint. Imported here, so that a process without
    an endpoint never loads an exporter."""
    if protocol == "grpc":
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter as GrpcExporter,
        )

        return GrpcExporter(endpoint=endpoint, headers=dict(headers or {}))
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter as HttpExporter,
    )

    return HttpExporter(endpoint=endpoint, headers=dict(headers or {}))


def metric_exporter_for(
    endpoint: str, *, protocol: Protocol, headers: Mapping[str, str] | None = None
) -> MetricExporter:
    """The OTLP exporter for histograms, to the endpoint the spans go to. Over HTTP an endpoint
    names the path of the spans, `/v1/traces`; the histograms go to `/v1/metrics` beside it."""
    if protocol == "grpc":
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
            OTLPMetricExporter as GrpcExporter,
        )

        return GrpcExporter(endpoint=endpoint, headers=dict(headers or {}))
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
        OTLPMetricExporter as HttpExporter,
    )

    base = endpoint.rstrip("/").removesuffix("/v1/traces")
    return HttpExporter(endpoint=f"{base}/v1/metrics", headers=dict(headers or {}))


def current_trace_id() -> str | None:
    """The same question, for a caller that has no adapter at hand — the log processor."""
    context = trace.get_current_span().get_span_context()
    return format(context.trace_id, "032x") if context.is_valid else None


def _checked(name: str) -> str:
    if not ATTRIBUTE_NAME.match(name):
        raise ValueError(f"{name!r} is not an attribute name: lowercase, dotted, no spaces")
    return name
