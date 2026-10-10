"""A figure observed in operation is a histogram beside the spans (ADR-0055 §7, NTC-0123)."""

from __future__ import annotations

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from taktus.adapters.driven.telemetry import OpenTelemetryTelemetry


def test_a_histogram_reaches_a_metric_reader_with_its_unit_and_checked_names() -> None:
    reader = InMemoryMetricReader()
    telemetry = OpenTelemetryTelemetry(metric_reader=reader)
    telemetry.observe("change.handover", 0.4, unit="s")
    telemetry.observe("change.handover", 1.2, unit="s")
    data = reader.get_metrics_data()
    assert data is not None
    (metric,) = [
        m
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for m in scope.metrics
    ]
    assert (metric.name, metric.unit) == ("change.handover", "s")
    (point,) = metric.data.data_points
    assert point.count == 2 and abs(point.sum - 1.6) < 1e-9
    with pytest.raises(ValueError, match="not an attribute name"):
        telemetry.observe("change.handover", 1.0, unit="s", attributes={"Run Id": "x"})
    telemetry.shutdown()
