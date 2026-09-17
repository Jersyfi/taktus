"""Telemetry adapters. `otel` is what runs: real spans through the OpenTelemetry SDK, exported
to an OTLP endpoint when one is configured and nowhere otherwise. `noop` is for tests and fakes:
spans that go nowhere and carry no trace identifier."""

from taktus.adapters.driven.telemetry.noop import NoTelemetry
from taktus.adapters.driven.telemetry.otel import OpenTelemetryTelemetry, exporter_for

__all__ = ["NoTelemetry", "OpenTelemetryTelemetry", "exporter_for"]
