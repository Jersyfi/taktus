"""The distribution family: a result against the moving median of the step's earlier results,
decided by a statistic, applied after the result counted (UC-4.10, ADR-0271).

What is real: the run engine over memory stores, the check of the catalogue, the ledger. What is
proven: a monthly total ten times the previous eleven marks exactly one suspect, on the step
that produced it, with the family `distribution` and its magnitude and baseline, and the run
finishes as it would; a result within the band, or with fewer earlier results than the window,
is not marked; a distribution decided by a rule or by a language model does not exist; and
every check of every example and blueprint bundle decides by a rule or a statistic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from governance.test_anchors import TENANT

from exactness.test_checks import booking, world
from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.governance.application.service import ReportDefect, ResultDefects
from taktus.components.governance.domain.model.anchors import AnchorConfiguration
from taktus.components.governance.domain.model.defects import Found
from taktus.components.governance.domain.model.incident import Incident, WatchConfiguration
from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.run.domain.model import RunState
from taktus.composition.contents import StepContents
from taktus.shared.v1 import Check, CheckKind, CheckMethod, ExactnessClass, Method, Step

ROOT = Path(__file__).resolve().parents[2]
MONTHLY = Check(kind=CheckKind.DISTRIBUTION, subject="the monthly total", window=11, band=0.5)
TOTALS = [100, 104, 97, 101, 99, 103, 98, 102, 100, 96, 105]


async def months(*totals: int) -> Any:
    w = await world(booking(MONTHLY, value=totals[0]))
    runs = []
    for total in totals:
        w.work["book"]["value"] = total
        runs.append(await w.start())
    return w, runs


async def suspects(w: Any) -> list[Any]:
    async with w.persistence.transaction(TENANT):
        return [e for e in await w.ledger.entries(TENANT) if e.kind == "check.suspect"]


async def test_a_total_ten_times_the_previous_eleven_marks_one_suspect_with_its_magnitude() -> None:
    w, runs = await months(*TOTALS, 1000)
    (marked,) = await suspects(w)
    last = runs[-1]
    assert last.state is RunState.FINISHED, "the mark stops nothing"
    assert (marked.refs.run_id, marked.refs.step_id, marked.outcome) == (last.id, "book", "check_1")
    assert marked.content_digest is not None
    stored = await w.engine._objects.get(marked.content_digest)
    assert stored is not None
    suspect = yaml.safe_load(stored)
    assert suspect["family"] == "distribution" and suspect.get("source") is None
    assert "the value 1000 lies 900 from the median 100 of the 11 result(s)" in suspect["compared"]
    assert "9 of its size; the band admits 0.5" in suspect["compared"]


async def test_a_result_within_the_band_or_before_a_baseline_is_not_marked() -> None:
    w, _ = await months(*TOTALS, 140)
    assert await suspects(w) == []
    w, _ = await months(100, 1000)
    assert await suspects(w) == [], "one earlier result is no baseline for a window of eleven"


async def test_a_result_of_another_sign_is_marked() -> None:
    w, _ = await months(*TOTALS, -100)
    (marked,) = await suspects(w)
    stored = await w.engine._objects.get(marked.content_digest)
    assert stored is not None and "another sign" in yaml.safe_load(stored)["compared"]


@pytest.mark.parametrize("method", ["rule", "llm"])
def test_a_distribution_decides_by_a_statistic_and_by_nothing_else(method: str) -> None:
    with pytest.raises(ValueError, match=r"distribution|method"):
        Check.model_validate({"kind": "distribution", "window": 11, "band": 0.5, "method": method})
    assert MONTHLY.decided_by is CheckMethod.STATISTICS


def test_every_check_of_every_bundle_decides_by_a_rule_or_a_statistic() -> None:
    bundles = [
        *ROOT.glob("blueprints/*/processes/*.yaml"),
        *ROOT.glob("blueprints/gallery/*/processes/*.yaml"),
        *ROOT.glob("examples/processes/*.yaml"),
    ]
    checks = [
        check
        for path in bundles
        for step in parse_bundle(yaml.safe_load(path.read_text(encoding="utf-8"))).steps
        for check in step.checks or ()
    ]
    assert checks, "the bundles declare checks"
    assert {check.decided_by for check in checks} <= {CheckMethod.RULE, CheckMethod.STATISTICS}


async def test_the_window_of_a_suspect_starts_where_the_check_run_again_marks_first() -> None:
    """UC-4.11 §1: no change in how the step produced, so the distribution that marked the
    newest total is run again over the recorded totals, each against those before it; the
    first it marks starts the window, and the analysis changes nothing."""
    w, runs = await months(*TOTALS, 1000, 1010, 990)
    assert len(await suspects(w)) == 3
    defects = ResultDefects(
        w.engine._provenance,
        w.ledger,
        MemoryRepository(w.persistence, Incident),
        MemoryRepository(w.persistence, WatchConfiguration),
        MemoryRepository(w.persistence, AnchorConfiguration),
        w.persistence,
        w.clock,
        contents=StepContents(
            objects=w.engine._objects,
            runs=w.runs,
            provenance=w.engine._provenance,
            ledger=w.ledger,
            work=w.persistence,
        ),
    )
    assessed = await defects.assess(
        ReportDefect(tenant=TENANT, run_id=runs[-1].id, step_id="book", found=Found.RECHECKED)
    )
    analysis = assessed.analysis
    assert analysis.cause is None
    assert analysis.rechecked_from == runs[11].id, "the first total ten times the others"
    assert analysis.window_runs == 3 and not analysis.unbounded


def tolerant(step_id: str, *checks: Check) -> tuple[Step, dict[str, Any]]:
    step = Step(
        id=step_id,
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        checks=checks or None,
    )
    return step, {"rule": "constant", "value": 7}


async def test_a_result_no_check_judged_is_recorded_as_unchecked_and_never_as_passed() -> None:
    bounded = Check(kind=CheckKind.BOUNDS, maximum=10)
    w = await world(tolerant("guess"), tolerant("bounded", bounded))
    run = await w.start()
    assert run.state is RunState.FINISHED
    async with w.persistence.transaction(TENANT):
        entries = list(await w.ledger.entries(TENANT, run.id))
    unchecked = [(e.refs.step_id, e.outcome) for e in entries if e.kind == "result.unchecked"]
    assert unchecked == [("guess", "unchecked")], "the step with a check is not unchecked"
    rehearsed = await w.start(rehearsal=True)
    async with w.persistence.transaction(TENANT):
        again = list(await w.ledger.entries(TENANT, rehearsed.id))
    assert not [e for e in again if e.kind == "result.unchecked"], "a rehearsal counts nothing"
