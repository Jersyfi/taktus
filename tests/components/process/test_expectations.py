"""A process version declares when a run is expected (ADR-0107 §1, UC-4.16): a schedule, or a
longest gap between two runs, and a bound on how long a run may take. A scheduled version
without a declaration inherits its schedule triggers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fakes import FakeClock

from components.process.test_bundle_parsing import bundle
from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.deactivate import (
    DeactivateProcess,
    DeactivateProcessHandler,
)
from taktus.components.process.application.service.expectations import ExpectationsHandler
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
    parse_bundle,
)
from taktus.components.process.domain.model import Expect, InvalidProcess, Process, ProcessVersion
from taktus.components.process.domain.service.bundle import bundle_of

TENANT = "t"
AT = datetime(2026, 10, 18, 10, 30, tzinfo=UTC)


def test_a_version_declares_a_schedule_and_a_bound() -> None:
    version = parse_bundle(bundle(expect={"schedule": "0 6 * * *", "bound": "2h"}))
    assert version.expect == Expect(schedule="0 6 * * *", bound=timedelta(hours=2))
    assert version.expected_schedules == ("0 6 * * *",), (
        "the declared schedule replaces the trigger's"
    )


def test_a_version_declares_a_longest_gap() -> None:
    version = parse_bundle(bundle(expect={"gap": "26h"}))
    assert version.expect is not None and version.expect.gap == timedelta(hours=26)
    assert version.expected_schedules == (), "a gap is expected instead of the trigger's slots"


def test_a_scheduled_version_without_a_declaration_inherits_its_schedule() -> None:
    version = parse_bundle(bundle())
    assert version.expect is None
    assert version.expected_schedules == ("daily",)
    bounded = parse_bundle(bundle(expect={"bound": "10m"}))
    assert bounded.expected_schedules == ("daily",), "a bound alone keeps the inherited schedule"


def test_a_version_without_a_schedule_expects_nothing_unless_it_says_so() -> None:
    assert parse_bundle(bundle(triggers=[])).expected_schedules == ()


@pytest.mark.parametrize(
    ("expect", "says"),
    [
        ({"schedule": "daily", "gap": "1h"}, "not both"),
        ({"schedule": "61 * * * *"}, "minute"),
        ({"gap": "0s"}, "longer than nothing"),
        ({}, "names a `schedule`"),
        ({"every": "1h"}, "takes schedule, gap and bound"),
        ("daily", "not a mapping"),
    ],
)
def test_a_declaration_that_does_not_hold_is_refused(expect: Any, says: str) -> None:
    with pytest.raises(InvalidProcess) as raised:
        parse_bundle(bundle(expect=expect))
    assert says in " ".join(raised.value.findings)


def test_a_declaration_survives_a_rollback_s_bundle() -> None:
    version = parse_bundle(bundle(expect={"gap": "26h", "bound": "90s"}))
    again = parse_bundle(bundle_of(version, as_version="2", author=None, reason="r"))
    assert again.expect == version.expect


class World:
    def __init__(self) -> None:
        self.clock = FakeClock(AT)
        self.persistence = MemoryPersistence()
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.processes = MemoryRepository(self.persistence, Process)
        self.versions = MemoryRepository(self.persistence, ProcessVersion)
        self.register = RegisterProcessVersionHandler(
            self.versions, self.persistence, self.processes, ledger=self.ledger, clock=self.clock
        )
        self.expectations = ExpectationsHandler(self.processes, self.versions, self.persistence)

    async def registered(self, document: dict[str, Any]) -> None:
        await self.register.execute(RegisterProcessVersion(document, tenant=TENANT, by="idn_op"))


async def test_the_latest_slot_after_the_activation_is_expected() -> None:
    world = World()
    await world.registered(bundle(triggers=[{"schedule": "hourly"}], expect={"bound": "5m"}))
    assert (await world.expectations.expected(TENANT, AT))[0].slots == (), (
        "10:00 lies before the activation at 10:30"
    )
    (expected,) = await world.expectations.expected(TENANT, AT + timedelta(minutes=45))
    assert expected.process_version == "p@1" and expected.activated_at >= AT
    assert expected.slots == (("hourly", datetime(2026, 10, 18, 11, 0, tzinfo=UTC)),)
    assert expected.bound == timedelta(minutes=5) and expected.gap is None


async def test_a_switched_off_process_expects_nothing() -> None:
    world = World()
    await world.registered(bundle(triggers=[{"schedule": "hourly"}]))
    await DeactivateProcessHandler(world.processes, world.persistence, world.ledger).execute(
        DeactivateProcess(tenant=TENANT, process_id="p", by="idn_op")
    )
    assert await world.expectations.expected(TENANT, AT + timedelta(hours=3)) == []
