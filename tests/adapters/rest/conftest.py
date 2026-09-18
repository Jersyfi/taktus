"""The HTTP surface over memory adapters and a scripted connector, driven in-process."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from fakes import FakeClock

from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryPersistence,
    MemoryRepository,
)
from taktus.adapters.driving.rest import build_app
from taktus.components.command.application.service import (
    CompleteIntakeHandler,
    ReceiveIntakeHandler,
)
from taktus.components.command.domain.model import IntakeEvent
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.run.domain.model import Run
from taktus.ports.connector import (
    ConnectorError,
    Delivery,
    Intake,
    IntakeConnector,
    IntakeResult,
    Refusal,
)
from taktus.ports.ledger import Fact
from taktus.ports.persistence import Repository, UnitOfWork
from taktus.ports.worker import ComputeLimit, Limits
from taktus.shared.v1 import ExactnessClass, LedgerRefs, Method, Step

TENANT = "default"


@dataclass
class ScriptedConnector(IntakeConnector):
    """Answers what it is told to; records what it was handed."""

    answer: IntakeResult | Exception
    deliveries: list[Delivery] = field(default_factory=list)

    async def intake(self, delivery: Delivery) -> IntakeResult:
        self.deliveries.append(delivery)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


ACCEPTED = IntakeResult(
    accepted=Intake.model_validate(
        {
            "event_id": "dlv_1",
            "event": "issue_comment.created",
            "channel": "channel.repo",
            "sender": {"account": "100200", "kind": "person"},
            "intent": {"raw": "@taktus turn this into a pull request"},
            "context": {"repository": "acme/taktus", "issue": "412"},
            "reply_to": {"channel": "channel.repo", "address": "acme/taktus#412", "thread": "9"},
            "occurred_at": "2026-09-16T08:15:00Z",
        }
    )
)


def refused(reason: str, detail: str = "as scripted") -> IntakeResult:
    return IntakeResult(refused=Refusal.model_validate({"reason": reason, "detail": detail}))


@dataclass
class Services:
    persistence: MemoryPersistence
    runs: Repository[Run]
    ledger: ChainedLedger
    events: Repository[IntakeEvent]
    intake: ReceiveIntakeHandler
    connector: ScriptedConnector
    clock: FakeClock
    complete_intake: CompleteIntakeHandler | None = None
    tenants: Sequence[str] = (TENANT,)
    roles: Sequence[str] = ("api", "runner")
    leading: bool = False
    not_ready_reason: str | None = None

    @property
    def work(self) -> UnitOfWork:
        return self.persistence

    async def ready(self) -> str | None:
        return self.not_ready_reason


def services(connector: ScriptedConnector | None = None) -> Services:
    persistence = MemoryPersistence()
    clock = FakeClock()
    scripted = connector or ScriptedConnector(ACCEPTED)
    events: Repository[IntakeEvent] = MemoryRepository(persistence, IntakeEvent)
    return Services(
        persistence=persistence,
        runs=MemoryRepository(persistence, Run),
        ledger=ChainedLedger(MemoryLedgerStore(persistence), clock),
        events=events,
        intake=ReceiveIntakeHandler({"channel.repo": scripted}, events, persistence),
        connector=scripted,
        clock=clock,
    )


async def a_run(given: Services, run_id: str = "run_1") -> Run:
    """One run stored with one ledger entry about it, as the engine would leave them."""
    clock = given.clock
    run = Run(
        id=run_id,
        plan_id="pln_1",
        process_version="p@1",
        tenant=TENANT,
        identity="idn_t",
        autonomy_level=2,
        budget=Limits(compute=ComputeLimit(seconds=10, resource_class="cpu.small")),
        steps=(
            Step(
                id="a",
                method=Method.RULE,
                reason="r",
                rejected=(),
                exactness=ExactnessClass.EXACT,
            ),
        ),
        work={"a": {"rule": "constant", "value": 1}},
        created_at=clock.now(),
        updated_at=clock.now(),
    )
    async with given.persistence.transaction(TENANT):
        await given.runs.put(TENANT, run)
        await given.ledger.record(
            TENANT,
            Fact(
                kind="run.created",
                refs=LedgerRefs(
                    tenant=TENANT, plan_id="pln_1", process_version="p@1", run_id=run_id
                ),
            ),
        )
    return run


@pytest.fixture(params=["/", "/taktus/instance-a"], ids=["root", "prefixed"])
def prefix(request: pytest.FixtureRequest) -> str:
    """Every test runs under the root and under a two-segment prefix."""
    chosen: str = request.param
    return chosen


@pytest.fixture
async def client(prefix: str) -> AsyncIterator[tuple[httpx.AsyncClient, Services, str]]:
    given = services()
    app = build_app(given, prefix=prefix)
    base = "" if prefix == "/" else prefix
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://taktus.test"
    ) as http:
        yield http, given, base


type Json = dict[str, Any]
__all__ = ["ConnectorError"]
