"""Registration holds a version to the tenant's residency rule (UC-11.1 §2, ADR-0281 §4).

A version whose step handling data of a restricted class would be bound to a model, a worker, a
connector or a host outside the permitted location does not register; each finding names the
step, the data class and the adapter. The composition root answers registration's port from the
pools and the tenant's rule, as an instance is wired.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fakes import FakeClock, FakeConnector, FakeWorker
from fakes.model import FakeModel
from fakes.takeover import instructed

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.adapters.driven.models import Declared, StaticModelPool
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.governance.application.service import ConfigureResidency, TenantResidency
from taktus.components.governance.domain.model import ResidencyRule
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import InvalidProcess, Process, ProcessVersion
from taktus.composition.pools import Pools
from taktus.composition.residency import PoolBindings
from taktus.ports.model import Location

TENANT = "t"
CHANGE = "change.implement"


def connector(data_class: str | None = "personal") -> dict[str, Any]:
    work: dict[str, Any] = {"rule": "connector", "operation": "fake.records.create", "input": {}}
    if data_class is not None:
        work["data_class"] = data_class
    return {
        "id": "write",
        "method": "rule",
        "reason": "r",
        "rejected": [],
        "exactness": "sourced",
        "checks": [{"kind": "bounds", "pattern": "^\\{"}],
        "work": work,
    }


def worker(*hosts: str) -> dict[str, Any]:
    return {
        "id": "implement",
        "method": "worker",
        "reason": "r",
        "rejected": [],
        "exactness": "tolerant",
        "fallback": {"when": "x", "to": "human"},
        "requires": [CHANGE],
        "work": {
            "task": {"goal": "g", "acceptance": ["a"]},
            "allowed_hosts": list(hosts),
            "data_class": "personal",
        },
    }


def model() -> dict[str, Any]:
    return {
        "id": "draft",
        "method": "llm",
        "reason": "free text",
        "rejected": [{"method": "rule", "why": "too varied"}],
        "exactness": "free",
        "fallback": {"when": "unclear", "to": "human"},
        "work": {"purpose": "drafting", "prompt": "x", "data_class": "personal"},
    }


def bundle(*steps: dict[str, Any]) -> dict[str, Any]:
    return instructed(
        {
            "id": "payroll",
            "version": "1",
            "name": "payroll",
            "autonomy": {"level": 3, "reason": "a test", "toward_next": "nothing"},
            "steps": list(steps),
        }
    )


async def handler(
    *,
    connector_at: Location = "elsewhere",
    workers_at: tuple[Location, ...] = ("elsewhere",),
    models_at: tuple[Location, ...] = ("elsewhere",),
    hosts: dict[str, Location] | None = None,
    personal: str = "eu",
) -> RegisterProcessVersionHandler:
    clock = FakeClock(datetime(2026, 11, 7, 9, 0, tzinfo=UTC))
    persistence = MemoryPersistence()
    ledger = ChainedLedger(MemoryLedgerStore(persistence), clock)
    rule = TenantResidency(MemoryRepository(persistence, ResidencyRule), ledger, persistence, clock)
    await rule.configure(
        ConfigureResidency(tenant=TENANT, location="anywhere", classes={"personal": personal}),
        by="op",
    )
    pools = Pools(
        StaticWorkerPool(
            [
                (f"worker.{at}", FakeWorker(capabilities_offered=(CHANGE,), data_location=at))
                for at in workers_at
            ]
        ),
        StaticConnectorPool(
            [("connector.records", FakeConnector())], locations={"connector.records": connector_at}
        ),
        StaticModelPool(
            [(f"model.{at}", ("drafting",), FakeModel(), None) for at in models_at],
            {f"model.{at}": Declared(location=at) for at in models_at},
        ),
    )
    return RegisterProcessVersionHandler(
        MemoryRepository(persistence, ProcessVersion),
        persistence,
        MemoryRepository(persistence, Process),
        ledger=ledger,
        clock=clock,
        residency=PoolBindings(pools, rule, hosts or {}),
    )


async def register(h: RegisterProcessVersionHandler, *steps: dict[str, Any]) -> ProcessVersion:
    return await h.execute(RegisterProcessVersion(bundle=bundle(*steps), tenant=TENANT))


async def test_a_step_bound_to_a_connector_outside_the_rule_does_not_register() -> None:
    with pytest.raises(InvalidProcess) as refused:
        await register(await handler(connector_at="elsewhere"), connector())
    (finding,) = refused.value.findings
    assert "step 'write'" in finding and "data of class 'personal'" in finding
    assert "the connector connector.records is at elsewhere" in finding
    assert "the residency rule permits (eu)" in finding
    version = await register(await handler(connector_at="eu"), connector())
    assert version.ref == "payroll@1"


async def test_a_step_bound_only_to_workers_outside_the_rule_does_not_register() -> None:
    with pytest.raises(InvalidProcess, match=r"the worker worker\.elsewhere is at elsewhere"):
        await register(await handler(workers_at=("elsewhere",)), worker())
    await register(await handler(workers_at=("elsewhere", "own")), worker())


async def test_a_step_bound_only_to_models_outside_the_rule_does_not_register() -> None:
    with pytest.raises(InvalidProcess, match=r"step 'draft'.*the model model\.elsewhere"):
        await register(await handler(models_at=("elsewhere",)), model())
    await register(await handler(models_at=("elsewhere", "eu")), model())


async def test_a_host_outside_the_rule_does_not_register() -> None:
    with pytest.raises(InvalidProcess, match=r"the host api\.example\.com is at elsewhere"):
        await register(await handler(workers_at=("eu",)), worker("api.example.com"))
    await register(
        await handler(workers_at=("eu",), hosts={"api.example.com": "eu"}),
        worker("api.example.com"),
    )


async def test_a_step_of_an_unrestricted_class_registers_wherever_its_adapters_are() -> None:
    for step in (connector(), worker("x.example"), model()):
        await register(await handler(personal="anywhere"), step)
    await register(await handler(), connector(data_class=None))
