"""The expiry connector reads the certificate a TLS endpoint presents and a domain's
registration over RDAP, with the whole days left (ADR-0196, UC-03 B-1.09).

Against `tests/fakes/expiry_service.py` in this process: its RDAP server in a thread, and TLS
endpoints whose certificates expire when the test says. The connector is served in-process over
MCP, as an instance reaches it.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from fakes import expiry_service
from taktus_connectors.expiry.operations import Config, endpoint
from taktus_connectors.expiry.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "tok-" + secrets.token_hex(8)


@pytest.fixture(autouse=True)
def credential(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "expiry_token"
    path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_EXPIRY_TOKEN_FILE", str(path))


@pytest.fixture
def rdap() -> Iterator[str]:
    server = expiry_service.make_server("127.0.0.1", 0, {TOKEN})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def endpoints() -> Iterator[dict[str, expiry_service.TlsEndpoint]]:
    started = {"soon": expiry_service.tls_endpoint(20), "expired": expiry_service.tls_endpoint(-3)}
    yield started
    for one in started.values():
        one.stop()


def context() -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_ops",
        run_id="run_read",
        step_id="read",
        attempt=1,
        idempotency_key=idempotency_key("run_read", "read", 1),
        credentials=(CredentialReference(name="EXPIRY_TOKEN", injected_as="env"),),
    )


def connector(rdap: str = "", *ports: int, ca_file: str | None = None) -> McpActionConnector:
    allowed = frozenset(("127.0.0.1", p) for p in ports)
    return McpActionConnector(build_server(Config(allowed, rdap, ca_file, timeout=5.0)))


# --- certificates --------------------------------------------------------------------------------


async def test_a_certificate_that_verifies_is_read_with_its_days_left(
    endpoints: dict[str, expiry_service.TlsEndpoint],
) -> None:
    soon = endpoints["soon"]
    result = await connector("", soon.port, ca_file=soon.ca_file).call(
        "expiry.certificates.read", context(), {"host": "127.0.0.1", "port": soon.port}
    )
    out = result.output
    assert result.effect.kind.value == "read"
    assert out["trusted"] is True and out["verify_failure"] is None
    assert out["subject"] == "localhost" and out["issuer"] == "Fake Test Authority"
    assert set(out["names"]) == {"localhost", "127.0.0.1"}
    assert out["days_left"] in (19, 20)
    until = datetime.fromisoformat(out["not_after"])
    assert until == soon.not_after
    assert out["key"] == f"certificate:127.0.0.1:{soon.port}:{out['not_after']}"
    assert result.consumption is not None and result.consumption.quota_units == 1


async def test_an_expired_certificate_is_read_untrusted_with_the_reason(
    endpoints: dict[str, expiry_service.TlsEndpoint],
) -> None:
    expired = endpoints["expired"]
    result = await connector("", expired.port, ca_file=expired.ca_file).call(
        "expiry.certificates.read", context(), {"host": "127.0.0.1", "port": expired.port}
    )
    out = result.output
    assert out["trusted"] is False and "expired" in (out["verify_failure"] or "")
    assert out["days_left"] in (-4, -3)
    assert result.consumption is not None and result.consumption.quota_units == 2


async def test_an_unknown_authority_is_untrusted_and_still_read(
    endpoints: dict[str, expiry_service.TlsEndpoint],
) -> None:
    soon = endpoints["soon"]
    result = await connector("", soon.port).call(
        "expiry.certificates.read", context(), {"host": "127.0.0.1", "port": soon.port}
    )
    assert result.output["trusted"] is False and result.output["days_left"] in (19, 20)


async def test_an_endpoint_outside_the_configuration_is_refused_before_any_connection(
    endpoints: dict[str, expiry_service.TlsEndpoint],
) -> None:
    soon = endpoints["soon"]
    with pytest.raises(CallFailed) as failed:
        await connector("", soon.port).call(
            "expiry.certificates.read", context(), {"host": "127.0.0.1", "port": soon.port + 1}
        )
    assert failed.value.error.cause.value == "invalid"


def test_an_endpoint_is_configured_as_host_and_port() -> None:
    assert endpoint("WWW.Example.com") == ("www.example.com", 443)
    assert endpoint("api.example.com:8443") == ("api.example.com", 8443)
    for wrong in ("", "host:", "host:99999", "a b:443"):
        with pytest.raises(ValueError):
            endpoint(wrong)


# --- domains -------------------------------------------------------------------------------------


async def test_a_domain_is_read_with_its_expiration_and_days_left(rdap: str) -> None:
    result = await connector(rdap).call(
        "expiry.domains.read", context(), {"domain": "Example-Product.test."}
    )
    out = result.output
    assert out["domain"] == "example-product.test"
    assert out["days_left"] in (24, 25) and out["expires"] is not None
    assert out["status"] == ["active", "client transfer prohibited"]
    assert out["key"] == f"domain:example-product.test:{out['expires']}"


async def test_a_registration_without_an_expiration_answers_none(rdap: str) -> None:
    out = (
        await connector(rdap).call(
            "expiry.domains.read", context(), {"domain": "example-dropped.test"}
        )
    ).output
    assert out["expires"] is None and out["days_left"] is None


@pytest.mark.parametrize(
    ("domain", "cause"),
    [("unknown.test", "not_found"), ("no spaces.test", "invalid"), ("x", "invalid")],
)
async def test_what_the_registry_does_not_hold_or_cannot_be_a_name_fails_by_its_cause(
    rdap: str, domain: str, cause: str
) -> None:
    with pytest.raises(CallFailed) as failed:
        await connector(rdap).call("expiry.domains.read", context(), {"domain": domain})
    assert failed.value.error.cause.value == cause
