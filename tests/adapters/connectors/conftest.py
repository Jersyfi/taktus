"""The fake repository hosting service, in a thread, with two credentials: one that may write
and one that may only read — and Taktus's own app (ADR-0033), whose private key is generated
here for the session. The values are random per session and reach the connector the way the
contract says — through the environment, under the name a call references, or the app's key
through the file its variable names — and nowhere else."""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fakes import chat_service as chat_fake
from fakes import repository_service

type Json = dict[str, Any]

WRITE_CREDENTIAL = "REPOSITORY_TOKEN"
READ_CREDENTIAL = "REPOSITORY_TOKEN_READONLY"


def private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def public_key_pem(private_pem: str) -> str:
    key = serialization.load_pem_private_key(private_pem.encode(), password=None)
    return (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )


@dataclass(frozen=True)
class Service:
    url: str
    write_value: str
    read_value: str
    app_id: str
    app_key: str  # the app's private key, PEM
    app_key_file: Path

    def state(self) -> Json:
        result: Json = httpx.get(f"{self.url}/_fake/state", timeout=5.0).json()
        return result

    def app(self) -> Json:
        """Every token the app was issued and every statement it signed, as the fake saw them."""
        result: Json = httpx.get(f"{self.url}/_fake/app", timeout=5.0).json()
        return result

    def control(self, path: str, body: Json) -> None:
        httpx.post(f"{self.url}{path}", json=body, timeout=5.0).raise_for_status()

    def reset(self) -> None:
        self.control("/_fake/reset", {})


@pytest.fixture(scope="session")
def service(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Service]:
    write_value = "write-" + secrets.token_hex(8)
    read_value = "read-" + secrets.token_hex(8)
    app_id = str(100000 + secrets.randbelow(900000))
    app_key = private_key_pem()
    key_file = tmp_path_factory.mktemp("app") / "app-key.pem"
    key_file.write_text(app_key, encoding="utf-8")
    key_file.chmod(0o600)
    server = repository_service.make_server(
        "127.0.0.1",
        0,
        {write_value: "write", read_value: "read"},
        repository_service.App(app_id, public_key_pem(app_key)),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield Service(f"http://{host}:{port}", write_value, read_value, app_id, app_key, key_file)
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def credentials(service: Service, monkeypatch: pytest.MonkeyPatch) -> None:
    """The two values in the environment, as the connector's runtime would put them there."""
    monkeypatch.setenv(WRITE_CREDENTIAL, service.write_value)
    monkeypatch.setenv(READ_CREDENTIAL, service.read_value)
    service.reset()


# --- the chat service -----------------------------------------------------------------------------

CHAT_WRITE = "CHAT_TOKEN"
CHAT_READ = "CHAT_TOKEN_READONLY"


@dataclass(frozen=True)
class ChatService:
    url: str
    write_value: str
    read_value: str

    def state(self) -> Json:
        result: Json = httpx.get(f"{self.url}/_fake/state", timeout=5.0).json()
        return result

    def messages(self, conversation: str) -> list[Json]:
        listed = httpx.get(
            f"{self.url}/_fake/messages", params={"channel": conversation}, timeout=5.0
        )
        result: list[Json] = listed.json()["messages"]
        return result

    def control(self, path: str, body: Json) -> None:
        httpx.post(f"{self.url}{path}", json=body, timeout=5.0).raise_for_status()

    def reset(self) -> None:
        self.control("/_fake/reset", {})


@pytest.fixture(scope="session")
def chat_service() -> Iterator[ChatService]:
    write_value = "chat-write-" + secrets.token_hex(8)
    read_value = "chat-read-" + secrets.token_hex(8)
    server = chat_fake.make_server("127.0.0.1", 0, {write_value: "write", read_value: "read"})
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield ChatService(f"http://{host!s}:{port}", write_value, read_value)
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def chat_credentials(chat_service: ChatService, monkeypatch: pytest.MonkeyPatch) -> None:
    """The two tokens in the environment, as the connector's runtime would put them there, and
    no file variable that would take precedence."""
    for name in (CHAT_WRITE, CHAT_READ):
        monkeypatch.delenv(f"TAKTUS_CREDENTIAL_{name}_FILE", raising=False)
    monkeypatch.setenv(CHAT_WRITE, chat_service.write_value)
    monkeypatch.setenv(CHAT_READ, chat_service.read_value)
    chat_service.reset()
