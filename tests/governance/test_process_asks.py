"""A process holds a step itself: a step runs only when its `when` holds, and a step that asks
puts its act to a person first, at every level (ADR-0088, UC-1.9).

Each case runs a plan through the run engine with the governance, decision and identity
components wired as the composition root wires them — the world of `test_anchors.py` — and
reads back the run, the requests and the ledger.
"""

from __future__ import annotations

from typing import Any

from fakes.connector import READ, WRITE

from governance.test_anchors import (
    World,
    call,
    requests_of,
    rule,
    states,
)
from taktus.components.run.domain.model import Cause, RunState, StepState
from taktus.shared.v1 import ExactnessClass, Method, Step

ROLE = "finance.lead"


def constant(id: str, value: Any) -> tuple[Step, dict[str, Any]]:
    step, _ = rule(id)
    return step, {"rule": "constant", "value": value}


def when(
    definition: tuple[Step, dict[str, Any]], *conditions: dict[str, Any], after: str
) -> tuple[Step, dict[str, Any]]:
    step, work = definition
    depends = tuple(dict.fromkeys((*(step.depends_on or ()), after)))
    return step.model_copy(update={"depends_on": depends}), {**work, "when": list(conditions)}


def asking(
    definition: tuple[Step, dict[str, Any]], *, on_decline: str = "halt", **more: Any
) -> tuple[Step, dict[str, Any]]:
    step, work = definition
    ask = {"question": "Shall the record be written?", "role": ROLE, "on_decline": on_decline}
    return step, {**work, "ask": {**ask, **more}}


def written(w: World) -> list[str]:
    return [operation for operation, _, _ in w.connector.calls if operation == WRITE]


async def test_a_step_whose_condition_does_not_hold_is_skipped_and_performs_nothing() -> None:
    w = await World(
        constant("class", "spam"),
        when(
            call("write", WRITE), {"value": {"$from": "class"}, "equals": "feature"}, after="class"
        ),
        configuration=None,
    ).setup()
    run = await w.start()

    assert run.state is RunState.FINISHED
    assert states(run) == {"class": StepState.SUCCEEDED, "write": StepState.SUCCEEDED}
    assert written(w) == [], "a skipped step performs nothing"
    assert "write" not in {e.refs.step_id for e in await w.entries(run) if e.kind == "egress.write"}
    assert "step.finished:write:skipped" in await w.kinds(run)
    assert "condition 1 does not hold" in (run.step_run("write").reason or "")


async def test_a_step_whose_condition_holds_runs_as_any_step() -> None:
    w = await World(
        constant("class", "feature"),
        when(
            call("write", WRITE), {"value": {"$from": "class"}, "equals": "feature"}, after="class"
        ),
        configuration=None,
    ).setup()
    run = await w.start()

    assert run.state is RunState.FINISHED
    assert written(w) == [WRITE]
    assert "step.finished:write:succeeded" in await w.kinds(run)


async def test_a_skipped_step_s_result_says_so_to_the_steps_after_it() -> None:
    reader = Step(
        id="reader",
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.EXACT,
        depends_on=("write",),
    )
    w = await World(
        constant("class", "spam"),
        when(
            call("write", WRITE), {"value": {"$from": "class"}, "equals": "feature"}, after="class"
        ),
        (
            reader,
            {
                "rule": "check",
                "conditions": [{"value": {"$from": "write", "$select": "skipped"}, "equals": True}],
            },
        ),
        configuration=None,
    ).setup()
    run = await w.start()

    assert run.state is RunState.FINISHED, run.reason


async def test_a_step_that_asks_raises_its_own_request_without_any_anchor_naming_it() -> None:
    w = await World(
        constant("summary", "a new export format"),
        asking(
            when(
                call("write", WRITE),
                {"value": {"$from": "summary"}, "matches": "."},
                after="summary",
            ),
            question="Is ${summary} taken into 0.4.0?",
            values={"summary": {"$from": "summary"}},
        ),
        configuration=None,  # the shipped default anchors nothing of this step
    ).setup()
    run = await w.start()

    assert run.state is RunState.WAITING_HUMAN
    assert run.step_run("write").state is StepState.WAITING_HUMAN
    (request_id,) = requests_of(run, "write")
    request = await w.request(request_id)
    assert request.request.question == "Is a new export format taken into 0.4.0?"
    assert request.decider == ROLE
    assert "step.anchored:write:strategic" in await w.kinds(run)
    assert written(w) == []

    await w.answer(request_id, option="A")
    run = await w.confirm(request_id)
    assert run.state is RunState.FINISHED
    assert written(w) == [WRITE]


