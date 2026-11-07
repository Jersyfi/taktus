"""The configuration a commissioned plan calls for, in the organisation's tools (ADR-0278,
UC-1.3): the undoing recorded before every change, an egress entry for every change, a halt on
any deviation with the options, a change whose undoing cannot be stated handed to a person, and
an unsafe change never sent twice."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fakes import FakeClock

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.command.application.service.configure import Configure
from taktus.components.command.domain.model.configuration import (
    ChangeState,
    ConfigurationChange,
)
from taktus.components.ledger.application.service import ChainedLedger
from taktus.ports.connector import (
    CallContext,
    Capabilities,
    Effect,
    EffectReport,
    Record,
    Result,
)
from taktus.ports.worker import CredentialReference
from taktus.shared.v1 import (
    Commissioned,
    Consumption,
    ExactnessClass,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    Step,
)

AT = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
T = "acme"
CAP = "tickets.projects"
KEY = (CredentialReference(name="TICKETS_ADA", injected_as="env"),)


@dataclass
class Tracker:
    """A ticket system's projects behind the action port: `create` is marked unless told
    otherwise; `delete` reverses it; `read` states what is there."""

    projects: dict[str, dict[str, Any]] = field(default_factory=dict)
    sent: list[tuple[str, str, tuple[str, ...]]] = field(default_factory=list)
    idempotency: str = "marked"
    operations: tuple[str, ...] = ("create", "delete", "read")
    answer: Mapping[str, Any] | None = None
    reports: tuple[str, ...] = ("project",)

    async def capabilities(self) -> Capabilities:
        base = {"capability": CAP, "demand": {"quota_units": 1}, "summary": "projects"}
        effects = {"create": "write", "delete": "write", "read": "read"}
        return Capabilities.model_validate(
            {
                "contract": "connector/v1",
                "capabilities": [CAP],
                "operations": [
                    {
                        **base,
                        "name": f"{CAP}.{op}",
                        "effect": effects[op],
                        **({} if effects[op] == "read" else {"idempotency": self.idempotency}),
                    }
                    for op in self.operations
                ],
                "credentials": [],
                "consumption": {"kinds": ["quota"], "unit": "calls", "window_seconds": 60},
                "permissions": "passthrough",
            }
        )

    async def call(self, operation: str, context: CallContext, input: Mapping[str, Any]) -> Result:
        self.sent.append((operation, context.identity, tuple(c.name for c in context.credentials)))
        name = str(input.get("key", ""))
        if operation.endswith(".read"):
            return Result(
                output={"exists": name in self.projects},
                effect=EffectReport(kind=Effect.READ),
                consumption=Consumption(quota_units=1),
            )
        self.projects[name] = dict(input)
        output = dict(self.answer) if self.answer is not None else {"key": name, "state": "open"}
        return Result(
            output=output,
            effect=EffectReport(
                kind=Effect.WRITE,
                replayed=False,
                records=tuple(Record(kind=k, id=name) for k in self.reports),
                content_digest="sha256:" + "a" * 64,
            ),
            consumption=Consumption(quota_units=1),
        )


@dataclass
class Targets:
    tracker: Tracker | None

    def connector(self, capability: str) -> Any:
        return self.tracker if capability == CAP else None


@dataclass
class Keys:
    held: dict[str, tuple[CredentialReference, ...]] = field(
        default_factory=lambda: {"idn_ada": KEY}
    )

    async def of(self, tenant: str, identity: str, capability: str) -> Any:
        return self.held.get(identity)


def change(**over: Any) -> dict[str, Any]:
    return {
        "capability": CAP,
        "action": {"operation": f"{CAP}.create", "input": {"key": "WEB"}},
        "read_before": {"operation": f"{CAP}.read", "input": {"key": "WEB"}},
        "reverse": {"operation": f"{CAP}.delete", "input": {"key": "WEB"}},
        "expects": {"state": "open"},
        "touches": ["project"],
        "instruction": "Create the project WEB in the ticket system.",
        **over,
    }


class World:
    def __init__(self, tracker: Tracker | None = None) -> None:
        self.persistence = MemoryPersistence()
        self.clock = FakeClock(AT)
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.plans = MemoryRepository(self.persistence, Plan)
        self.changes = MemoryRepository(self.persistence, ConfigurationChange)
        self.tracker = tracker if tracker is not None else Tracker()
        self.keys = Keys()
        self.configure = Configure(
            self.changes,
            self.plans,
            Targets(self.tracker),
            self.keys,
            self.ledger,
            self.persistence,
            self.clock,
        )

    async def plan(self, commissioned: bool = True) -> str:
        plan = Plan(
            id="pld_1@v1",
            command_id="cmd_1",
            goal="set up the web team's tools",
            autonomy_level=2,
            steps=(
                Step(
                    id="configure",
                    method=Method.RULE,
                    reason="the plan's changes, by rule",
                    rejected=(),
                    exactness=ExactnessClass.EXACT,
                ),
            ),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED if commissioned else PlanStatus.DRAFT,
            commissioned=Commissioned(by="idn_ada", at=AT) if commissioned else None,
        )
        async with self.persistence.transaction(T):
            await self.plans.put(T, plan)
        return plan.id

    async def entries(self) -> list[Any]:
        async with self.persistence.transaction(T):
            return list(await self.ledger.entries(T))


async def test_the_undoing_is_recorded_before_the_change_and_the_change_is_an_egress_entry() -> (
    None
):
    world = World()
    plan = await world.plan()
    await world.configure.prepare(T, plan, [change()])
    assert await world.configure.carry_out(T, plan) is None
    kinds = [e.kind for e in await world.entries()]
    assert kinds == ["configuration.undo_recorded", "egress.write"], "the undoing comes first"
    egress = (await world.entries())[1]
    assert egress.adapter == CAP and egress.refs.plan_id == plan and egress.content_digest
    (done,) = await world.configure.of_plan(T, plan)
    assert done.state is ChangeState.APPLIED
    assert done.undo is not None and done.undo.before == {"exists": False}
    assert done.undo.reverse is not None and done.undo.reverse.operation == f"{CAP}.delete"
    assert world.tracker.sent[-1] == (f"{CAP}.create", "idn_ada", ("TICKETS_ADA",)), (
        "made with the credential of the identity the plan was commissioned for"
    )


async def test_only_a_commissioned_plan_is_configured() -> None:
    world = World()
    plan = await world.plan(commissioned=False)
    try:
        await world.configure.prepare(T, plan, [change()])
    except Exception as error:
        assert "not commissioned" in str(error)
    else:
        raise AssertionError("a plan nobody commissioned was configured")


async def test_a_change_whose_undoing_cannot_be_stated_is_handed_to_a_person() -> None:
    world = World()
    plan = await world.plan()
    await world.configure.prepare(T, plan, [change(read_before=None, reverse=None)])
    halted = await world.configure.carry_out(T, plan)
    assert halted is not None and halted.state is ChangeState.HANDED
    assert "Create the project WEB" in halted.reason
    assert world.tracker.sent == [], "nothing was sent"


async def test_a_target_that_cannot_do_what_was_planned_halts_with_the_options() -> None:
    world = World(Tracker(operations=("read",)))
    plan = await world.plan()
    await world.configure.prepare(T, plan, [change(), change(instruction="second")])
    halted = await world.configure.carry_out(T, plan)
    assert halted is not None and halted.state is ChangeState.DEVIATED
    assert "cannot do" in halted.reason and len(halted.options) == 3
    _, second = await world.configure.of_plan(T, plan)
    assert second.state is ChangeState.PLANNED, "the configuration halted at the boundary"
    assert "configuration.deviated" in [e.kind for e in await world.entries()]


async def test_a_change_the_plan_does_not_name_or_another_result_is_a_deviation() -> None:
    world = World(Tracker(reports=("project", "webhook")))
    plan = await world.plan()
    await world.configure.prepare(T, plan, [change()])
    halted = await world.configure.carry_out(T, plan)
    assert halted is not None and "does not name: webhook" in halted.reason

    other = World(Tracker(answer={"key": "WEB", "state": "archived"}))
    plan = await other.plan()
    await other.configure.prepare(T, plan, [change()])
    halted = await other.configure.carry_out(T, plan)
    assert halted is not None and "otherwise than planned: state" in halted.reason
    again = await other.configure.carry_out(T, plan)
    assert again is not None and again.state is ChangeState.DEVIATED, "no substitute is chosen"


async def test_an_unsafe_change_is_never_sent_again_after_a_restart() -> None:
    world = World(Tracker(idempotency="none"))
    plan = await world.plan()
    (planned,) = await world.configure.prepare(T, plan, [change()])
    # A restart after the undoing was recorded and before the outcome was: the change may
    # have been sent.
    async with world.persistence.transaction(T):
        await world.changes.put(T, planned.model_copy(update={"state": ChangeState.UNDO_RECORDED}))
    halted = await world.configure.carry_out(T, plan)
    assert halted is not None and halted.state is ChangeState.HANDED
    assert "cannot recognise a repeat" in halted.reason
    assert [s[0] for s in world.tracker.sent] == [], "never sent twice"


async def test_an_identity_without_its_own_credential_hands_the_change_to_a_person() -> None:
    world = World()
    world.keys.held.clear()
    plan = await world.plan()
    await world.configure.prepare(T, plan, [change()])
    halted = await world.configure.carry_out(T, plan)
    assert halted is not None and halted.state is ChangeState.HANDED
    assert "holds no credential" in halted.reason
