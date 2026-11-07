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
    "model purpose": (
        "what the agent asks a model for, such as drafting or classifying; Taktus picks the "
        "model that serves the purpose, so no product is named"
    ),
    "knowledge source": (
        "where the agent reads what it knows, named by what it holds, such as handbook or "
        "tickets, never by the product that keeps it"
    ),
    "tool": (
        "an action the agent may take, named by capability, such as mail.read or mail.send; "
        "it may take no other"
    ),
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
    agent = _agent_question(draft)
    if agent is not None:
        return agent
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
        *_agent_settings(draft),
    )


def _agent_question(draft: PlanDraft) -> Question | None:
    """The question for the first part an agent draft's agent lacks (ADR-0292 §2)."""
    agent = draft.agent
    if agent is None:
        return None
    if agent.name is None:
        return Question(
            "agent.name",
            "What should the agent be called? A short name in lowercase, such as replies.",
            "An agent is a packaged assistant: a role, its instructions, what it reads, the "
            "tools it may use, the model purpose it asks and its autonomy level.",
        )
    if agent.instructions is None:
        return Question(
            "agent.instructions", "What should the agent be told, every time it is called?", ""
        )
    if agent.model is None:
        return Question(
            "agent.model",
            "What does the agent ask a model for, in one word?",
            f"The model purpose is {TERMS['model purpose']}.",
        )
    if agent.tools is None:
        return Question(
            "agent.tools",
            "Which tools may the agent use? Name none if it only answers.",
            f"A tool is {TERMS['tool']}.",
        )
    if agent.sources is None:
        return Question(
            "agent.sources",
            "What should the agent read? Name none if it reads nothing.",
            f"A knowledge source is {TERMS['knowledge source']}.",
        )
    if draft.process_version is None:
        return Question(
            "steps",
            "Which process should the agent run when it is called? Choose one of the templates.",
            "An agent runs a process of Taktus's; steps described by hand name none.",
        )
    return None


def _agent_settings(draft: PlanDraft) -> tuple[Setting, ...]:
    """The agent part's settings, asked or not (ADR-0292 §2); none for a draft that is no agent."""
    agent = draft.agent
    whether = Setting(
        "agent",
        "no agent" if agent is None else "an agent, registered when the plan is commissioned",
        "whether the plan works out an agent; chosen when it is opened, not asked",
        asked=False,
    )
    if agent is None:
        return (whether,)

    def listed(values: tuple[str, ...] | None) -> str:
        return "not set yet" if values is None else ", ".join(values) or "none"

    return (
        whether,
        Setting("agent.name", agent.name or "not set yet", "what the agent is called by", True),
        Setting(
            "agent.instructions",
            agent.instructions or "not set yet",
            "what the agent is told every time it is called",
            asked=True,
        ),
        Setting(
            "agent.model",
            agent.model or "not set yet",
            "the model purpose it asks; which model serves it is Taktus's to pick",
            asked=True,
        ),
        Setting(
            "agent.tools",
            listed(agent.tools),
            "the tools it may use and no other; a chosen process proposes the ones it uses",
            asked=True,
        ),
        Setting("agent.sources", listed(agent.sources), "what it reads and nothing else", True),
        Setting(
            "agent.version",
            agent.version,
            "the version the agent is registered as; a registered version never changes",
            asked=False,
        ),
        Setting(
            "agent.connectors",
            listed(agent.connectors),
            "the connectors it may call; set in the expert mode",
            asked=False,
        ),
        Setting(
            "agent.approval_limit",
            "approves nothing" if agent.approval_limit is None else str(agent.approval_limit),
            "up to which amount a result of it may be approved without a further person",
            asked=False,
        ),
    )
