"""The process level of UC-6.10, drawn from a process version's facts (ADR-0064, issue #190).

Every step hands over the vocabulary's glyph with motion and without; a step moves only while a
run of the version runs it; the autonomy statement is shown in words; every element's text says
how the step works; a process or a run the predicate withholds is absent and not counted.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from taktus.components.reporting.application.query import LevelQueries
from taktus.components.reporting.domain.model import (
    ProcessFacts,
    ProcessStepFacts,
    Reader,
    RunAtVersion,
    RunFacts,
    RunRef,
    VersionRef,
)
from taktus.components.reporting.domain.model.vocabulary import Motion
from taktus.components.reporting.domain.service import visibility
from taktus.components.reporting.domain.service.drawing import Glyph, Run, Step, check
from taktus.components.reporting.domain.service.levels import (
    AT_REST,
    ProcessLevel,
    autonomy_text,
    process_level,
)
from taktus.shared.v1 import Autonomy, ExactnessClass, Method

AT = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)

AUTONOMY = Autonomy.model_validate(
    {
        "level": 2,
        "reason": "a person confirms each booking",
        "toward_next": "twenty runs without a result defect",
        "actions": {
            "ledger.entry.book": {
                "level": 1,
                "reason": "a booking is legally binding",
                "toward_next": "a legal anchor decides",
            }
        },
    }
)


def run(name: str, *running: str, state: str = "running", minutes: int = 0) -> RunAtVersion:
    return RunAtVersion(
        id=name,
        tenant="default",
        state=state,
        running=running,
        created_at=AT + timedelta(minutes=minutes),
    )


def facts(*runs: RunAtVersion) -> ProcessFacts:
    return ProcessFacts(
        id="invoices",
        tenant="default",
        name="Invoices",
        version="2",
        autonomy=AUTONOMY,
        steps=(
            ProcessStepFacts(
                id="read", method=Method.RULE, exactness=ExactnessClass.EXACT, reason="fixed fields"
            ),
            ProcessStepFacts(
                id="draft",
                method=Method.LLM,
                exactness=ExactnessClass.FREE,
                reason="free text",
                rejected=(Method.RULE,),
                fallback=Method.HUMAN,
                depends_on=("read",),
            ),
            ProcessStepFacts(
                id="approve",
                method=Method.HUMAN,
                exactness=None,
                reason="a person decides",
                depends_on=("draft",),
            ),
        ),
        versions=(VersionRef(version="1"), VersionRef(version="2", active=True)),
        runs=runs,
    )


def drawn(level: ProcessLevel, *, motion: bool) -> list[tuple[Step | Run, Glyph]]:
    def pick(element: object) -> Glyph:
        d = element.drawn  # type: ignore[attr-defined]
        return d.moving if motion else d.still  # type: ignore[no-any-return]

    found: list[tuple[Step | Run, Glyph]] = [
        (
            Step(
                name=s.id,
                method=s.method,
                exactness=s.exactness,
                state="running" if s.running_in else AT_REST,
            ),
            pick(s),
        )
        for s in level.steps
    ]
    found.extend((Run(name=r.id, state=r.state), pick(r)) for r in level.runs)
    return found


def test_every_element_hands_over_the_vocabularys_glyph_with_motion_and_without() -> None:
    level = process_level(facts(run("r1", "draft"), run("r2", state="finished")))
    assert check(drawn(level, motion=True), motion=True) == ()
    assert check(drawn(level, motion=False), motion=False) == ()


def test_a_step_moves_only_while_a_run_of_the_version_runs_it() -> None:
    idle = process_level(facts(run("r2", state="finished")))
    assert all(s.drawn.moving.motion is Motion.NONE for s in idle.steps)
    busy = process_level(facts(run("r1", "draft"), run("r3", "draft", minutes=1)))
    motions = {s.id: s.drawn.moving.motion for s in busy.steps}
    assert motions == {"read": Motion.NONE, "draft": Motion.SHIMMER, "approve": Motion.NONE}
    draft = next(s for s in busy.steps if s.id == "draft")
    assert draft.running_in == ("r3", "r1") and draft.drawn.still.motion is Motion.NONE
    assert draft.drawn.still.still_mark != "none"


def test_the_autonomy_statement_is_shown_with_the_process() -> None:
    level = process_level(facts())
    assert level.process.autonomy == AUTONOMY
    statement = level.process.autonomy_text
    assert "autonomy level 2: a person confirms each booking" in statement
    assert "Toward level 3: twenty runs without a result defect" in statement
    assert "ledger.entry.book runs at level 1: a booking is legally binding" in statement
    assert statement in level.process.text
    at_four = Autonomy.model_validate({"level": 4, "reason": "fully automatic"})
    assert autonomy_text(at_four) == "Runs at autonomy level 4: fully automatic."


def test_each_step_says_how_it_works() -> None:
    texts = {s.id: s.text for s in process_level(facts(run("r1", "draft"))).steps}
    assert "language model, variable; free" in texts["draft"]
    assert "Why this method: free text." in texts["draft"]
    assert "Considered and not chosen: rule." in texts["draft"]
    assert "Falls back to human." in texts["draft"]
    assert "After read." in texts["draft"] and "Running in r1." in texts["draft"]
    assert "At rest." in texts["read"] and "exact" in texts["read"]


def test_the_versions_and_which_is_active() -> None:
    level = process_level(facts())
    assert level.process.version == "2"
    assert [(v.version, v.active) for v in level.process.versions] == [("1", False), ("2", True)]
    assert "the active version" in level.process.text


class Records:
    """Records that hand over whatever they are given, even another tenant's process."""

    def __init__(self, found: ProcessFacts) -> None:
        self.found = found

    async def run(self, tenant: str, run_id: str) -> RunFacts | None:
        return None

    async def process(
        self, tenant: str, process_id: str, version: str | None
    ) -> ProcessFacts | None:
        return self.found


async def test_a_process_the_predicate_withholds_is_absent() -> None:
    reader = Reader(tenant="default", identity="idn_ada")
    elsewhere = facts().model_copy(update={"tenant": "other"})
    assert await LevelQueries(Records(elsewhere)).process(reader, "invoices") is None
    assert await LevelQueries(Records(facts())).process(reader, "invoices") is not None


async def test_a_run_the_predicate_withholds_is_neither_drawn_nor_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = visibility.may_see

    def narrowed(reader: Reader, ref: RunRef) -> bool:
        return original(reader, ref) and ref.id != "r1"

    monkeypatch.setattr(visibility, "may_see", narrowed)
    reader = Reader(tenant="default", identity="idn_ada")
    level = await LevelQueries(Records(facts(run("r1", "draft"), run("r2")))).process(
        reader, "invoices"
    )
    assert level is not None
    assert [r.id for r in level.runs] == ["r2"]
    assert all("r1" not in s.text and "r1" not in s.running_in for s in level.steps)
    assert "with 3 steps and 1 run." in level.process.text
    assert all(s.drawn.moving.motion is Motion.NONE for s in level.steps)
