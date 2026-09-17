"""The fake repository hosting service, in a thread, with two credentials: one that may write
and one that may only read. The values are random per session and reach the connector the way
the contract says — through the environment, under the name a call references — and nowhere
else."""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from fakes import repository_service

type Json = dict[str, Any]

WRITE_CREDENTIAL = "REPOSITORY_TOKEN"
READ_CREDENTIAL = "REPOSITORY_TOKEN_READONLY"


@dataclass(frozen=True)
class Service:
    url: str
    write_value: str
    read_value: str

    def state(self) -> Json:
        result: Json = httpx.get(f"{self.url}/_fake/state", timeout=5.0).json()
        return result

    def control(self, path: str, body: Json) -> None:
        httpx.post(f"{self.url}{path}", json=body, timeout=5.0).raise_for_status()

    def reset(self) -> None:
        self.control("/_fake/reset", {})


@pytest.fixture(scope="session")
def service() -> Iterator[Service]:
    write_value = "write-" + secrets.token_hex(8)
    read_value = "read-" + secrets.token_hex(8)
    server = repository_service.make_server(
        "127.0.0.1", 0, {write_value: "write", read_value: "read"}
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield Service(f"http://{host}:{port}", write_value, read_value)
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def credentials(service: Service, monkeypatch: pytest.MonkeyPatch) -> None:
    """The two values in the environment, as the connector's runtime would put them there."""
    monkeypatch.setenv(WRITE_CREDENTIAL, service.write_value)
    monkeypatch.setenv(READ_CREDENTIAL, service.read_value)
    service.reset()
