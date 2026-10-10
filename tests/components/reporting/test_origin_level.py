"""The origin of a result, the fourth level of UC-6.10 (ADR-0068, issue #192).

The path from a result back through the steps and sources that produced it is drawn from the
provenance records and nothing else: the result with its exactness class, each step with how it
works, each source with when it was read; nothing moves; a step whose run the reader may not see
is absent and the path ends there; a step that produced no result has no origin.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from taktus.components.reporting.application.query import LevelQueries
from taktus.components.reporting.domain.model import (
    OriginFacts,
    OverviewFacts,
    ProcessFacts,
    Reader,
    RunFacts,
    RunRef,
)
from taktus.components.reporting.domain.model.vocabulary import Motion
from taktus.components.reporting.domain.service import visibility
from taktus.components.reporting.domain.service.drawing import (
    Element,
    Glyph,
    Result,
    Source,
    Step,
    check,
)
from taktus.components.reporting.domain.service.levels import OriginLevel, origin_level
from taktus.shared.v1 import ExactnessClass, Provenance

AT = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)
DIGEST = "sha256:" + "1" * 64
READER = Reader(tenant="default", identity="idn_ada")


def record(run: str, step: str, method: str, exactness: str | None, *inputs: Any) -> Provenance:
    return Provenance.model_validate(
        {
            "id": f"prv_{run}_{step}",
            "run_id": run,
            "step_id": step,
            "process_version": "invoices@1",
            "method": method,
            "exactness": exactness,
            "inputs": list(inputs),
            "outputs": [],
            "result_digest": DIGEST if exactness else None,
            "ledger_seq": 1,
            "recorded_at": AT,
        }
    )


def result_of(run: str, step: str) -> dict[str, Any]:
    return {"kind": "result", "run_id": run, "step_id": step, "digest": DIGEST, "observed_at": AT}


SOURCE = {
    "kind": "source",
    "capability": "repository.files",
    "ref": "main:prices.csv",
    "digest": DIGEST,
    "observed_at": AT,
}

PATH = OriginFacts(
    tenant="default",
    run_id="r2",
    step_id="book",
    records=(
        record("r2", "book", "rule", "exact", result_of("r2", "total"), result_of("r1", "read")),
        record("r2", "total", "statistics", "sourced", SOURCE),
        record("r1", "read", "rule", "exact", SOURCE),
    ),
)


def drawn(level: OriginLevel, *, motion: bool) -> list[tuple[Element, Glyph]]:
    def pick(element: Any) -> Glyph:
        found: Glyph = element.drawn.moving if motion else element.drawn.still
        return found

    elements: list[tuple[Element, Glyph]] = [
        (
            Result(
                name=f"{level.result.run}/{level.result.step}", exactness=level.result.exactness
            ),
            pick(level.result),
        )
    ]
    elements.extend(
        (Step(name=s.step, method=s.method, exactness=s.exactness, state="succeeded"), pick(s))
        for s in level.steps
    )
    elements.extend((Source(name=f"{s.capability} {s.ref}"), pick(s)) for s in level.sources)
    return elements


def test_the_path_runs_from_the_result_back_through_steps_and_sources() -> None:
    level = origin_level(PATH)
    assert level is not None
    assert level.result.exactness is ExactnessClass.EXACT
    assert level.result.depends_on == ("r2/book",)
    assert [s.id for s in level.steps] == ["r2/book", "r1/read", "r2/total"]
    by_id = {s.id: s for s in level.steps}
    assert by_id["r2/book"].depends_on == ("r2/total", "r1/read")
    assert by_id["r2/total"].depends_on == ("source:repository.files:main:prices.csv",)
    assert [s.id for s in level.sources] == ["source:repository.files:main:prices.csv"]


def test_every_glyph_is_the_vocabularys_and_nothing_moves() -> None:
    level = origin_level(PATH)
    assert level is not None
    for motion in (True, False):
        found = drawn(level, motion=motion)
        assert check(found, motion=motion) == ()
        assert all(g.motion is Motion.NONE for _, g in found)


def test_each_element_says_what_it_is_and_when() -> None:
    level = origin_level(PATH)
    assert level is not None
    assert level.result.text == "result of r2/book: exact; recorded, produced by book in run r2."
    book = level.steps[0].text
    assert "rule, reproducible; exact; completed." in book
    assert "Read r2/total, r1/read." in book and "In run r2, invoices@1." in book
    assert AT.isoformat() in level.sources[0].text


def test_a_step_that_produced_no_result_has_no_origin() -> None:
    approve = OriginFacts(
        tenant="default",
        run_id="r2",
        step_id="approve",
        records=(record("r2", "approve", "human", None),),
    )
    assert origin_level(approve) is None


class Records:
    async def run(self, tenant: str, run_id: str) -> RunFacts | None:
        return None

    async def process(
        self, tenant: str, process_id: str, version: str | None
    ) -> ProcessFacts | None:
        return None

    async def overview(self, tenant: str) -> OverviewFacts:
        return OverviewFacts(tenant=tenant)

    async def origin(self, tenant: str, run_id: str, step_id: str) -> OriginFacts | None:
        return PATH if (run_id, step_id) == ("r2", "book") else None


async def test_a_step_on_the_path_the_reader_may_not_see_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = visibility.may_see

    def narrowed(reader: Reader, ref: RunRef) -> bool:
        return original(reader, ref) and ref.id != "r1"

    monkeypatch.setattr(visibility, "may_see", narrowed)
    level = await LevelQueries(Records()).origin(READER, "r2", "book")
    assert level is not None
    assert [s.id for s in level.steps] == ["r2/book", "r2/total"]
    assert level.steps[0].depends_on == ("r2/total",)
    assert "r1" not in level.steps[0].text


async def test_a_result_the_reader_may_not_see_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(visibility, "may_see", lambda reader, ref: ref.id != "r2")
    assert await LevelQueries(Records()).origin(READER, "r2", "book") is None
    assert await LevelQueries(Records()).origin(READER, "r9", "book") is None
