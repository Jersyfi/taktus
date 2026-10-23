"""A step sees only the data of its case, and an analysis step never speaks outward (UC-7.7,
ADR-0130).

A scoped step names its subject from the run's inputs; every connector call of it carries the
scope, and a connector serving a scoped capability refuses another subject's data — the
refusal is recorded as `frame.refused`. An analytic step reaches its source only, through reads,
and only a source the tenant declares free of personal fields. A step that reads personal data
outside a specific case waits for a person, at every level.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest
from fakes.maturity import VERIFIED

from components.run.test_engine import BUDGET, TENANT, rule
from components.run.test_replay import Requests
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import RunState, StepState, UnsupportedWork
from taktus.ports.connector import (
    CallContext,
    CallFailed,
    Capabilities,
    Effect,
    EffectReport,
    Error,
    Record,
    Result,
)
from taktus.shared.v1 import Consumption, ExactnessClass, Method, Step

from .test_connector_steps import ConnectorHarness

ACCOUNT = "customers.accounts.read"
NOTE = "customers.accounts.note"
COHORTS = "analytics.cohorts.read"
PUBLISH = "analytics.cohorts.publish"
MAIL = "channel.mail.send"
CUSTOMERS = {
    "cust-1": {"id": "cust-1", "plan": "team"},
    "cust-2": {"id": "cust-2", "plan": "enterprise"},
}


def _op(name: str, effect: str = "read") -> dict[str, Any]:
    operation: dict[str, Any] = {
        "name": name,
        "capability": name.rsplit(".", 1)[0],
        "effect": effect,
        "demand": {"quota_units": 1},
        "summary": name,
    }
    if effect != "read":
        operation["idempotency"] = "marked"
    return operation


@dataclass
class CustomerConnector:
    """A connector of a customer system: `customers.accounts` is declared scoped and honours a
    call's scope; `analytics.cohorts` is a copy without personal fields; `channel.mail` sends."""

    scoped: bool = True
    calls: list[tuple[str, CallContext, dict[str, Any]]] = field(default_factory=list)

    async def capabilities(self) -> Capabilities:
        return Capabilities.model_validate(
            {
                "contract": "connector/v1",
                "version": "1.0.0",
                "capabilities": ["customers.accounts", "analytics.cohorts", "channel.mail"],
                "operations": [
                    _op(ACCOUNT),
                    _op(NOTE, "write"),
                    _op(COHORTS),
                    _op(PUBLISH, "delivery"),
                    _op(MAIL, "delivery"),
                ],
                "credentials": [{"name": "FAKE_TOKEN", "purpose": "actions"}],
                "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 60},
                "permissions": "passthrough",
                **({"scoped": ["customers.accounts"]} if self.scoped else {}),
            }
        )

    async def call(self, operation: str, context: CallContext, input: Mapping[str, Any]) -> Result:
        self.calls.append((operation, context, dict(input)))
        if operation == ACCOUNT:
            account = str(input.get("account"))
            if self.scoped and context.scope is not None and account != context.scope.subject:
                raise CallFailed(
                    operation,
                    Error.model_validate(
                        {
                            "class": "failure",
                            "cause": "out_of_scope",
                            "effect": "none",
                            "retryable": False,
                            "detail": "the account is not the case's subject",
                        }
                    ),
                )
            return _read(CUSTOMERS[account])
        if operation == COHORTS:
            return _read({"cohort": "2026-09", "retained": 0.81})
        return Result(
            output={"sent": True},
            effect=EffectReport(
                kind=Effect.DELIVERY,
                replayed=False,
                records=(Record(kind="message", id="m1"),),
            ),
            consumption=Consumption(quota_units=1),
        )


def _read(output: dict[str, Any]) -> Result:
    return Result(
        output=output, effect=EffectReport(kind=Effect.READ), consumption=Consumption(quota_units=1)
    )


class Declared:
    """What the tenant declares about its sources, as the run's port reads it."""

    def __init__(self, free: set[str] | None = None, personal: set[str] | None = None) -> None:
        self._free = frozenset(free or ())
        self._personal = frozenset(personal or ())

    async def free_of_personal_fields(self, tenant: str, capability: str) -> bool:
        return capability in self._free

    async def personal(self, tenant: str, capability: str) -> bool:
        return capability in self._personal


