"""Telemetry adapters. `noop` is the default: spans are opened and closed and go nowhere. An
OpenTelemetry exporter arrives with the roles that run in operation."""

from taktus.adapters.driven.telemetry.noop import NoTelemetry

__all__ = ["NoTelemetry"]
