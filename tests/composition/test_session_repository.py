"""A session reads the project's repository through its code search, as the participant, with
the participant's own credential (ADR-0306, UC-1.8).

The repository connector is served over MCP in this process against the fake of the hosting
service. One participant holds a token the service admits; one holds a token it refuses; one
holds none, and the service is not asked for them at all.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fakes import FakeClock, FakeIdentifiers
from fakes import repository_service as service
from taktus_connectors.github import declaration
from taktus_connectors.github.server import Config, build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.command.application.service.sessions import Sessions
from taktus.components.identity.domain.model import Identity
from taktus.components.identity.domain.model.structure import Circle, Reference
from taktus.components.ledger.application.service import ChainedLedger
from taktus.composition.personal import ConfiguredPersonalCredentials
from taktus.composition.sessions import SourceKnowledge, SourceSystem
from taktus.composition.workspace import structure_of, workspace_of
from taktus.ports.connector import CallContext, Capabilities, ResolvedConnector
from taktus.ports.persistence import Stored
from taktus.ports.worker import CredentialReference
from taktus.shared.v1 import Capability

T = "acme"
AT = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
WEB = "channel.web"
REPOSITORY = "acme/product"
WRITER, ADA = "write-" + secrets.token_hex(8), "read-" + secrets.token_hex(8)
SOURCE = SourceSystem(
    kind="repository",
    operation="repository.code.search",
    credential="REPOSITORY_TOKEN",
    read="repository.files.read_many",
    ref="main",
)


@dataclass
class Pool:
    connector: McpActionConnector

    async def resolve(self, capability: Capability) -> ResolvedConnector | None:
        if capability not in ("repository.code", "repository.files"):
            return None
        return ResolvedConnector(
            adapter="repository",
            connector=self.connector,
            declaration=Capabilities.model_validate(declaration.capabilities()),
        )


@pytest.fixture
def hosted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    server = service.make_server("127.0.0.1", 0, {WRITER: "write", ADA: "read"})
    threading.Thread(target=server.serve_forever, daemon=True).start()
    for name, value in (
        ("REPOSITORY_TOKEN_WRITER", WRITER),
        ("REPOSITORY_TOKEN_ADA", ADA),
        ("REPOSITORY_TOKEN_BOB", "read-" + secrets.token_hex(8)),  # one the service refuses
    ):
        path = tmp_path / name.lower()
        path.write_text(value, encoding="utf-8")
        monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{name}_FILE", str(path))
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


async def committed(connector: McpActionConnector) -> None:
    def context(step: str) -> CallContext:
        return CallContext(
            tenant=T,
            identity="idn_writer",
            run_id="run_seed",
            step_id=step,
            attempt=1,
            idempotency_key=f"taktus:run_seed:{step}:1",
            credentials=(CredentialReference(name="REPOSITORY_TOKEN_WRITER", injected_as="env"),),
        )

    main = await connector.call("repository.branches.read", context("read"), {"name": "main"})
    await connector.call(
        "repository.branches.commit",
        context("commit"),
        {
            "name": "main",
            "expected": main.output["sha"],
            "files": [
                {"path": "docs/release.md", "content": "We release on Thursdays.\n"},
                {"path": "src/app.py", "content": "print('hello')\n"},
            ],
        },
    )


async def sessions_of(url: str) -> Sessions:
    persistence = MemoryPersistence()
    clock = FakeClock(AT)
    ledger = ChainedLedger(MemoryLedgerStore(persistence), clock)

    def stored[K: Stored](kind: type[K]) -> MemoryRepository[K]:
        return MemoryRepository(persistence, kind)

    async with persistence.transaction(T):
        for who in ("idn_ada", "idn_bob", "idn_carl"):
            await stored(Identity).put(T, Identity(id=who, tenant=T, org_path=(T,), created_at=AT))
    structure = structure_of(stored, persistence, ledger, clock)
    await structure.create_project(
        T, "launch", "Launch", Circle.PROJECT_TEAM, by="idn_ada", members=("idn_bob", "idn_carl")
    )
    await structure.refer(
        T,
        "launch",
        Reference(kind="repository", link="https://code.example.org/acme/product", title="Code"),
        by="idn_ada",
    )
    connector = McpActionConnector(build_server(Config(target=url, repository=REPOSITORY)))
    await committed(connector)
    personal = ConfiguredPersonalCredentials(
        {
            ("idn_ada", "REPOSITORY_TOKEN"): "REPOSITORY_TOKEN_ADA",
            ("idn_bob", "REPOSITORY_TOKEN"): "REPOSITORY_TOKEN_BOB",
        }
    )
    pool = Pool(connector)
    return workspace_of(
        stored,
        persistence,
        ledger,
        clock,
        FakeIdentifiers(),
        structure,
        knowledge=lambda held: SourceKnowledge(held, (SOURCE,), pool, personal),
    ).sessions


async def answered(sessions: Sessions, who: str, asked: str) -> list[tuple[str, str | None]]:
    session = await sessions.open(T, "launch", who)
    answer = await sessions.say(T, session.id, who, WEB, asked)
    return [(s.text, None if s.source is None else s.source.link) for s in answer.statements]


async def test_a_participant_reads_the_repository_through_its_search_as_themselves(
    hosted: str,
) -> None:
    sessions = await sessions_of(hosted)
    said = await answered(sessions, "idn_ada", "when do we release?")
    assert (
        "We release on Thursdays.",
        "https://code.example.org/acme/product#docs/release.md",
    ) in said
    assert all("hello" not in text for text, _ in said), "only what the search found"


async def test_a_refused_credential_or_none_gets_nothing_from_the_repository(hosted: str) -> None:
    sessions = await sessions_of(hosted)
    for who in ("idn_bob", "idn_carl"):
        said = await answered(sessions, who, "when do we release?")
        assert all("Thursdays" not in text for text, _ in said), who
