"""Creating a process, approving it for operation and setting its autonomy level are three
rights, each granted to a role (UC-7.3, ADR-0257).

The identity component over memory stores holds the identities, their roles and the rights per
role; registration asks it. While no role of the tenant holds a right of a process, nothing is
asked. Once one does, an act by an identity without its right is refused, and `process.refused`
records the right it lacked.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import pytest
from fakes import FakeClock
from fakes.identity import directory
from fakes.takeover import instructed

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.identity.domain.model import Right, RoleRights
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import InvalidProcess, Process, ProcessVersion
from taktus.shared.v1 import LedgerEntry

TENANT = "default"


def bundle(version: str = "1", level: int = 1) -> dict[str, Any]:
    return instructed(
        {
            "id": "paid",
            "version": version,
            "name": "paid",
            "autonomy": {"level": level, "reason": "a test", "toward_next": "nothing"},
            "steps": [
                {
                    "id": "sum",
                    "method": "rule",
                    "reason": "a sum",
                    "rejected": [],
                    "exactness": "tolerant",
                }
            ],
        }
    )


class Given:
    def __init__(self) -> None:
        self.identities = directory()
        self.persistence = MemoryPersistence()
        clock = FakeClock(datetime(2026, 11, 7, 9, 0, tzinfo=UTC))
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), clock)
        self.register = RegisterProcessVersionHandler(
            MemoryRepository(self.persistence, ProcessVersion),
            self.persistence,
            MemoryRepository(self.persistence, Process),
            ledger=self.ledger,
            clock=clock,
            rights=self.identities.directory,
        )

    async def person(self, identity: str, *roles: str) -> None:
        await self.identities.directory.add(TENANT, identity, (TENANT,), roles=roles)

    async def grant(self, role: str, *rights: Right) -> None:
        for right in rights:
            await self.identities.directory.grant(TENANT, role, right, by="idn_admin")

    async def entries(self) -> list[LedgerEntry]:
        async with self.persistence.transaction(TENANT):
            return list(await self.ledger.entries(TENANT))


async def test_while_no_role_holds_a_right_of_a_process_nothing_is_asked() -> None:
    given = Given()
    await given.grant("ops", Right.START)
    version = await given.register.execute(RegisterProcessVersion(bundle=bundle(), tenant=TENANT))
    assert version.ref == "paid@1"


@pytest.mark.parametrize(
    ("held", "lacked"),
    [
        ((Right.PROCESS_APPROVE, Right.AUTONOMY_SET), "process.create"),
        ((Right.PROCESS_CREATE, Right.AUTONOMY_SET), "process.approve"),
        ((Right.PROCESS_CREATE, Right.PROCESS_APPROVE), "autonomy.set"),
    ],
)
async def test_each_act_on_a_new_process_is_a_right_of_its_own_and_refused_without_it(
    held: tuple[Right, ...], lacked: str
) -> None:
    given = Given()
    await given.person("idn_ada", "process-owner")
    await given.grant("process-owner", *held)
    with pytest.raises(
        InvalidProcess, match=rf"'idn_ada' may not .* lacks the right {re.escape(lacked)}"
    ):
        await given.register.execute(
            RegisterProcessVersion(bundle=bundle(), tenant=TENANT, by="idn_ada")
        )
    [refused] = [e for e in await given.entries() if e.kind == "process.refused"]
    assert refused.outcome == "lacks_" + lacked.replace(".", "_")
    assert refused.refs.actor == "idn_ada" and refused.refs.process_version == "paid@1"


async def test_an_identity_holding_the_three_rights_through_its_roles_registers() -> None:
    given = Given()
    await given.person("idn_ada", "process-owner", "autonomy-board")
    await given.grant("process-owner", Right.PROCESS_CREATE, Right.PROCESS_APPROVE)
    await given.grant("autonomy-board", Right.AUTONOMY_SET)
    version = await given.register.execute(
        RegisterProcessVersion(bundle=bundle(), tenant=TENANT, by="idn_ada")
    )
    assert version.ref == "paid@1"
    assert not [e for e in await given.entries() if e.kind == "process.refused"]


async def test_approving_a_new_version_and_raising_its_level_are_separate_rights() -> None:
    given = Given()
    await given.person("idn_ada", "process-owner", "autonomy-board")
    await given.person("idn_bo", "operator")
    await given.grant("process-owner", Right.PROCESS_CREATE, Right.PROCESS_APPROVE)
    await given.grant("autonomy-board", Right.AUTONOMY_SET)
    await given.grant("operator", Right.PROCESS_APPROVE)
    await given.register.execute(
        RegisterProcessVersion(bundle=bundle(), tenant=TENANT, by="idn_ada")
    )

    same_level = await given.register.execute(
        RegisterProcessVersion(bundle=bundle("2"), tenant=TENANT, by="idn_bo")
    )
    assert same_level.ref == "paid@2", "approving needs no right to create or to set the level"
    with pytest.raises(InvalidProcess, match=r"'idn_bo' may not raise .* autonomy\.set"):
        await given.register.execute(
            RegisterProcessVersion(
                bundle=bundle("3", level=2), tenant=TENANT, by="idn_bo", approved_by="idn_bo"
            )
        )
    outcomes = [e.outcome for e in await given.entries() if e.kind == "process.refused"]
    assert outcomes == ["lacks_autonomy_set"]


async def test_an_act_naming_no_identity_is_refused_once_rights_are_granted() -> None:
    given = Given()
    await given.grant("process-owner", Right.PROCESS_CREATE)
    with pytest.raises(InvalidProcess, match="an act naming no identity may not create"):
        await given.register.execute(RegisterProcessVersion(bundle=bundle(), tenant=TENANT))


def test_a_right_is_held_by_a_role_and_no_record_grants_one_to_a_person() -> None:
    assert set(RoleRights.model_fields) == {"id", "tenant", "rights"}, "keyed by the role alone"
    assert {r.value for r in Right} >= {"process.create", "process.approve", "autonomy.set"}
