"""Every run ends `ok`, `empty` or `error`, with its duration, in the ledger (ADR-0107 §2,
UC-4.16). `empty` is never recorded as `ok`, and an `error` never as `empty`."""

from __future__ import annotations

from typing import Any

import pytest
from fakes import FakeWorker

from components.run.test_engine import Harness, rule, wait, worker
from taktus.components.run.domain.model import Run, RunState, UnsupportedWork, control_of
from taktus.shared.v1 import LedgerEntry


def found(value: str) -> tuple[Any, dict[str, Any]]:
    return rule("look", {"rule": "constant", "value": value})


def act(*, marks: bool = True) -> tuple[Any, dict[str, Any]]:
    work: dict[str, Any] = {
        "rule": "constant",
        "value": "acted",
        "when": [{"value": {"$from": "look"}, "equals": "something"}],
    }
    if marks:
        work["empty_when_skipped"] = True
    return rule("act", work, after=("look",))


async def ended(h: Harness, run: Run) -> LedgerEntry:
    entries = [e for e in await h.entries(run) if e.kind == "run.ended"]
    assert len(entries) == 1, "a run that ended once says so once"
    return entries[0]


async def test_a_run_that_found_something_ends_ok_with_its_duration() -> None:
    h = Harness(found("something"), act())
    run = await h.start()
    assert run.state is RunState.FINISHED
    end = await ended(h, run)
    assert end.outcome == "ok"
    assert end.duration_seconds is not None and end.duration_seconds >= 0
    assert end.refs.process_version == "p@1" and end.refs.run_id == run.id


async def test_a_run_whose_marked_step_was_skipped_ends_empty_never_ok() -> None:
    h = Harness(found("nothing"), act())
    run = await h.start()
    assert run.state is RunState.FINISHED
    assert (await ended(h, run)).outcome == "empty"


async def test_a_skipped_step_that_marks_nothing_leaves_the_run_ok() -> None:
    h = Harness(found("nothing"), act(marks=False))
    run = await h.start()
    assert (await ended(h, run)).outcome == "ok"


async def test_a_run_that_escalated_ends_error_never_empty() -> None:
    """The step that marks the run empty was skipped, and the run still escalated: `error`."""
    fake = FakeWorker(unreachable="the execution unit could not be started")
    h = Harness(found("nothing"), act(), worker("do", after=("look",)), workers=[fake])
    run = await h.start()
    assert run.state is RunState.ESCALATED
    end = await ended(h, run)
    assert end.outcome == "error"
    assert end.duration_seconds is not None


async def test_the_duration_counts_from_the_run_s_creation() -> None:
    """The run waited 30 s on the fake clock: its duration holds the wait, and no more than
    the clock has moved since the run was created."""
    h = Harness(found("something"), wait("pause", 30, after=("look",)))
    run = await h.start()
    took = (h.clock.now() - run.created_at).total_seconds()
    duration = (await ended(h, run)).duration_seconds
    assert duration is not None and 30 <= duration <= took


async def test_a_halted_run_has_not_ended() -> None:
    h = Harness(found("something"), act())
    run = await h.start(stop_after=1)
    assert run.state is RunState.HALTED
    assert [e for e in await h.entries(run) if e.kind == "run.ended"] == []


def test_a_mark_without_a_when_is_refused() -> None:
    step, _ = found("x")
    with pytest.raises(UnsupportedWork, match="when"):
        control_of(step, {"rule": "constant", "value": 1, "empty_when_skipped": True})
