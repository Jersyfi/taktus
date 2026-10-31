"""A run addresses the wait at a person's step to the role the step names (UC-4.20, ADR-0167 §1).

A `human` step of the organisation is performed by a person of its role: the run waits for
them at every level, the block names the role, and the step ends with no result of Taktus's
once the person reports it performed. A fallback to a person is addressed to the fallback's
role. No record names the person behind a role until one answers.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from taktus.components.run.application.service import ConfirmSteps
from taktus.components.run.domain.model import Cause, RunError, RunState, StepState, block
from taktus.shared.v1 import Fallback, Method, Step

from .test_engine import TENANT, Harness, rule
from .test_ml_steps import after_it, bench, ml, source

PERSON = "idn_person"


def human(
    id: str = "approve",
    *,
    role: str | None = "finance-lead",
    task: str | None = "approve the payment run",
    after: tuple[str, ...] = ("prep",),
) -> tuple[Step, dict[str, Any]]:
    step = Step(
        id=id,
        method=Method.HUMAN,
        reason="a person approves what leaves the house",
        rejected=(),
        role=role,
        expertise=("payment terms",) if role is not None else None,
        depends_on=after or None,
    )
    return step, ({} if task is None else {"task": task})


def prep() -> tuple[Step, dict[str, Any]]:
    return rule("prep", {"rule": "constant", "value": 1})


def then() -> tuple[Step, dict[str, Any]]:
    return rule(
        "then",
        {"rule": "template", "text": "${v}", "values": {"v": {"$from": "approve"}}},
        after=("approve",),
    )


async def answer(h: Harness, run_id: str, step: str = "approve", **given: Any) -> Any:
    return await h.engine.confirm(
        ConfirmSteps(run_id=run_id, steps=(step,), actor=PERSON, tenant=TENANT, **given)
    )


async def test_a_human_step_waits_for_its_role_and_ends_once_performed() -> None:
    h = Harness(prep(), human(), then())
    run = await h.start()
    assert run.state is RunState.WAITING_HUMAN and run.cause is Cause.PERSON
    waiting = run.step_run("approve")
    assert waiting.state is StepState.WAITING_HUMAN
    assert waiting.block is not None
    assert (waiting.block.account, waiting.block.cause, waiting.block.role) == (
        "wait.human",
        block.AWAITING_ROLE,
        "finance-lead",
    )
    assert "the role finance-lead" in (waiting.reason or "")
    held = run.step_run("then")
    assert held.block is not None and held.block.cause == "held_back"

    awaiting = next(e for e in await h.entries(run) if e.kind == "step.awaiting")
    assert awaiting.outcome == block.AWAITING_ROLE and awaiting.content_digest is not None
    asked = json.loads(await h.objects.get(awaiting.content_digest) or b"{}")
    assert asked["role"] == "finance-lead" and asked["task"] == "approve the payment run"
    assert asked["expertise"] == ["payment terms"]
    assert PERSON not in json.dumps(asked), "the wait names the role, never a person"

    with pytest.raises(RunError, match="report it performed"):
        await answer(h, run.id)
    run = await answer(h, run.id, performed=True)
    assert run.state is RunState.FINISHED, run.reason
    done = run.step_run("approve")
    assert done.state is StepState.SUCCEEDED and done.confirmed_by == PERSON
    assert done.method is Method.HUMAN and "in the role finance-lead" in (done.reason or "")
    used = run.step_run("then")
    assert used.checkpoint is not None and used.checkpoint.result_digest is not None
    assert await h.objects.get(used.checkpoint.result_digest) == b'"null"', "nothing of Taktus's"
    assert "step.performed:approve" in await h.kinds(run)
    assert await h.verify()


async def test_a_human_step_naming_no_role_waits_addressed_to_no_role() -> None:
    """A tenant without a structure registers a human step without a role (UC-4.20 §2); its
    run waits as before, for whoever may answer it."""
    h = Harness(prep(), human(role=None, task=None))
    run = await h.start()
    waiting = run.step_run("approve")
    assert waiting.block is not None and waiting.block.role is None
    assert waiting.block.cause == block.AWAITING_ROLE
    awaiting = next(e for e in await h.entries(run) if e.kind == "step.awaiting")
    asked = json.loads(await h.objects.get(awaiting.content_digest or "") or b"{}")
    assert asked["task"] == "a person approves what leaves the house", "the reason says it"
    run = await answer(h, run.id, performed=True)
    assert run.state is RunState.FINISHED


async def test_a_human_step_rejected_halts_and_is_asked_again_on_resume() -> None:
    h = Harness(prep(), human())
    run = await h.start()
    with pytest.raises(RunError, match="nothing to correct"):
        await answer(h, run.id, corrected={"approve": {"task": "other"}})
    run = await answer(h, run.id, rejected=True)
    assert run.state is RunState.HALTED and run.cause is Cause.DECLINED
    assert run.step_run("approve").state is StepState.PLANNED
    run = await h.resume(run)
    again = run.step_run("approve")
    assert again.state is StepState.WAITING_HUMAN
    assert again.block is not None and again.block.role == "finance-lead"


async def test_a_fallback_to_a_person_is_addressed_to_the_fallbacks_role() -> None:
    step, work = ml()
    fallback = Fallback(when="confidence < 0.9", to=Method.HUMAN, role="controlling")
    named = (step.model_copy(update={"fallback": fallback}), work)
    h = Harness(source(), named, after_it(), workers=[bench(("k1", 0.97), ("k2", 0.71))])
    run = await h.start()
    waiting = run.step_run("classify")
    assert waiting.block is not None and waiting.block.cause == "fell_back"
    assert waiting.block.role == "controlling"