def step(
    id: str, operation: str, input: dict[str, Any], *, after: tuple[str, ...] = (), **frame: Any
) -> tuple[Step, dict[str, Any]]:
    definition = Step(
        id=id,
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.SOURCED,
        depends_on=after or None,
    )
    work = {
        "rule": "connector",
        "operation": operation,
        "input": input,
        "credentials": [{"name": "FAKE_TOKEN", "injected_as": "env"}],
        **frame,
    }
    return definition, work


SCOPE = {"subject": {"$input": "customer"}}


class Scoped(ConnectorHarness):
    def __init__(
        self,
        *definitions: tuple[Step, dict[str, Any]],
        connector: CustomerConnector | None = None,
        sources: Declared | None = None,
        level: int = 3,
    ) -> None:
        super().__init__(*definitions)
        self.customers = connector or CustomerConnector()
        self.requests = Requests()
        self.level = level
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
            connectors=StaticConnectorPool([("connector.customers", self.customers)]),
            options=self.engine._options,
            decisions=self.requests,
            sources=sources or Declared(),
        )

    async def begin(self, **inputs: Any) -> Any:
        plan = self.plan().model_copy(update={"autonomy_level": self.level})
        return await self.engine.start(
            StartRun(
                plan=plan,
                work=self.work,
                budget=BUDGET,
                process_version="p@1",
                actor="idn_t",
                tenant=TENANT,
                inputs=inputs,
            )
        )


# --- a step serves a case ------------------------------------------------------------------------


async def test_every_call_of_a_scoped_step_carries_its_subject_and_the_record_names_it() -> None:
    h = Scoped(step("account", ACCOUNT, {"account": {"$input": "customer"}}, scope=SCOPE))
    run = await h.begin(customer="cust-1")
    assert run.state is RunState.FINISHED, run.reason
    ((_, context, _),) = h.customers.calls
    assert context.scope is not None and context.scope.subject == "cust-1"
    (record,) = await h.records(run.id)
    assert record.scope is not None and record.scope.subject == "cust-1"


async def test_a_scoped_step_asking_for_a_second_customer_is_refused_and_it_is_recorded() -> None:
    # The second customer's account is what an earlier step produced — as a confused or
    # manipulated model would name it — and the scope is the case's, from the intake.
    h = Scoped(
        rule("guess", {"rule": "constant", "value": {"output": {"other": "cust-2"}}}),
        step(
            "account",
            ACCOUNT,
            {"account": {"$from": "guess", "$select": "output.other"}},
            after=("guess",),
            scope=SCOPE,
        ),
    )
    run = await h.begin(customer="cust-1")
    assert run.state is RunState.ESCALATED, run.reason
    account = run.step_run("account")
    assert account.state is StepState.FAILED and account.retryable is False
    assert "out of the case's scope" in (account.reason or "")
    kinds = await h.kinds(run)
    assert "frame.refused:account:out_of_scope" in kinds
    (call,) = h.customers.calls
    assert call[1].scope is not None and call[1].scope.subject == "cust-1"
    assert call[2] == {"account": "cust-2"}


async def test_a_subject_taken_from_a_step_s_output_is_refused_before_the_run_starts() -> None:
    for subject in (
        {"$from": "guess"},
        {"$input": "customer", "$otherwise": "cust-2"},
        {"$run": "id"},
        "cust-1",
    ):
        h = Scoped(step("account", ACCOUNT, {"account": "cust-1"}, scope={"subject": subject}))
        with pytest.raises(UnsupportedWork, match="one of the run's inputs"):
            await h.begin(customer="cust-1")
        assert h.customers.calls == []


async def test_a_scoped_call_to_personal_data_whose_connector_honours_no_scope_is_refused() -> None:
    h = Scoped(
        step("account", ACCOUNT, {"account": {"$input": "customer"}}, scope=SCOPE),
        connector=CustomerConnector(scoped=False),
        sources=Declared(personal={"customers.accounts"}),
    )
    run = await h.begin(customer="cust-1")
    assert run.state is RunState.ESCALATED
    assert h.customers.calls == [], "nothing was asked of a connector that would not scope it"
    assert "frame.refused:account:scope_not_honoured" in await h.kinds(run)


