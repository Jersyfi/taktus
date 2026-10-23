"""W-06 and W-11 do not depend on how fast the suite's stop reaches the worker (#551).

The suite stops the work at the start of the step that produced the first artifact. On a machine
under load the request can reach the worker after the work has finished, and the stopped run then
carries nothing to resume from: both checks ended inconclusive on the speed of the machine. The
suite now runs the work again when the stop came too late. These tests delay the first stop by
more than the whole work lasts, which is what a loaded machine did, and hold that the checks
still reach their verdict: a pass for the honest worker, and a failure of W-11 for the worker
that repeats an artifact on resume.
"""

from __future__ import annotations

import asyncio

import pytest

from taktus.conformance import Status
from taktus.conformance.client import Json, Response, WorkerClient

from .conftest import StartWorker

LATE = 2.5
"""Seconds. The reference worker's quick work lasts under a second."""


@pytest.fixture
def first_stop_is_late(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Delay the first stop of the suite's stopped run; every other request is untouched."""
    delayed: list[float] = []
    real = WorkerClient.post

    async def post(self: WorkerClient, path: str, body: Json | None = None) -> Response:
        is_the_stop = (body or {}).get("reason") == "conformance W-06"
        if path.endswith("/stop") and is_the_stop and not delayed:
            delayed.append(LATE)
            await asyncio.sleep(LATE)
        return await real(self, path, body)

    monkeypatch.setattr(WorkerClient, "post", post)
    return delayed


async def test_a_stop_that_comes_after_the_work_has_finished_is_made_again(
    start_worker: StartWorker, first_stop_is_late: list[float]
) -> None:
    worker = start_worker()
    report = await worker.run_suite()
    assert first_stop_is_late, "the first stop was delayed"
    assert report.failed == [] and report.inconclusive == [], report.render()
    statuses = {c.id: c.status for c in report.checks}
    assert statuses["W-06"] is Status.PASSED and statuses["W-11"] is Status.PASSED
    stopped = [r for r in report.runs if r.purpose == "stopped"]
    assert len(stopped) == 1, "the run the checks judge is the one whose stop landed"
    assert stopped[0].outcome == "stopped"


async def test_a_worker_that_repeats_an_artifact_on_resume_fails_w11_also_after_a_late_stop(
    start_worker: StartWorker, first_stop_is_late: list[float]
) -> None:
    worker = start_worker(fault="W-11")
    report = await worker.run_suite()
    assert first_stop_is_late, "the first stop was delayed"
    assert {c.id for c in report.failed} == {"W-11"}, report.render()
