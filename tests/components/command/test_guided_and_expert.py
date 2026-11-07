"""A guided and an expert mode reach the same plan (ADR-0238, UC-13.1).

One intent pursued both ways: in the expert mode every field is set at once, in the guided mode
the questions are answered one at a time. Both change the same kind of record, and their
commissioned plans are equal but for the identifiers.
"""

from __future__ import annotations

import inspect
from datetime import timedelta
from typing import Any

from components.command.test_plan_dialogue import AT, STEP_A, STEP_B, TENANT, Dialogue
from taktus.components.command.application.service import (
    CommissionDraft,
    OpenDraft,
    PlanDialogue,
    ReviseDraft,
)
from taktus.components.command.domain.model import Estimate, PlanDraft
from taktus.components.command.domain.service.guided import (
    SAFE_LEVELS,
    TERMS,
    next_question,
    settings,
)
from taktus.shared.v1 import Plan

ANSWERS: dict[str, Any] = {
    "goal": "answer supplier invoices",
    "steps": [STEP_A, STEP_B],
    "due": AT + timedelta(days=1),
    "autonomy_level": 2,
    "autonomy_reason": "a person confirms every reply until the drafts are trusted",
}
ESTIMATES = {
    "a": Estimate(step_id="a", figure=0.2, basis="the rule's last 30 runs"),
    "b": Estimate(step_id="b", figure=40, basis="the worker's own estimate"),
}


async def guided(d: Dialogue, by: str = "idn_p") -> tuple[PlanDraft, list[str]]:
    """Answer the guided mode's questions until it asks none; the fields asked, in order."""
    draft = await d.dialogue.open(OpenDraft(command=d.command, tenant=TENANT))
    asked: list[str] = []
    while (question := next_question(draft)) is not None:
        asked.append(question.field if question.step_id is None else f"estimate {question.step_id}")
        if question.field == "estimates":
            assert question.step_id is not None
            change: Any = (*draft.estimates, ESTIMATES[question.step_id])
        else:
            change = ANSWERS[question.field]
        draft = await d.dialogue.revise(
            ReviseDraft(draft.id, TENANT, by=by, changes={question.field: change})
        )
    return draft, asked


def same(plan: Plan) -> dict[str, Any]:
    """The plan but for its identifiers and the moment it was commissioned."""
    assert plan.commissioned is not None
    return {
        **plan.model_dump(exclude={"id", "command_id", "commissioned"}),
        "by": plan.commissioned.by,
    }


async def test_one_intent_pursued_in_either_mode_reaches_the_same_plan() -> None:
    d = Dialogue()
    expert = await d.dialogue.open(
        OpenDraft(
            command=d.command,
            tenant=TENANT,
            estimates=tuple(ESTIMATES.values()),
            **ANSWERS,
        )
    )
    walked, asked = await guided(d)
    assert asked == [
        "goal",
        "steps",
        "due",
        "autonomy_level",
        "autonomy_reason",
        "estimate a",
        "estimate b",
    ]
    fields = {"goal", "steps", "due", "autonomy_level", "autonomy_reason", "estimates"}
    assert walked.model_dump(include=fields) == expert.model_dump(include=fields)
    by_expert = await d.dialogue.commission(CommissionDraft(expert.id, TENANT, by="idn_p"))
    by_guide = await d.dialogue.commission(CommissionDraft(walked.id, TENANT, by="idn_p"))
    assert same(by_expert) == same(by_guide), "the same command's plan, the same identity's act"


async def test_switching_mode_keeps_the_work_and_asks_nothing_twice() -> None:
    d = Dialogue()
    draft = await d.dialogue.open(OpenDraft(command=d.command, tenant=TENANT))
    asked: list[str] = []
    for _ in range(2):  # guided: the goal and the steps
        question = next_question(draft)
        assert question is not None
        asked.append(question.field)
        draft = await d.dialogue.revise(
            ReviseDraft(
                draft.id, TENANT, by="idn_p", changes={question.field: ANSWERS[question.field]}
            )
        )
    # expert: the level and its reason, set at once
    draft = await d.dialogue.revise(
        ReviseDraft(
            draft.id,
            TENANT,
            by="idn_p",
            changes={k: ANSWERS[k] for k in ("autonomy_level", "autonomy_reason")},
        )
    )
    question = next_question(draft)
    assert question is not None and question.field == "due"
    assert question.field not in asked
    assert draft.goal == ANSWERS["goal"] and len(draft.steps) == 2, "nothing was lost"


async def test_every_setting_is_shown_in_the_guided_mode_with_its_value_and_why() -> None:
    d = Dialogue()
    walked, _ = await guided(d)
    shown = {s.field: s for s in settings(walked)}
    assert set(shown) >= set(PlanDraft.model_fields) - {
        "id",
        "tenant",
        "command_id",
        "version",
        "changed_by",
        "changed_at",
        "commissioned_version",
        "commissioned",
    }
    unasked = [s for s in shown.values() if not s.asked]
    assert {s.field for s in unasked} == {"results_in", "process_version", "agent"}
    for setting in shown.values():
        assert setting.value and setting.why
    assert shown["results_in"].value == "run" and "runs once" in shown["results_in"].why


async def test_the_guided_start_offers_safe_levels_and_explains_its_terms() -> None:
    d = Dialogue()
    draft = await d.dialogue.open(
        OpenDraft(command=d.command, tenant=TENANT, goal="g", steps=(STEP_A,), due=AT)
    )
    question = next_question(draft)
    assert question is not None and question.field == "autonomy_level"
    assert "level 2" in question.asks and "level 1" in question.asks
    assert TERMS["autonomy level"] in question.explains
    assert SAFE_LEVELS == (1, 2)


def test_the_mode_is_a_preference_never_a_permission() -> None:
    for name in ("open", "revise", "commission"):
        method = getattr(PlanDialogue, name)
        assert "mode" not in inspect.signature(method).parameters
    for kind in (OpenDraft, ReviseDraft, CommissionDraft):
        assert "mode" not in kind.__dataclass_fields__
