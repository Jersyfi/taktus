"""A call on behalf of the person a run acts for (ADR-0264): it is served with that person's own
credential in place of the one the step names, and a person without one gets nothing from the
source — the call is never made with a wider credential of Taktus's own."""

from __future__ import annotations

from fakes import FakeConnector
from fakes.connector import READ, WRITE
from fakes.maturity import VERIFIED

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.components.run.application.service import RunEngine
from taktus.components.run.domain.model import RunState, StepState
from taktus.composition.personal import ConfiguredPersonalCredentials

from .test_connector_steps import ConnectorHarness, call


class OnBehalf(ConnectorHarness):
    def __init__(self, mapping: dict[tuple[str, str], str], operation: str = READ) -> None:
        step, work = call("read", operation, {"id": "doc-1"})
        super().__init__((step, {**work, "on_behalf": True}))
        self.connector = FakeConnector()
        self.connector.reads["doc-1"] = {"id": "doc-1"}
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.runs,
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=self.provenance,
            workers=self.engine._workers,
            clock=self.clock,
            ids=self.ids,
            telemetry=self.engine._telemetry,
            connectors=StaticConnectorPool([("connector.fake", self.connector)]),
            options=self.engine._options,
            personal=ConfiguredPersonalCredentials(mapping),
        )


async def test_a_call_on_behalf_is_served_with_the_persons_own_credential() -> None:
    h = OnBehalf({("idn_t", "FAKE_TOKEN"): "FAKE_TOKEN_ADA"})
    run = await h.start()
    assert run.state is RunState.FINISHED
    context = h.connector.calls[0][1]
    assert [c.name for c in context.credentials] == ["FAKE_TOKEN_ADA"]


async def test_a_person_without_an_own_credential_gets_nothing_and_no_call_is_made() -> None:
    h = OnBehalf({("someone-else", "FAKE_TOKEN"): "FAKE_TOKEN_BOB"})
    run = await h.start()
    read = run.step_run("read")
    assert read.state is StepState.FAILED
    assert "idn_t has no credential of its own" in (read.reason or "")
    assert h.connector.calls == []


async def test_an_outward_act_on_behalf_of_a_person_is_refused_before_any_call() -> None:
    """ADR-0332: nothing is written or sent in a person's name, even where the person has a
    credential of their own; Taktus acts outward as an identity of its own (ADR-0033)."""
    h = OnBehalf({("idn_t", "FAKE_TOKEN"): "FAKE_TOKEN_ADA"}, WRITE)
    run = await h.start()
    step = run.step_run("read")
    assert step.state is StepState.FAILED
    assert "nothing is sent or written in a person's name" in (step.reason or "")
    assert h.connector.calls == []
    assert h.connector.records == {}