async def test_a_scoped_call_to_a_capability_that_serves_no_personal_data_carries_the_scope() -> (
    None
):
    h = Scoped(step("reply", MAIL, {"to": "x"}, scope=SCOPE))
    run = await h.begin(customer="cust-1")
    assert run.state is RunState.FINISHED, run.reason
    ((_, context, _),) = h.customers.calls
    assert context.scope is not None and context.scope.subject == "cust-1"


# --- personal data outside a specific case ------------------------------------------------------


@pytest.mark.parametrize("declared_by", ["connector", "tenant"])
async def test_reading_personal_data_outside_a_case_halts_a_level_4_process(
    declared_by: str,
) -> None:
    h = Scoped(
        step("export", ACCOUNT, {"account": "cust-2"}),
        connector=CustomerConnector(scoped=declared_by == "connector"),
        sources=Declared(personal={"customers.accounts"} if declared_by == "tenant" else set()),
        level=4,
    )
    run = await h.begin()
    assert run.state is RunState.WAITING_HUMAN, run.reason
    assert run.step_run("export").state is StepState.WAITING_HUMAN
    assert h.customers.calls == [], "nothing was read before a person decided"
    (draft,) = h.requests.raised
    assert draft.anchor == "anc-personal-data" and draft.class_ == "legal"
    assert "step.anchored:export:legal" in await h.kinds(run)


async def test_a_step_without_a_scope_on_data_that_is_not_personal_needs_no_person() -> None:
    h = Scoped(step("cohorts", COHORTS, {}), level=4)
    run = await h.begin()
    assert run.state is RunState.FINISHED, run.reason
    assert h.requests.raised == []


# --- an analytic step ----------------------------------------------------------------------------


FREE = Declared(free={"analytics.cohorts"})
ANALYTIC = {"source": "analytics.cohorts"}


async def test_an_analytic_step_reads_a_source_the_tenant_declares_free() -> None:
    h = Scoped(step("cohorts", COHORTS, {}, analytic=ANALYTIC), sources=FREE)
    run = await h.begin()
    assert run.state is RunState.FINISHED, run.reason
    ((_, context, _),) = h.customers.calls
    assert context.scope is None


async def test_an_analytic_step_on_a_source_not_declared_free_is_refused() -> None:
    h = Scoped(step("cohorts", COHORTS, {}, analytic=ANALYTIC))
    run = await h.begin()
    assert run.state is RunState.ESCALATED
    assert h.customers.calls == []
    assert "frame.refused:cohorts:not_declared_free" in await h.kinds(run)


async def test_an_analytic_step_never_speaks_outward_even_through_its_source() -> None:
    h = Scoped(step("publish", PUBLISH, {}, analytic=ANALYTIC), sources=FREE)
    run = await h.begin()
    assert run.state is RunState.ESCALATED
    assert h.customers.calls == []
    assert "frame.refused:publish:outward" in await h.kinds(run)
    assert not [k for k in await h.kinds(run) if k.startswith("egress.")]


async def test_an_analytic_step_on_a_source_that_serves_personal_data_is_refused() -> None:
    h = Scoped(
        step("accounts", ACCOUNT, {"account": "cust-1"}, analytic={"source": "customers.accounts"}),
        sources=Declared(free={"customers.accounts"}),
    )
    run = await h.begin()
    assert run.state is RunState.ESCALATED
    assert h.customers.calls == []
    assert "frame.refused:accounts:personal_source" in await h.kinds(run)


async def test_an_analytic_step_given_a_mail_capability_is_refused_before_the_run_starts() -> None:
    h = Scoped(step("tell", MAIL, {"to": "x"}, analytic=ANALYTIC), sources=FREE)
    with pytest.raises(UnsupportedWork, match="reaches its source only"):
        await h.begin()
    assert h.customers.calls == []


async def test_an_analytic_step_reads_only_what_analytic_steps_produced() -> None:
    h = Scoped(
        step("account", ACCOUNT, {"account": {"$input": "customer"}}, scope=SCOPE),
        step(
            "cohorts",
            COHORTS,
            {"of": {"$from": "account"}},
            after=("account",),
            analytic=ANALYTIC,
        ),
        sources=FREE,
    )
    with pytest.raises(UnsupportedWork, match="account is not analytic"):
        await h.begin(customer="cust-1")
