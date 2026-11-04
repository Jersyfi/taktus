"""A check that reads a source is applied again after the result counted, and marks the result
suspect when the source no longer agrees with it (#92, ADR-0179 §1, UC-4.10)."""

from __future__ import annotations

from governance.test_anchors import TENANT

from exactness.test_checks import RECONCILED, TOTAL_READ, after, booking, world
from taktus.components.run.domain.model import RunState
from taktus.shared.v1 import InputKind


async def test_a_source_that_changed_underneath_a_result_marks_it_suspect_once() -> None:
    w = await world(booking(RECONCILED, value=[100, 20], reads=TOTAL_READ), after())
    run = await w.start()
    assert run.state is RunState.FINISHED
    assert await w.engine.recheck(TENANT, run.id) == (), "the source still agrees"
    w.connector.reads["invoice"] = {"id": "invoice", "total": "125.00"}
    (suspect,) = await w.engine.recheck(TENANT, run.id)
    assert (suspect.step_id, suspect.check, suspect.family) == ("book", "check_1", "reconciliation")
    assert "120" in suspect.compared and "125.00" in suspect.compared
    assert suspect.source.kind is InputKind.SOURCE
    (marked,) = [e for e in await w.entries(run) if e.kind == "check.suspect"]
    assert marked.refs.step_id == "book" and marked.outcome == "check_1"
    assert marked.content_digest is not None
    assert await w.engine.recheck(TENANT, run.id) == (), "a result is marked once per check"
    async with w.persistence.transaction(TENANT):
        again = await w.runs.get(TENANT, run.id)
    assert again is not None and again.updated_at == run.updated_at


async def test_a_rehearsal_or_an_unknown_run_is_not_checked_again() -> None:
    w = await world(booking(RECONCILED, value=[100, 20], reads=TOTAL_READ), after())
    rehearsed = await w.start(rehearsal=True)
    w.connector.reads["invoice"] = {"id": "invoice", "total": "125.00"}
    assert await w.engine.recheck(TENANT, rehearsed.id) == ()
    assert await w.engine.recheck(TENANT, "run_unknown") == ()
