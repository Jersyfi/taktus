"""Method maturation as the instance wires it (issue #229, ADR-0086): the handlers given the
instance's price table and its decision port, and reached through the loopback connector the
way S-06 reaches them.

The run history and the scripted bench are `tests/components/run/test_maturation.py`'s.
"""

from __future__ import annotations

from typing import Any

import pytest
from components.run.test_maturation import (
    PRICES,
    STARTER,
    TENANT,
    World,
    bench,
    candidate_world,
    separable,
)

from taktus.adapters.driven.connectors.loopback import (
    DECLARATION,
    MATURATION_MEASURES,
    MATURATION_PROPOSE,
    LoopbackConnector,
)
from taktus.components.run.application.service.maturation import NO_TABLE
from taktus.composition.maturation import InstanceMaturation, Maturation, maturation_wiring
from taktus.ports.connector import CallContext, CallFailed, Effect, idempotency_key
from taktus.ports.model import PriceTable

BUDGET = {"compute": {"seconds": 600, "resource_class": "cpu.small"}}


def wired(w: World, prices: PriceTable | None) -> Maturation:
    """Maturation as `composition/local.py` and `composition/daemon.py` build it."""
    return maturation_wiring(
        engine=w.engine,
        runs=w.runs,
        ledger=w.ledger,
        objects=w.objects,
        work=w.persistence,
        clock=w.clock,
        decisions=w.decisions.requests,
        prices=prices,
    )


def context(step: str) -> CallContext:
    return CallContext(
        tenant=TENANT,
        identity=STARTER,
        run_id="run_s06",
        step_id=step,
        attempt=1,
        idempotency_key=idempotency_key("run_s06", step, 1),
        credentials=(),
    )


async def call(loopback: LoopbackConnector, operation: str, input: dict[str, Any]) -> Any:
    step = operation.rsplit(".", 1)[-1]
    result = await loopback.call(operation, context(step), input)
    assert result.effect.kind is Effect.READ, "nothing leaves Taktus through the loopback"
    return result.output


def test_the_loopback_declares_maturation_as_two_reads() -> None:
    operations = {o.name: o for o in DECLARATION.operations}
    for name in (MATURATION_MEASURES, MATURATION_PROPOSE):
        assert operations[name].effect is Effect.READ and operations[name].demand is not None


async def test_s06_measures_and_has_a_candidate_proposed_through_the_decision_port() -> None:
    w = await candidate_world()
    loopback = LoopbackConnector(maturation=InstanceMaturation(wired(w, PRICES)))

    measured = await call(loopback, MATURATION_MEASURES, {})
    (classify,) = [s for s in measured["steps"] if s["step_id"] == "classify"]
    assert classify["cases"] == 540 and classify["currency"] == "eur"
    assert measured["count"] == len(measured["steps"]) and measured["unpriced"] == 0

    proposed = await call(loopback, MATURATION_PROPOSE, {"budget": BUDGET, "scope": {}})
    assert proposed["looked_at"] == 1 and proposed["proposed"] == 1 and proposed["applied"] == 0
    (outcome,) = proposed["outcomes"]
    assert outcome["proposed"] is True and outcome["applied"] is False
    (request,) = await w.proposals()
    assert request.id == outcome["request_id"] and request.decider == "owner"
    # The training and the trial act for the identity the scheduled run acts for.
    async with w.persistence.transaction(TENANT):
        entries = await w.ledger.entries(TENANT, outcome["training_run"])
    created = next(e for e in entries if e.kind == "run.created")
    assert created.refs.actor == STARTER


async def test_without_a_price_table_every_cost_is_unpriced_and_nothing_is_proposed() -> None:
    history = separable(540)
    w = World(workers=bench([kind for _, kind in history]), prices=None)
    await w.history(history)
    loopback = LoopbackConnector(maturation=InstanceMaturation(wired(w, None)))

    measured = await call(loopback, MATURATION_MEASURES, {})
    assert measured["unpriced"] == measured["count"] >= 1
    for step in measured["steps"]:
        if step["cases"]:
            assert step["unpriced"] == ["no price table is configured"]

    proposed = await call(loopback, MATURATION_PROPOSE, {"budget": BUDGET, "scope": {}})
    (outcome,) = proposed["outcomes"]
    assert proposed["proposed"] == 0 and outcome["findings"] == [NO_TABLE]
    assert "training_run" not in outcome, "nothing is trained when no cost can be compared"
    assert await w.proposals() == []


async def test_a_budget_that_is_no_limits_or_a_scope_it_does_not_know_is_refused() -> None:
    w = World()
    loopback = LoopbackConnector(maturation=InstanceMaturation(wired(w, PRICES)))
    with pytest.raises(CallFailed, match="at least one consumption kind"):
        await call(loopback, MATURATION_PROPOSE, {"budget": {}, "scope": {}})
    with pytest.raises(CallFailed, match="names a process version and a step"):
        await call(loopback, MATURATION_PROPOSE, {"budget": BUDGET, "scope": {"run": "x"}})
    with pytest.raises(CallFailed, match="runs no maturation"):
        await call(LoopbackConnector(), MATURATION_MEASURES, {})
