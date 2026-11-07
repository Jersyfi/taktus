"""The guided mode of the plan dialogue (ADR-0238, UC-13.1, UC-10.3).

Two ways of working out the same plan draft. In the **expert mode** a person sets any field of
the draft at once. In the **guided mode** Taktus asks one question at a time, for the first part
the draft still lacks, in plain words, each technical term explained where it first appears;
the answer is a revision of the same draft. Both modes change the one record, so the same
intent reaches the same draft, and commissioning it is the same act with the same rights.

Switching mode at any point keeps the work: a question is asked only for what the draft lacks,
so nothing answered in either mode is asked again. Every setting that takes effect is shown in
the guided mode — the ones it asks about, and the ones it does not, with the value each takes
and why.

The mode is a preference of the person and never a permission: nothing here, and nothing in the
dialogue, reads it to decide what a person may do.

Pure: the draft in, the question and the settings out.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from taktus.components.command.domain.model.planning import PlanDraft
from taktus.shared.v1 import PlanResult


class Mode(StrEnum):
    GUIDED = "guided"
    EXPERT = "expert"


@dataclass(frozen=True)
class Question:
    field: str
    """The field of the draft the answer revises."""
    asks: str
    explains: str
    """The technical term the question uses, explained in plain words; empty when it uses none."""
    step_id: str | None = None
    """For an estimate: the step it is about."""


@dataclass(frozen=True)
class Setting:
    field: str
    value: str
    why: str
    asked: bool
    """Whether the guided mode asks for it; one it does not ask is shown with its value and why."""


SAFE_LEVELS = (1, 2)
"""The levels the guided start offers: a person confirms every act, or performs it (ADR-0026)."""

TERMS = {
    "autonomy level": (
        "how much Taktus does on its own: at level 1 it proposes and you act, at level 2 it acts "
        "once you confirmed each step, at level 3 and 4 it acts and tells you"
    ),
    "step": "one piece of the work that ends with a result Taktus keeps, so nothing is lost",
    "estimate": (
        "how much a step will take — seconds, tokens or money — and what that figure is based on"
    ),
}


def next_question(draft: PlanDraft) -> Question | None:
    """The question for the first part the draft lacks, or None when it lacks nothing that the
    guided mode asks. A part set in either mode is never asked again."""
    if draft.goal is None:
        return Question("goal", "What should be achieved? Say it in one sentence.", "")
    if not draft.steps:
        return Question(
            "steps",
            "Which template or process should do it? Choose one, or describe the steps.",
            f"A step is {TERMS['step']}.",
        )
    if draft.due is None:
        return Question("due", "By when should it be done?", "")
    if draft.autonomy_level is None:
        return Question(
            "autonomy_level",
            "Should you confirm every step before Taktus acts (level 2), or perform each act "
            "yourself on Taktus's proposal (level 1)?",
            f"The autonomy level is {TERMS['autonomy level']}. A first automation starts at "
            "level 1 or 2; it goes higher only when you raise it later.",
        )
    if draft.autonomy_reason is None:
        return Question(
            "autonomy_reason",
            "Why that level? A sentence is enough, for whoever reads the plan later.",
            "",
        )
    for step_id in draft.unestimable():
        return Question(
            "estimates",
            f"How long will step {step_id} take, roughly, and what is that based on?",
            f"An estimate is {TERMS['estimate']}. Without a basis it is shown as a guess.",
            step_id=step_id,
        )
    return None


def settings(draft: PlanDraft) -> tuple[Setting, ...]:
    """Every setting of the draft that takes effect, with its value and why, in the order the
    guided mode presents them; the ones it never asks are marked so."""

    def shown(value: object) -> str:
        return "not set yet" if value is None or value == () else str(value)

    level_why = (
        "a first automation starts where a person confirms or performs every act (ADR-0026)"
        if draft.autonomy_level in SAFE_LEVELS
        else "set in the expert mode; the guided mode would have offered level 1 or 2"
    )
    return (
        Setting("goal", shown(draft.goal), "what the plan is for, in your words", asked=True),
        Setting(
            "steps",
            shown(", ".join(s.id for s in draft.steps) or None),
            "what does the work, step by step",
            asked=True,
        ),
        Setting("due", shown(draft.due), "the date the plan is due", asked=True),
        Setting("autonomy_level", shown(draft.autonomy_level), level_why, asked=True),
        Setting(
            "autonomy_reason",
            shown(draft.autonomy_reason),
            "why the level, kept with it",
            asked=True,
        ),
        Setting(
            "estimates",
            shown("; ".join(e.shown() for e in draft.estimates) or None),
            "what each step will take; a step without one cannot be commissioned (ADR-0005)",
            asked=True,
        ),
        Setting(
            "results_in",
            str(draft.results_in),
            "a plan runs once"
            if draft.results_in is PlanResult.RUN
            else "the plan becomes a new process version, registered like any other",
            asked=False,
        ),
        Setting(
            "process_version",
            shown(draft.process_version),
            "the process the chosen template registered; set by the choice, not asked",
            asked=False,
        ),
    )
