"""The identity component over memory stores, and fakes of what it and the intake need around
it: randomness that repeats, an identity source that answers what it is told, a channel that
records what it was told to say."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from fakes.clock import FakeClock
from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.identity.application.service import IdentityDirectory
from taktus.components.identity.domain.model import ChannelLink, Identity, LinkCode
from taktus.components.ledger.application.service import ChainedLedger
from taktus.ports.clock import Clock
from taktus.ports.connector import ChannelReplies, IntakeReplyTo
from taktus.ports.identity import IdentitySource, Resolution, SourceAnswer


class FakeRandomness:
    """Distinct and repeatable: the n-th token is n, padded to the length asked for."""

    def __init__(self) -> None:
        self.drawn = 0

    def token(self, length: int) -> str:
        self.drawn += 1
        return f"{self.drawn:0{length * 2}x}"


@dataclass
class FakeSource(IdentitySource):
    answers: Mapping[tuple[str, str], SourceAnswer] = field(default_factory=dict)
    asked: list[tuple[str, str]] = field(default_factory=list)

    async def lookup(self, channel: str, account: str) -> SourceAnswer | None:
        self.asked.append((channel, account))
        return self.answers.get((channel, account))


@dataclass
class FakeReplies(ChannelReplies):
    said: list[tuple[str, IntakeReplyTo, str, str]] = field(default_factory=list)
    delivers: bool = True

    async def reply(self, tenant: str, to: IntakeReplyTo, text: str, *, key: str) -> bool:
        self.said.append((tenant, to, text, key))
        return self.delivers


@dataclass
class Directory:
    """An identity directory and the stores and ledger it writes, all in memory."""

    persistence: MemoryPersistence
    clock: Any
    """The clock the directory reads; a test that moves time moves it through this."""
    ledger: ChainedLedger
    links: MemoryRepository[ChannelLink]
    directory: IdentityDirectory

    async def kinds(self, tenant: str) -> list[str]:
        async with self.persistence.transaction(tenant):
            return [entry.kind for entry in await self.ledger.entries(tenant)]

    async def person(
        self, tenant: str, name: str, org_path: Sequence[str] = ()
    ) -> tuple[Resolution, str]:
        """An identity added by an administrator, and the account key handed to the person."""
        _, key = await self.directory.add(tenant, name, tuple(org_path) or (tenant,))
        who = await self.directory.authenticate(key)
        assert who is not None
        return who, key

    async def code(self, who: Resolution, channel: str = "channel.repo") -> str:
        """A link code the person created in their Taktus account."""
        code, _ = await self.directory.create_link_code(who, channel)
        return code


def directory(
    tenants: Sequence[str] = ("default",),
    *,
    persistence: MemoryPersistence | None = None,
    clock: Clock | None = None,
    source: IdentitySource | None = None,
) -> Directory:
    persistence = persistence or MemoryPersistence()
    clock = clock or FakeClock()
    ledger = ChainedLedger(MemoryLedgerStore(persistence), clock)
    links = MemoryRepository(persistence, ChannelLink)
    return Directory(
        persistence=persistence,
        clock=clock,
        ledger=ledger,
        links=links,
        directory=IdentityDirectory(
            tenants=tenants,
            identities=MemoryRepository(persistence, Identity),
            links=links,
            codes=MemoryRepository(persistence, LinkCode),
            work=persistence,
            ledger=ledger,
            clock=clock,
            randomness=FakeRandomness(),
            source=source,
        ),
    )


def added_by_command_line(
    taktusctl: str, identity: str, env: Mapping[str, str] | None = None, *options: str
) -> None:
    """`taktusctl identity add`, as an administrator does it before a command line run names
    the identity: nothing executes as an identity the component does not know (ADR-0040)."""
    import subprocess

    completed = subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl, "identity", "add", identity, *options],
        capture_output=True,
        text=True,
        env=dict(env) if env is not None else None,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
