"""Writing on a connection is granted by a person with the right, and recorded (ADR-0262 §2,
UC-5.6 §2): a new connection reads only; the owner grants and withdraws; a process, a worker,
an unknown identity and a person without the right are refused, and the refusal is recorded."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from fakes.clock import FakeClock

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.governance.application.service import (
    ConnectionGrants,
    Granter,
    GrantRefused,
    NotGrantable,
)
from taktus.components.governance.domain.model import ConnectionGrant
from taktus.components.ledger.application.service import ChainedLedger
from taktus.ports.identity import Resolution

TENANT = "t"
WAREHOUSE = "warehouse.queries"


@dataclass
class People:
    """The identities the tenant knows, with their roles."""

    roles: dict[str, tuple[str, ...]] = field(default_factory=dict)

    async def identity(self, tenant: str, identity: str) -> Resolution | None:
        if identity not in self.roles:
            return None
        return Resolution(
            tenant=tenant, identity=identity, org_path=("org",), roles=self.roles[identity]
        )


class Given:
    def __init__(self) -> None:
        self.persistence = MemoryPersistence()
        self.clock = FakeClock()
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.grants = ConnectionGrants(
            MemoryRepository(self.persistence, ConnectionGrant),
            self.ledger,
            self.persistence,
            self.clock,
            People({"idn_owner": ("owner",), "idn_analyst": ("analyst",)}),  # type: ignore[arg-type]
        )

    async def kinds(self) -> list[tuple[str, str | None, str | None]]:
        async with self.persistence.transaction(TENANT):
            entries = await self.ledger.entries(TENANT)
        return [(e.kind, e.outcome, e.refs.actor) for e in entries]


async def test_a_new_connection_reads_only() -> None:
    given = Given()
    assert await given.grants.granted(TENANT, WAREHOUSE) is False
    assert await given.grants.grant(TENANT, WAREHOUSE) is None


async def test_the_owner_grants_writing_and_withdraws_it_and_each_act_is_recorded() -> None:
    given = Given()
    grant = await given.grants.give(TENANT, WAREHOUSE, by=Granter("idn_owner"))
    assert grant.in_force and await given.grants.granted(TENANT, WAREHOUSE)
    withdrawn = await given.grants.withdraw(TENANT, WAREHOUSE, by=Granter("idn_owner"))
    assert not withdrawn.in_force and not await given.grants.granted(TENANT, WAREHOUSE)
    assert await given.kinds() == [
        ("connection.granted", "granted", "idn_owner"),
        ("connection.withdrawn", "withdrawn", "idn_owner"),
    ]
    async with given.persistence.transaction(TENANT):
        entries = await given.ledger.entries(TENANT)
    assert all(e.content_digest and e.content_digest.startswith("sha256:") for e in entries)


@pytest.mark.parametrize(
    ("by", "reason"),
    [
        (Granter("idn_owner", run_id="run_1"), "process"),
        (Granter("idn_owner", assignment_id="asg_1"), "worker"),
        (Granter("idn_stranger"), "unknown"),
        (Granter("idn_analyst"), "role"),
    ],
)
async def test_anyone_but_a_person_with_the_right_is_refused_and_the_refusal_recorded(
    by: Granter, reason: str
) -> None:
    given = Given()
    with pytest.raises(GrantRefused) as refused:
        await given.grants.give(TENANT, WAREHOUSE, by=by)
    assert refused.value.reason == reason
    assert await given.grants.granted(TENANT, WAREHOUSE) is False
    assert await given.kinds() == [("connection.refused", reason, by.identity)]


async def test_a_connection_that_needs_no_grant_has_nothing_to_grant() -> None:
    given = Given()
    with pytest.raises(NotGrantable):
        await given.grants.give(TENANT, "chat.threads", by=Granter("idn_owner"))
    assert await given.kinds() == []
