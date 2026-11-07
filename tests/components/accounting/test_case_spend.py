"""What a process spends per case, and a process that reads it through the loopback connector
(ADR-0216, UC-03 B-2.02).

A version names the input that is its run's case; the runs of the process are grouped by that
input's value, each priced at its own table, the costliest case first. A run that names no case
is counted beside the cases, never in one.
"""

from __future__ import annotations

from typing import Any

import pytest
from fakes.takeover import instructed

from taktus.adapters.driven.connectors.loopback import SPEND_CASES, LoopbackConnector
from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.accounting.application.service import SpendHandler, SpendOfCases
from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.process.domain.model import InvalidProcess, ProcessVersion
from taktus.composition.case_spend import InstanceSpend
from taktus.ports.connector import CallContext, CallFailed
from taktus.ports.worker import Limits

from ..run.test_estimates import ISSUE, priced
from ..run.test_llm_steps import WORK, ModelHarness, llm

BUDGET = Limits(currency={"usd": 1.0})


def harness() -> ModelHarness:
    return priced(ModelHarness(ISSUE, llm("refine", WORK, after=("issue",))))


def version(case: str | None) -> dict[str, Any]:
    bundle: dict[str, Any] = {
        "id": "p",
        "version": "1",
        "name": "P",
        "autonomy": {"level": 2, "reason": "r", "toward_next": "t"},
        "inputs": {"message": {"description": "the message", "example": "m"}},
        "steps": [
            {
                "id": "issue",
                "method": "rule",
                "reason": "r",
                "rejected": [],
                "exactness": "tolerant",
                "work": {"rule": "constant", "value": 1},
            }
        ],
    }
    if case is not None:
        bundle["case"] = case
    return instructed(bundle)


async def test_the_runs_of_a_process_are_grouped_by_case_the_costliest_first() -> None:
    h = harness()
    one, two, three = [await h.start(BUDGET) for _ in range(3)]
    handler = SpendHandler(h.ledger, h.objects, h.persistence)
    process = one.process_version.partition("@")[0]
    found = await handler.of_cases(
        SpendOfCases(process, "t", cases={one.id: "msg-a", two.id: "msg-a"})
    )
    assert found.runs == 3 and found.without_case == 1, "a run without a case is in no case"
    (case,) = found.cases
    assert case.case == "msg-a" and case.runs == 2
    single = await handler.of_cases(SpendOfCases(process, "t", cases={three.id: "msg-b"}))
    assert single.cases[0].amount is not None and single.cases[0].amount > 0
    assert case.amount == pytest.approx(2 * single.cases[0].amount), "each run at its own table"
    assert case.amounts == {"usd": case.amount}


async def test_the_case_of_a_run_is_the_input_its_version_names() -> None:
    h = harness()
    runs = [await h.start(BUDGET) for _ in range(3)]
    for run, message in zip(runs, ("m1", "m1", None), strict=True):
        async with h.persistence.transaction("t"):
            inputs = {} if message is None else {"message": message}
            await h.runs.put("t", run.model_copy(update={"inputs": inputs}))
    versions = MemoryRepository(h.persistence, ProcessVersion)
    async with h.persistence.transaction("t"):
        await versions.put("t", parse_bundle(version("message")))
    spend = InstanceSpend(
        SpendHandler(h.ledger, h.objects, h.persistence), versions, h.runs, h.persistence, h.clock
    )
    assert await spend.of_runs("t", "p") == {runs[0].id: "m1", runs[1].id: "m1"}

    loopback = LoopbackConnector(spend=spend)
    context = CallContext(
        tenant="t",
        identity="idn_t",
        run_id="run_x",
        step_id="read",
        attempt=1,
        idempotency_key="taktus:run_x:read:1",
        credentials=(),
    )
    answered = await loopback.call(SPEND_CASES, context, {"process": "p", "days": 30})
    assert answered.output["days"] == 30
    assert [(c["case"], c["runs"]) for c in answered.output["cases"]] == [("m1", 2)]
    assert answered.output["without_case"] == 1
    with pytest.raises(CallFailed):
        await loopback.call(SPEND_CASES, context, {"process": "p", "days": 0})


def test_a_case_names_an_input_the_version_declares() -> None:
    with pytest.raises(InvalidProcess, match="case is named by the input 'thread'"):
        parse_bundle(version("thread"))