async def test_a_step_that_asks_is_asked_at_every_level() -> None:
    w = await World(asking(call("write", WRITE)), level=4, configuration=None).setup()
    run = await w.start()
    assert run.state is RunState.WAITING_HUMAN
    assert written(w) == []


async def test_a_declined_act_the_process_continues_after_becomes_the_result_it_acts_on() -> None:
    answer_step = Step(
        id="close",
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.SOURCED,
        depends_on=("accept",),
    )
    close_work = {
        "rule": "connector",
        "operation": WRITE,
        "input": {"id": "x", "reason": {"$from": "accept", "$select": "answer"}},
        "when": [{"value": {"$from": "accept", "$select": "declined"}, "equals": True}],
    }
    w = await World(
        asking(call("accept", WRITE), on_decline="continue"),
        (answer_step, close_work),
        configuration=None,
    ).setup()
    run = await w.start()
    (request_id,) = requests_of(run, "accept")

    await w.answer(request_id, text="B — it repeats what #3 asks for")
    run = await w.confirm(request_id)

    assert run.state is RunState.FINISHED, run.reason
    assert states(run) == {"accept": StepState.SUCCEEDED, "close": StepState.SUCCEEDED}
    (only,) = w.connector.calls
    operation, _, given = only
    assert operation == WRITE and given["reason"] == "B — it repeats what #3 asks for"
    kinds = await w.kinds(run)
    assert "step.finished:accept:declined" in kinds and "step.decided:accept:decline" in kinds


async def test_a_declined_act_halts_the_run_unless_the_process_continues_after_it() -> None:
    w = await World(asking(call("accept", WRITE)), configuration=None).setup()
    run = await w.start()
    (request_id,) = requests_of(run, "accept")
    await w.answer(request_id, option="B")
    run = await w.confirm(request_id)
    assert run.state is RunState.HALTED and run.cause is Cause.DECLINED
    assert w.connector.calls == []


async def test_an_approved_act_the_process_continues_after_skips_what_follows_a_decline() -> None:
    close = Step(
        id="close",
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.SOURCED,
        depends_on=("accept",),
    )
    w = await World(
        asking(call("accept", WRITE), on_decline="continue"),
        (
            close,
            {
                "rule": "connector",
                "operation": WRITE,
                "input": {"id": "y"},
                "when": [{"value": {"$from": "accept", "$select": "declined"}, "equals": True}],
            },
        ),
        configuration=None,
    ).setup()
    run = await w.start()
    (request_id,) = requests_of(run, "accept")
    await w.answer(request_id, option="A")
    run = await w.confirm(request_id)

    assert run.state is RunState.FINISHED
    assert [given["id"] for _, _, given in w.connector.calls] == ["x"]


async def test_a_rehearsal_is_asked_nothing() -> None:
    w = await World(asking(call("write", READ)), configuration=None).setup()
    run = await w.start(rehearsal=True)
    assert run.step_run("write").anchoring is None


async def test_a_question_naming_a_value_it_does_not_carry_is_not_raised_and_the_step_fails() -> (
    None
):
    w = await World(
        asking(call("write", WRITE), question="Is ${missing} right?"), configuration=None
    ).setup()
    run = await w.start()
    assert run.state is RunState.ESCALATED
    assert run.step_run("write").state is StepState.FAILED
    assert "cannot be put" in (run.step_run("write").reason or "")
    assert w.connector.calls == []


async def test_a_condition_that_names_no_dependency_is_refused_before_the_run_starts() -> None:
    w = await World(
        constant("class", "spam"),
        (
            call("write", WRITE)[0],
            {**call("write", WRITE)[1], "when": [{"value": {"$from": "class"}, "equals": "x"}]},
        ),
        configuration=None,
    ).setup()
    try:
        await w.start()
    except Exception as error:  # the engine refuses the run before anything runs
        assert "not a dependency" in str(error)
    else:
        raise AssertionError("a condition over a step that is no dependency was accepted")
    assert w.connector.calls == []
