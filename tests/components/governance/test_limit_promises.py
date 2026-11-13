"""Setting a unit limit states what Taktus can promise for each of its lines, as a run's budget
does when it is set (UC-8.5 §2, ADR-0300 §4)."""

from __future__ import annotations

from datetime import UTC, datetime

from fakes import FakeClock

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.governance.application.service.unit_limits import (
    SetUnitLimit,
    UnitLimits,
)
from taktus.components.governance.domain.model.incident import Incident
from taktus.components.governance.domain.model.unit_limits import LimitWatch, UnitLimit
from taktus.components.ledger.application.service import ChainedLedger
from taktus.ports.persistence import Tenant

TENANT = "t"


async def _nobody(tenant: Tenant, name: str) -> bool:
    return False


def limits(pricing: tuple[str, str] | None) -> UnitLimits:
    persistence = MemoryPersistence()
    clock = FakeClock(datetime(2026, 11, 13, 9, 0, tzinfo=UTC))
    return UnitLimits(
        MemoryRepository(persistence, UnitLimit),
        MemoryRepository(persistence, LimitWatch),
        MemoryRepository(persistence, Incident),
        ChainedLedger(MemoryLedgerStore(persistence), clock),
        persistence,
        clock,
        _nobody,
        pricing,
    )


def command(**amounts: object) -> SetUnitLimit:
    return SetUnitLimit(tenant=TENANT, name="field_month", role="finance-lead", **amounts)  # type: ignore[arg-type]


async def test_a_limit_says_how_each_of_its_lines_is_held_when_it_is_set() -> None:
    set_ = await limits(("usd", "table-1")).set(
        command(money={"usd": 100.0, "eur": 90.0}, compute_seconds=3600.0, tokens=10_000),
        by="idn_owner",
    )
    said = {p.line: p for p in set_.promises}
    assert said["money.usd"].how == "estimate" and "table-1" in said["money.usd"].reason
    assert said["money.eur"].how == "unpriced" and "prices in usd" in said["money.eur"].reason
    assert said["compute_seconds"].how == "held"
    assert said["tokens"].how == "estimate"
    assert said["concurrent_runners"].how == "held" and "claim" in said["concurrent_runners"].reason
    stored = await limits(("usd", "table-1")).all(TENANT)
    assert stored == [], "another instance's store holds nothing"


async def test_without_a_price_table_money_is_said_not_to_be_held() -> None:
    held = limits(None)
    set_ = await held.set(command(money={"usd": 100.0}), by="idn_owner")
    (money,) = [p for p in set_.promises if p.line == "money.usd"]
    assert money.how == "unpriced" and "no price table" in money.reason
    (kept,) = await held.all(TENANT)
    assert kept.promises == set_.promises, "the statement is kept with the limit"
