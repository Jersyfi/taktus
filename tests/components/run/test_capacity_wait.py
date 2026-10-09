"""A worker at capacity makes a step wait, not fail (ADR-0037, issue #122).

The engine against a scripted worker that answers at capacity: the step goes back to its
boundary and gives its reservation back, the run halts with cause `capacity`, a resume asks the
worker again, and once the worker takes the assignment the run goes on as if nothing had
happened — but for `step.waiting` and `step.waited` in the ledger, the latter naming the wait's
account, cause and duration. A wait that outlasts the step's ceiling ends the step with cause
`capacity` and escalates the run. The runner's side — the deferral of the job, and runners that
share one worker — is in `test_runner.py`.
"""

from __future__ import annotations

import json
from typing import Any

from fakes import FakeWorker, InnerStep

from taktus.components.run.application.service import EngineOptions
from taktus.components.run.domain.model import Cause, RunState, StepState
from taktus.components.run.domain.service import waiting
from taktus.shared.v1 import Step

from .test_engine import Harness, worker


def waiting_worker(ceiling: int | None = None) -> tuple[Step, dict[str, Any]]:
    step, work = worker("do")
    if ceiling is not None:
        work["capacity_ceiling_seconds"] = ceiling
    return step, work


async def document(h: Harness, digest: str | None) -> dict[str, Any]:
    assert digest is not None
    content = await h.objects.get(digest)
    assert content is not None
    loaded: dict[str, Any] = json.loads(content)
    return loaded


async def test_a_worker_at_capacity_makes_the_step_wait_and_a_later_try_succeeds() -> None:
    fake = FakeWorker(full_for=2, script=(InnerStep("one", 1.0),))
    h = Harness(waiting_worker(), workers=[fake])

    run = await h.start()
    assert run.state is RunState.HALTED and run.cause is Cause.CAPACITY
    do = run.step_run("do")
    assert do.state is StepState.STOPPED, "back at its boundary, not failed"
    assert do.waiting_since is not None and do.waits == 1
    assert do.reason is not None and "at capacity" in do.reason
    assert run.consumed().compute_seconds is None, "the reservation was given back"
    assert fake.assignments == [], "nothing started"

    run = await h.resume(run)
    assert run.state is RunState.HALTED and run.cause is Cause.CAPACITY
    assert run.step_run("do").waits == 2
    since = run.step_run("do").waiting_since

    run = await h.resume(run)
    assert run.state is RunState.FINISHED
    do = run.step_run("do")
    assert do.state is StepState.SUCCEEDED and do.waiting_since is None and do.waits == 0
    assert len(fake.assignments) == 1 and fake.refused == 2

    kinds = await h.kinds(run)
    assert kinds.count("step.waiting:do:at_capacity") == 2
    assert kinds.count("run.halted::capacity") == 2
    assert not [k for k in kinds if k.startswith(("run.escalated", "step.finished:do:failed"))]
    waited = [e for e in await h.entries(run) if e.kind == "step.waited"]
    assert len(waited) == 1 and waited[0].outcome == waiting.AT_CAPACITY
    assert waited[0].adapter == "worker.fake.0"
    assert kinds.index("step.waited:do:at_capacity") < kinds.index("step.started:do")
    record = await document(h, waited[0].content_digest)
    assert record["account"] == "limit.compute" and record["cause"] == "at_capacity"
    assert record["ended"] == "assigned" and record["waits"] == 2
    assert since is not None and record["since"] == since.isoformat()
    assert record["seconds"] > 0
    assert await h.verify()


async def test_a_wait_beyond_the_step_s_ceiling_escalates_with_the_cause() -> None:
    fake = FakeWorker(full_for=1000)
    h = Harness(waiting_worker(ceiling=30), workers=[fake])
    run = await h.start()
    tries = 1
    while run.state is RunState.HALTED:
        assert run.cause is Cause.CAPACITY
        await h.clock.sleep(10)  # what the runner's delay would be
        run = await h.resume(run)
        tries += 1
        assert tries < 10, "the ceiling ended the wait"
    assert run.state is RunState.ESCALATED and run.cause is Cause.CAPACITY
    do = run.step_run("do")
    assert do.state is StepState.FAILED
    assert do.reason is not None and "stayed at capacity" in do.reason and "30s" in do.reason
    assert do.waiting_since is None
    assert fake.assignments == []

    kinds = await h.kinds(run)
    assert kinds[-3:] == [
        "step.waited:do:at_capacity",
        "step.finished:do:at_capacity",
        "run.escalated::capacity",
    ]
    waited = next(e for e in await h.entries(run) if e.kind == "step.waited")
    record = await document(h, waited.content_digest)
    assert record["ended"] == "ceiling" and record["ceiling_seconds"] == 30
    assert record["seconds"] >= 30 and record["waits"] == tries
    assert await h.verify()


async def test_a_step_without_a_ceiling_takes_the_engine_s() -> None:
    fake = FakeWorker(full_for=1000)
    options = EngineOptions(uncalibrated_margin=0.0, capacity_ceiling_seconds=5)
    h = Harness(waiting_worker(), workers=[fake], options=options)
    run = await h.start()
    await h.clock.sleep(10)
    run = await h.resume(run)
    assert run.state is RunState.ESCALATED and run.cause is Cause.CAPACITY
    assert "ceiling is 5s" in (run.step_run("do").reason or "")


async def test_an_escalated_wait_resumes_as_a_fresh_wait() -> None:
    """A person who resumes the escalated run starts a new wait: the ceiling counts again
    from the first answer at capacity after the resume."""
    fake = FakeWorker(full_for=3)
    h = Harness(waiting_worker(ceiling=5), workers=[fake])
    run = await h.start()
    await h.clock.sleep(10)
    run = await h.resume(run)
    assert run.state is RunState.ESCALATED
    run = await h.resume(run)
    assert run.state is RunState.HALTED and run.cause is Cause.CAPACITY
    assert run.step_run("do").waits == 1
    run = await h.resume(run)
    assert run.state is RunState.FINISHED
