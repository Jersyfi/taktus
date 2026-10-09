"""The run records every failed call that speaks about its interface (ADR-0047, issue #100).

A connector step whose call fails writes `interface.failed` beside its `step.finished` when the
cause is unforeseen — the connector broke its contract, the service refused the authentication or
answered as the connector does not foresee — or transient. A cause that is the service answering
about the input or the state writes nothing. The entry carries the adapter, the run, the step and
the cause token, and no consumption: the step's own entry counts what the call used.
"""

from __future__ import annotations

from typing import Any

import pytest
from fakes import FakeConnector, failure
from fakes.connector import READ, WRITE

from taktus.components.run.application.query import InterfaceFailures
from taktus.components.run.domain.model import RunState
from taktus.components.run.domain.service import interfaces
from taktus.ports.connector import Cause, ContractBroken

from .test_connector_steps import ConnectorHarness, call
from .test_engine import TENANT


async def failed_with(connector: FakeConnector, operation: str = READ) -> list[Any]:
    h = ConnectorHarness(call("step", operation, {"id": "x", "title": "t"}), connector=connector)
    run = await h.start()
    assert run.state is RunState.ESCALATED
    return [e for e in await h.entries(run) if e.kind == interfaces.RECORD_KIND]


@pytest.mark.parametrize(
    ("cause", "recorded"),
    [
        ("unauthenticated", "unauthenticated"),
        ("unexpected", "unexpected"),
        ("unavailable", "unavailable"),
        ("unknown", "unknown"),
        ("forbidden", None),
        ("not_found", None),
        ("invalid", None),
        ("conflict", None),
    ],
)
async def test_a_classified_failure_is_recorded_by_its_cause(
    cause: str, recorded: str | None
) -> None:
    connector = FakeConnector()
    effect = "unknown" if cause == "unknown" else "none"
    connector.fail_next[READ] = failure(cause, effect=effect, retryable=cause == "unavailable")
    entries = await failed_with(connector)
    if recorded is None:
        assert entries == []
        return
    (entry,) = entries
    assert entry.outcome == recorded
    assert entry.adapter == "connector.fake"
    assert entry.refs.step_id == "step" and entry.consumption is None


def test_every_cause_of_the_contract_is_read_by_the_rule() -> None:
    for cause in Cause:
        token = interfaces.of_cause(cause)
        assert token is None or token in interfaces.UNFORESEEN | interfaces.TRANSIENT


async def test_a_connector_that_breaks_its_contract_or_is_down_is_recorded() -> None:
    class Unclassified(FakeConnector):
        async def call(self, operation: str, context: Any, input: Any) -> Any:
            raise ContractBroken("the connector answered with an error that is not classified")

    (broke,) = await failed_with(Unclassified())
    assert broke.outcome == interfaces.CONTRACT

    class Lying(FakeConnector):
        async def call(self, operation: str, context: Any, input: Any) -> Any:
            result = await super().call(operation, context, input)
            return result.model_copy(
                update={"effect": result.effect.model_copy(update={"kind": "read"})}
            )

    (lied,) = await failed_with(Lying(), WRITE)
    assert lied.outcome == interfaces.CONTRACT

    down = FakeConnector()
    down.unreachable = "the connector at fake did not answer"
    (unreachable,) = await failed_with(down)
    assert unreachable.outcome == interfaces.UNREACHABLE


async def test_the_query_reads_every_recorded_failure() -> None:
    connector = FakeConnector()
    connector.fail_next[READ] = failure("unexpected")
    h = ConnectorHarness(call("step", READ, {"id": "x"}), connector=connector)
    run = await h.start()
    (found,) = await InterfaceFailures(h.ledger, h.persistence).failures(TENANT)
    assert (found.adapter, found.cause, found.run_id, found.step_id) == (
        "connector.fake",
        "unexpected",
        run.id,
        "step",
    )
