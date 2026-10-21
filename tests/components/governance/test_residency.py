"""A tenant's residency rule: kept, narrowed per data class, never widened (ADR-0116 §3, issue
#328; NTC-0217)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fakes import FakeClock
from pydantic import ValidationError

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.governance.application.service import ConfigureResidency, TenantResidency
from taktus.components.governance.domain.model import ResidencyRule, shipped_rule
from taktus.components.ledger.application.service import ChainedLedger

AT = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
TENANT = "t"


def residency() -> tuple[TenantResidency, ChainedLedger, MemoryPersistence]:
    clock = FakeClock(AT)
    persistence = MemoryPersistence()
    ledger = ChainedLedger(MemoryLedgerStore(persistence), clock)
    rules = MemoryRepository(persistence, ResidencyRule)
    return TenantResidency(rules, ledger, persistence, clock), ledger, persistence


async def test_a_tenant_that_set_no_rule_permits_anywhere() -> None:
    service, _, _ = residency()
    assert await service.rule(TENANT) == shipped_rule(TENANT)
    assert await service.permitted(TENANT, None) == "anywhere"
    assert await service.permitted(TENANT, "personal") == "anywhere"


async def test_a_rule_is_set_narrowed_per_class_and_recorded_in_the_ledger() -> None:
    service, ledger, persistence = residency()
    rule = await service.configure(
        ConfigureResidency(tenant=TENANT, location="eu", classes={"personal": "own"}), by="op"
    )
    assert (rule.location, rule.classes) == ("eu", {"personal": "own"})
    assert await service.permitted(TENANT, None) == "eu"
    assert await service.permitted(TENANT, "personal") == "own"
    assert await service.permitted(TENANT, "public") == "eu"
    async with persistence.transaction(TENANT):
        (entry,) = [e for e in await ledger.entries(TENANT) if e.kind == "residency.configured"]
    assert (entry.outcome, entry.refs.actor) == ("eu", "op")
    cleared = await service.configure(
        ConfigureResidency(tenant=TENANT, cleared=("personal",)), by="op"
    )
    assert (cleared.location, cleared.classes) == ("eu", {})


async def test_a_class_is_never_wider_than_the_tenant_s_rule() -> None:
    with pytest.raises(ValidationError, match="never widens"):
        ResidencyRule(id=TENANT, tenant=TENANT, location="eu", classes={"public": "anywhere"})
    service, _, _ = residency()
    await service.configure(ConfigureResidency(tenant=TENANT, location="eu"), by="op")
    with pytest.raises(ValueError, match="never widens"):
        await service.configure(
            ConfigureResidency(tenant=TENANT, classes={"public": "anywhere"}), by="op"
        )
    assert await service.permitted(TENANT, "public") == "eu"
