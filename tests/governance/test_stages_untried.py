"""A stage's report says which process it raises to level 3 or 4 untried by hand (UC-6.3 §2,
ADR-0180 §3, #627).

The world is `governance.test_stages`'s, its levels read with the trials of the takeover
instructions. A process the stage would raise to level 3 or 4 whose active version no person
has run by hand from its instructions is *untried* in the stage's view, and the report that
proposes opening the stage says so; a passed trial on that version removes it."""

from __future__ import annotations

from datetime import UTC, datetime

from governance.test_stages import PERSON, TENANT, World, declared
from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.process.domain.model import TakeoverTrial
from taktus.composition.stages import LevelsOfTheProcess, _untried


def world() -> tuple[World, MemoryRepository[TakeoverTrial]]:
    w = World()
    trials = MemoryRepository(w.persistence, TakeoverTrial)
    w.stages._levels = LevelsOfTheProcess(  # the same levels, now reading the trials
        w.processes, w.versions, w.persistence, w.corrections, trials
    )
    return w, trials


async def test_a_stage_that_raises_a_process_to_level_three_reports_it_untried_by_hand() -> None:
    w, trials = world()
    await declared(w)
    await w.registered("report", 2)
    await w.registered("cost", 2)
    await w.registered("triage", 2)
    routine = await w.view("routine")
    by = {p.process: p for p in routine.processes}
    assert by["cost"].untried and by["triage"].untried, "granted 3 and 4, never tried by hand"
    assert not {p.process: p for p in (await w.view("watch")).processes}["report"].untried
    said = _untried(routine)
    assert any(line.startswith("cost would run at level 3, untried by hand") for line in said)
    assert all("cost@1" in line or "triage@1" in line for line in said)
    async with w.persistence.transaction(TENANT):
        await trials.put(
            TENANT,
            TakeoverTrial(
                id="trl_cost",
                process_id="cost",
                process_version="cost@1",
                role="operations",
                passed=True,
                at=datetime(2026, 10, 1, tzinfo=UTC),
            ),
        )
    again = {p.process: p for p in (await w.view("routine")).processes}
    assert not again["cost"].untried and again["triage"].untried
    assert PERSON not in " ".join(_untried(await w.view("routine"))), "it names no person"
