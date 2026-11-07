"""A level per class of request a step's result names, counted and lowered per class (ADR-0215,
UC-7.1, UC-7.5, UC-03 B-3.03).

Each case registers a version whose statement names its classes, runs it through the run
engine over the fakes `test_corrections.py` wires, and reads back the run, the ledger and the
governance component's figures.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from fakes.connector import WRITE
from fakes.takeover import instructed

from taktus.components.governance.domain.model import IncidentKind, Unit
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
)
from taktus.components.process.domain.model import RaiseRefused
from taktus.components.run.domain.model import RunState, StepState
from taktus.shared.v1 import Autonomy, AutonomyLevel

from .test_corrections import PERSON, TENANT, VERSION, World, call, rule_step

LIMITS = {
    "raise_decisions": 2,
    "raise_weeks": 1,
    "raise_rate": 0.05,
    "lower_corrections": 2,
    "lower_days": 7,
}


def statement(
    level: int, default: int, levels: dict[str, int], limits: dict[str, Any] | None = None
) -> dict[str, Any]:
    def entry(at: int) -> dict[str, Any]:
        return {"level": at, "reason": "r", **({"toward_next": "t"} if at < 4 else {})}

    return {
        "level": level,
        "reason": "r",
        "toward_next": "t",
        "history": 1,
        "classes": {
            "step": "classify",
            "default": entry(default),
            "levels": {name: entry(at) for name, at in levels.items()},
            "limits": limits or LIMITS,
        },
    }


def bundle(version: str, autonomy: dict[str, Any], answer: str = "how_to") -> dict[str, Any]:
    return instructed(
        {
            "id": "p",
            "version": version,
            "name": "P",
            "autonomy": autonomy,
            "steps": [
                {
                    "id": "classify",
                    "method": "rule",
                    "reason": "r",
                    "rejected": [],
                    "exactness": "tolerant",
                    "work": {"rule": "constant", "value": {"text": answer}},
                },
                {
                    "id": "send",
                    "method": "rule",
                    "reason": "r",
                    "rejected": [],
                    "exactness": "sourced",
                    "depends_on": ["classify"],
                    "work": {"rule": "connector", "operation": WRITE, "input": {"id": "x"}},
                },
            ],
        }
    )


async def world(
    answer: str,
    level: AutonomyLevel,
    default: int,
    levels: dict[str, int],
    limits: dict[str, Any] | None = None,
) -> World:
    w = await World(
        rule_step("classify", value={"text": answer}),
        call("send", WRITE, after=("classify",)),
        level=level,
    ).setup()
    await w.register.execute(
        RegisterProcessVersion(
            bundle("1", statement(level, default, levels, limits), answer),
            tenant=TENANT,
            by=PERSON,
            approved_by=PERSON,
        )
    )
    return w


async def test_a_released_class_sends_at_its_level_while_every_other_class_waits() -> None:
    released = await world("how_to", 3, 2, {"how_to": 3, "billing": 2})
    run = await released.start()
    assert run.state is RunState.FINISHED, "the class released for sending runs unattended"
    assert run.case_class == "how_to"
    assert released.connector.acted == 1
    (classified,) = await released.of("run.classified")
    assert classified.outcome == "named" and classified.refs.case_class == "how_to"

    held = await world("billing", 3, 2, {"how_to": 3, "billing": 2})
    run = await held.start()
    assert run.step_run("classify").state is StepState.SUCCEEDED, "before the class: level 3"
    assert run.step_run("send").state is StepState.WAITING_HUMAN, "the class billing: level 2"
    assert held.connector.acted == 0
    (awaiting,) = [e for e in await held.of("step.awaiting") if e.refs.step_id == "send"]
    assert (await held.document(awaiting.content_digest))["held_by"] == "class billing"


async def test_an_answer_that_names_no_class_runs_at_the_default_and_counts_for_the_process() -> (
    None
):
    w = await world("the weather", 3, 2, {"how_to": 3})
    run = await w.start()
    assert run.case_class is None
    assert run.step_run("send").state is StepState.WAITING_HUMAN
    (classified,) = await w.of("run.classified")
    assert classified.outcome == "unnamed" and classified.refs.case_class is None
    await w.answer(run, "send")
    (decided,) = await w.of("proposal.decided")
    assert decided.refs.case_class is None and decided.refs.action is None


async def test_a_decision_on_a_step_its_class_held_counts_for_that_class() -> None:
    w = await world("how_to", 2, 2, {"how_to": 2, "billing": 2})
    run = await w.start()
    assert run.step_run("classify").state is StepState.WAITING_HUMAN, "level 2: confirmed first"
    run = await w.answer(run, "classify")
    assert run.step_run("send").state is StepState.WAITING_HUMAN
    run = await w.answer(run, "send")
    assert run.state is RunState.FINISHED
    decided = await w.of("proposal.decided")
    assert [(d.refs.step_id, d.refs.case_class) for d in decided] == [
        ("classify", None),
        ("send", "how_to"),
    ], "at the process's level a class named holds, so that it gathers its own evidence"
    units = {f.unit for f in await w.corrections.figures(TENANT)}
    assert Unit(process_id="p", case_class="how_to") in units


async def test_two_corrections_in_a_week_lower_the_class_and_leave_the_others() -> None:
    w = await world("how_to", 2, 2, {"how_to": 2, "billing": 2})
    for _ in range(2):
        run = await w.start()
        run = await w.answer(run, "classify")
        await w.answer(run, "send", rejected=True)
    lowered = await w.corrections.lowered(TENANT, VERSION)
    assert dict(lowered.classes) == {"how_to": 1}, "the statement's count, not the tenant's rate"
    assert lowered.level is None and not lowered.actions, "the process and its actions stay"
    (incident,) = await w.corrections.lowerings(TENANT)
    assert incident.kind is IncidentKind.CORRECTIONS
    assert incident.facts["unit"] == "class how_to"
    assert incident.facts["corrections_limit"] == 2.0
    (entry,) = await w.of("autonomy.lowered")
    assert entry.refs.case_class == "how_to" and entry.outcome == "level_1"
    assert entry.refs.actor is None, "nobody approves the way down"

    run = await w.start()
    run = await w.answer(run, "classify")
    assert run.classes is not None and run.classes.level_of("how_to") == 1
    awaiting = [e.outcome for e in await w.of("step.awaiting") if e.refs.step_id == "send"]
    assert awaiting[-1] == "performance", "at level 1 the person performs the send"


async def test_a_raise_of_a_class_is_proposed_on_the_statements_limits_and_never_applied() -> None:
    w = await world("how_to", 2, 2, {"how_to": 2})
    for _ in range(2):
        run = await w.start()
        run = await w.answer(run, "classify")
        await w.answer(run, "send")
        w.clock.current += timedelta(days=8)
    run = await w.start()
    run = await w.answer(run, "classify")
    await w.answer(run, "send")
    proposed = await w.of("autonomy.proposed")
    assert [(p.refs.case_class, p.outcome) for p in proposed] == [("how_to", "corrections")]
    assert (await w.corrections.lowered(TENANT, VERSION)).classes == {}
    async with w.persistence.transaction(TENANT):
        version = await w.register._versions.get(TENANT, VERSION)
    assert version is not None and version.autonomy.class_level("how_to") == 2, "never applied"


async def test_a_class_raised_by_a_new_version_needs_a_persons_approval() -> None:
    w = await world("how_to", 3, 2, {"how_to": 2})
    with pytest.raises(RaiseRefused) as refused:
        await w.register.execute(
            RegisterProcessVersion(
                bundle("2", statement(3, 2, {"how_to": 3})), tenant=TENANT, by=PERSON
            )
        )
    assert "the class how_to from level 2 to 3" in " ".join(refused.value.findings)
    with pytest.raises(RaiseRefused) as default:
        await w.register.execute(
            RegisterProcessVersion(
                bundle("2", statement(3, 3, {"how_to": 2})), tenant=TENANT, by=PERSON
            )
        )
    assert "a class not named from level 2 to 3" in " ".join(default.value.findings)


def test_no_class_runs_above_the_process_and_the_limits_are_the_statements() -> None:
    with pytest.raises(ValueError, match="above the process"):
        Autonomy.model_validate(statement(2, 2, {"how_to": 3}))
    with pytest.raises(ValueError, match="above the process"):
        Autonomy.model_validate(statement(2, 3, {}))
    without = statement(2, 2, {})
    del without["classes"]["limits"]
    with pytest.raises(ValueError, match="limits"):
        Autonomy.model_validate(without)
