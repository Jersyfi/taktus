"""A tenant's quotas per organisational unit: set, recorded, cleared, read by the run through
its port, and never set on a person (ADR-0166, UC-7.11; principle 14)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fakes import FakeClock

from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryOrgUnitSpends,
    MemoryPersistence,
    MemoryRepository,
)
from taktus.components.governance.application.service import (
    OrgUnitQuotaRefused,
    SetOrgUnitQuota,
    TenantOrgUnits,
)
from taktus.components.governance.domain.model import OrgUnitQuota
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.run.ports import OrgUnitBudget
from taktus.composition.org_units import OrgUnitsOfTheRun

AT = datetime(2026, 10, 31, 9, 0, tzinfo=UTC)
TENANT = "t"
PERSONS = {"idn_ada", "ada"}


async def is_person(tenant: str, name: str) -> bool:
    return name in PERSONS


def kept() -> tuple[TenantOrgUnits, ChainedLedger, MemoryPersistence]:
    clock = FakeClock(AT)
    persistence = MemoryPersistence()
    ledger = ChainedLedger(MemoryLedgerStore(persistence), clock)
    service = TenantOrgUnits(
        MemoryRepository(persistence, OrgUnitQuota), ledger, persistence, clock, is_person
    )
    return service, ledger, persistence


async def kinds(ledger: ChainedLedger, persistence: MemoryPersistence) -> list[str]:
    async with persistence.transaction(TENANT):
        return [f"{e.kind}:{e.outcome}:{e.refs.actor}" for e in await ledger.entries(TENANT)]


async def test_a_tenant_without_quotas_holds_none_and_the_run_sees_none() -> None:
    service, _, persistence = kept()
    port = OrgUnitsOfTheRun(service, MemoryOrgUnitSpends(persistence))
    assert await service.quotas(TENANT) == []
    assert await port.concurrent(TENANT) == {}
    assert await port.budget(TENANT, "sales") is None


async def test_a_quota_is_set_recorded_by_its_person_and_read_by_the_run() -> None:
    service, ledger, persistence = kept()
    await service.set(
        SetOrgUnitQuota(tenant=TENANT, org_unit="sales", concurrent_runs=2, budget={"eur": 250.0}),
        by="idn_admin",
    )
    await service.set(
        SetOrgUnitQuota(tenant=TENANT, org_unit="support", concurrent_runs=1), by="idn_admin"
    )
    port = OrgUnitsOfTheRun(service, MemoryOrgUnitSpends(persistence))
    assert await port.concurrent(TENANT) == {"sales": 2, "support": 1}
    assert await port.budget(TENANT, "sales") == OrgUnitBudget(amounts={"eur": 250.0})
    assert await port.budget(TENANT, "support") is None, "support limits places, not money"
    assert await kinds(ledger, persistence) == [
        "units.configured:configured:idn_admin",
        "units.configured:configured:idn_admin",
    ]


async def test_a_cleared_quota_limits_nothing_and_is_recorded() -> None:
    service, ledger, persistence = kept()
    await service.set(SetOrgUnitQuota(tenant=TENANT, org_unit="sales", concurrent_runs=2), by="a")
    await service.set(SetOrgUnitQuota(tenant=TENANT, org_unit="sales"), by="a")
    assert await service.quotas(TENANT) == []
    assert await service.concurrent(TENANT) == {}
    assert (await kinds(ledger, persistence))[-1] == "units.configured:cleared:a"


@pytest.mark.parametrize("name", sorted(PERSONS))
async def test_a_quota_is_never_set_on_a_person(name: str) -> None:
    service, ledger, persistence = kept()
    with pytest.raises(OrgUnitQuotaRefused, match="principle 14"):
        await service.set(
            SetOrgUnitQuota(tenant=TENANT, org_unit=name, concurrent_runs=1), by="idn_admin"
        )
    assert await service.quotas(TENANT) == []
    assert await kinds(ledger, persistence) == [], "a refusal changes nothing"


@pytest.mark.parametrize("name", ["sales/emea", " sales"])
async def test_a_quota_names_one_level_of_the_structure(name: str) -> None:
    service, _, _ = kept()
    with pytest.raises(OrgUnitQuotaRefused):
        await service.set(SetOrgUnitQuota(tenant=TENANT, org_unit=name, concurrent_runs=1), by="a")
