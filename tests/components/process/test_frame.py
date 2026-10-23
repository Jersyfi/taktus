"""Registration holds a step's frame (UC-7.7 §2, ADR-0130): a scope names its subject from the
run's inputs, and an analytic step reaches its source only — given a mail capability, the
process is refused at registration — and reads only a source the tenant declares free of
personal fields."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fakes import FakeClock

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
    parse_bundle,
)
from taktus.components.process.domain.model import InvalidProcess, Process, ProcessVersion

TENANT = "t"


class Free:
    def __init__(self, *free: str) -> None:
        self._free = set(free)

    async def free_of_personal_fields(self, tenant: str, capability: str) -> bool:
        return capability in self._free


def handler(*free: str) -> RegisterProcessVersionHandler:
    clock = FakeClock(datetime(2026, 10, 23, 9, 0, tzinfo=UTC))
    persistence = MemoryPersistence()
    return RegisterProcessVersionHandler(
        MemoryRepository(persistence, ProcessVersion),
        persistence,
        MemoryRepository(persistence, Process),
        ledger=ChainedLedger(MemoryLedgerStore(persistence), clock),
        clock=clock,
        sources=Free(*free),
    )


def connector(id: str, operation: str, **frame: Any) -> dict[str, Any]:
    return {
        "id": id,
        "method": "rule",
        "reason": "r",
        "rejected": [],
        "exactness": "sourced",
        "work": {"rule": "connector", "operation": operation, "input": {}, **frame},
    }


def bundle(*steps: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "framed",
        "version": "1",
        "name": "framed",
        "autonomy": {"level": 3, "reason": "a test", "toward_next": "nothing"},
        "inputs": {"customer": {"description": "the case's customer", "example": "cust-1"}},
        "steps": list(steps),
    }


ANALYTIC = {"source": "analytics.cohorts"}


async def test_an_analytic_step_given_a_mail_capability_is_refused_at_registration() -> None:
    with pytest.raises(InvalidProcess, match=r"channel\.mail\.send is outside it"):
        await handler("analytics.cohorts").execute(
            RegisterProcessVersion(
                bundle=bundle(connector("tell", "channel.mail.send", analytic=ANALYTIC)),
                tenant=TENANT,
            )
        )


async def test_an_analytic_step_on_a_source_the_tenant_does_not_declare_free_is_refused() -> None:
    given = bundle(connector("cohorts", "analytics.cohorts.read", analytic=ANALYTIC))
    with pytest.raises(InvalidProcess, match=r"does not declare analytics\.cohorts so"):
        await handler().execute(RegisterProcessVersion(bundle=given, tenant=TENANT))
    version = await handler("analytics.cohorts").execute(
        RegisterProcessVersion(bundle=given, tenant=TENANT)
    )
    assert version.ref == "framed@1"


@pytest.mark.parametrize(
    ("frame", "why"),
    [
        ({"scope": {"subject": {"$from": "other"}}}, "one of the run's inputs"),
        ({"scope": {"subject": {"$input": "customer", "$otherwise": "x"}}}, "never a step"),
        ({"scope": {"subject": {"$input": "nobody"}}}, "does not declare"),
        ({"scope": {"subject": "cust-1"}}, "one of the run's inputs"),
        ({"scope": {"subject": {"$input": "customer"}}, "analytic": ANALYTIC}, "never both"),
        ({"analytic": {"source": "Mail"}}, "is a capability"),
        ({"analytic": "yes"}, "names its source"),
    ],
)
def test_a_frame_that_cannot_hold_is_refused(frame: dict[str, Any], why: str) -> None:
    with pytest.raises(InvalidProcess, match=why):
        parse_bundle(bundle(connector("read", "customers.accounts.read", **frame)))


def test_an_analytic_step_reads_only_what_analytic_steps_produced() -> None:
    reading = connector("account", "customers.accounts.read")
    analysing = connector("cohorts", "analytics.cohorts.read", analytic=ANALYTIC)
    analysing["depends_on"] = ["account"]
    analysing["work"]["input"] = {"of": {"$from": "account"}}
    with pytest.raises(InvalidProcess, match="account is not analytic"):
        parse_bundle(bundle(reading, analysing))


def test_an_analytic_or_scoped_worker_step_reaches_no_host() -> None:
    worker = {
        "id": "w",
        "method": "worker",
        "reason": "r",
        "rejected": [],
        "exactness": "tolerant",
        "fallback": {"when": "x", "to": "human"},
        "requires": ["shell.script"],
        "work": {
            "task": {"goal": "g", "acceptance": ["a"]},
            "allowed_hosts": ["example.org"],
            "analytic": True,
        },
    }
    with pytest.raises(InvalidProcess, match="reaches no host"):
        parse_bundle(bundle(worker))
    worker["work"] = {
        "task": {"goal": "g", "acceptance": ["a"]},
        "allowed_hosts": ["example.org"],
        "scope": {"subject": {"$input": "customer"}},
    }
    with pytest.raises(InvalidProcess, match="cannot scope"):
        parse_bundle(bundle(worker))


def test_a_scoped_step_and_an_analytic_step_that_hold_register() -> None:
    analysing = connector("cohorts", "analytics.cohorts.read", analytic=ANALYTIC)
    analysing["depends_on"] = ["account"]
    version = parse_bundle(
        bundle(
            connector(
                "account",
                "customers.accounts.read",
                scope={"subject": {"$input": "customer", "$select": "id"}},
            ),
            analysing,
        )
    )
    assert [step.id for step in version.steps] == ["account", "cohorts"]
