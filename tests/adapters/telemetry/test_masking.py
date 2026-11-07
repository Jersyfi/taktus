"""A trace with a personal field is sent through a masking policy and found masked at the
platform (UC-5.8 §2, ADR-0286).

The platform is a stand-in that receives OTLP over HTTP as the OpenTelemetry protocol
specifies it: `POST /v1/traces` with an `ExportTraceServiceRequest` in protobuf. The trace inside
Taktus keeps what it had; only the copy that leaves is masked.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.telemetry import OpenTelemetryTelemetry, exporter_for
from taktus.adapters.driven.telemetry.masking import MASK, MaskingExporter, MaskingPolicy
from taktus.composition.settings import ConfigurationError, load_telemetry


class Platform:
    """What an OTLP/HTTP receiver was sent, by attribute name and value."""

    def __init__(self) -> None:
        self.requests: list[ExportTraceServiceRequest] = []

    def attributes(self) -> dict[str, Any]:
        found: dict[str, Any] = {}
        for request in self.requests:
            for resource in request.resource_spans:
                for scope in resource.scope_spans:
                    for span in scope.spans:
                        for attribute in span.attributes:
                            found[attribute.key] = attribute.value.string_value
                        for event in span.events:
                            for attribute in event.attributes:
                                found[f"event:{attribute.key}"] = attribute.value.string_value
        return found


@pytest.fixture
def platform() -> Iterator[tuple[Platform, str]]:
    received = Platform()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers["Content-Length"]))
            if self.path == "/v1/traces":
                request = ExportTraceServiceRequest()
                request.ParseFromString(body)
                received.requests.append(request)
            self.send_response(200)
            self.send_header("Content-Type", "application/x-protobuf")
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield received, f"http://127.0.0.1:{server.server_address[1]}/v1/traces"
    finally:
        server.shutdown()


async def test_a_personal_field_leaves_masked_and_stays_whole_inside(
    platform: tuple[Platform, str],
) -> None:
    received, endpoint = platform
    inside = InMemorySpanExporter()
    policy = MaskingPolicy(attributes=("customer.*",), kinds=("email", "iban", "phone"))
    telemetry = OpenTelemetryTelemetry(
        exporter=MaskingExporter(exporter_for(endpoint, protocol="http"), policy),
        processor=SimpleSpanProcessor(inside),
    )
    async with telemetry.span(
        "step",
        {
            "customer.name": "Ada Lovelace",
            "step.note": (
                "write to ada@example.com or +49 30 1234567, IBAN DE89 3704 0044 0532 0130 00"
            ),
            "run.id": "run_1",
        },
    ) as span:
        span.set_attribute("tokens.in", 12)
    telemetry.shutdown()

    sent = received.attributes()
    assert sent["customer.name"] == MASK
    assert sent["step.note"] == f"write to {MASK} or {MASK}, IBAN {MASK}"
    assert sent["run.id"] == "run_1"
    (kept,) = inside.get_finished_spans()
    assert kept.attributes is not None and kept.attributes["customer.name"] == "Ada Lovelace"


def test_the_policy_is_configured_and_an_unknown_kind_is_refused() -> None:
    settings = load_telemetry(
        EnvironmentConfiguration(
            {
                "TAKTUS_OTLP_ENDPOINT": "http://collector:4318/v1/traces",
                "TAKTUS_OTLP_MASKED_ATTRIBUTES": "customer.*,mail.subject",
            }
        )
    )
    assert settings.masked_attributes == ("customer.*", "mail.subject")
    assert settings.masked_kinds == ("email", "iban", "phone"), "every kind by default"
    none = load_telemetry(EnvironmentConfiguration({"TAKTUS_OTLP_MASKED_KINDS": "none"}))
    assert none.masked_kinds == ()
    with pytest.raises(ConfigurationError):
        load_telemetry(EnvironmentConfiguration({"TAKTUS_OTLP_MASKED_KINDS": "email,passport"}))
