"""An assignment is recorded before it is handed over, and adopted after a crash (ADR-0038).

The engine runs against a scripted worker that keeps its assignments when the instance that
posted them dies, as a worker process does. A crash is an exception that is no worker error:
nothing in the engine handles it, and what the store holds at that moment is what the next
instance finds. The cases against two runners and PostgreSQL are in
`tests/integration/test_handover.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fakes import FakeWorker, InnerStep

from taktus.components.run.domain.model import Cause, RunState, StepState
from taktus.ports.worker import Assignment, AssignmentState, Event, StopRequest, WorkerError

from .test_engine import Harness, worker


class Crash(Exception):
    """The instance dies: not a worker error, nothing the engine handles."""


def script() -> tuple[InnerStep, ...]:
    return (
        InnerStep("one", 1.0, (("out-1", b"1"),)),
        InnerStep("two", 1.0, (("out-2", b"2"),)),
        InnerStep("three", 1.0, (("out-3", b"3"),)),
    )


@dataclass
class DiesAfterAcceptance(FakeWorker):
    """The worker accepts the assignment; the instance that posted it dies before it hears so."""

    die: bool = True

    async def assign(self, assignment: Assignment) -> AssignmentState:
        state = await super().assign(assignment)
        if self.die:
            self.die = False
            raise Crash
        return state


async def assignment_ids(h: Harness, run_id: str) -> dict[str, set[str]]:
    """Every assignment id the ledger names, by entry kind."""
    stored = await h.stored(run_id)
    assert stored is not None
    named: dict[str, set[str]] = {}
    for entry in await h.entries(stored):
        if entry.refs.assignment_id is not None:
            named.setdefault(entry.kind, set()).add(entry.refs.assignment_id)
    return named


async def test_the_assignment_is_named_in_the_ledger_before_the_worker_is_asked() -> None:
    fake = FakeWorker(script=script())
    h = Harness(worker("do"), workers=[fake])
    seen: list[set[str]] = []

    async def before_the_post(assignment: Assignment) -> None:
        seen.append((await assignment_ids(h, "run_0001")).get("step.assigned", set()))

    fake.on_assign = before_the_post
    run = await h.start()
    assert run.state is RunState.FINISHED
    assert seen == [{"asg_0001"}], "step.assigned was committed before the post"
    kinds = await h.kinds(run)
    assert kinds[3:7] == [
        "step.admitted:do",
        "step.assigned:do",
        "step.started:do",
        "step.finished:do:succeeded",
    ]
    do = run.step_run("do")
    assert not do.assignment_open and do.assignment_seq > 0, "its end was read"


async def test_a_crash_between_acceptance_and_start_adopts_the_accepted_assignment() -> None:
    fake = DiesAfterAcceptance(script=script())
    h = Harness(worker("do"), workers=[fake])
    with pytest.raises(Crash):
        await h.start()
    left = await h.stored("run_0001")
    assert left is not None
    do = left.step_run("do")
    assert do.state is StepState.ADMITTED and do.assignment_open
    assert do.assignment_id == "asg_0001"
    assert "step.started:do" not in await h.kinds(left)

    run = await h.resume(left)
    assert run.state is RunState.FINISHED
    assert [a.assignment_id for a in fake.assignments] == ["asg_0001"], "nothing handed over twice"
    assert fake.stops == []
    kinds = await h.kinds(run)
    assert kinds.count("step.assigned:do") == 1
    assert "step.adopted:do:accepted" in kinds and "step.started:do" not in kinds
    assert await assignment_ids(h, run.id) == {
        "step.assigned": {"asg_0001"},
        "run.recovered": {"asg_0001"},
        "step.adopted": {"asg_0001"},
        "step.finished": {"asg_0001"},
    }
    do = run.step_run("do")
    assert [a.id for a in do.artifacts] == ["out-1", "out-2", "out-3"]
    assert do.consumption is not None and do.consumption.compute_seconds == 3.0
    assert await h.verify()


async def test_a_crash_while_the_step_runs_adopts_it_from_the_last_boundary() -> None:
    fake = FakeWorker(script=script())
    h = Harness(worker("do"), workers=[fake])

    async def die_inside_the_second_inner_step(event: Event) -> None:
        if event.type == "step.started" and event.seq == 5:  # boundary of "one" was seq 4
            raise Crash

    fake.on_event = die_inside_the_second_inner_step
    with pytest.raises(Crash):
        await h.start()
    left = await h.stored("run_0001")
    assert left is not None
    assert left.step_run("do").assignment_seq == 4
    fake.on_event = None

    run = await h.resume(left)
    assert run.state is RunState.FINISHED
    assert len(fake.assignments) == 1 and fake.stops == []
    assert fake.follows == [("asg_0001", 0), ("asg_0001", 4)], "read on after the boundary"
    do = run.step_run("do")
    assert [a.id for a in do.artifacts] == ["out-1", "out-2", "out-3"], "every output, once"
    assert do.consumption is not None and do.consumption.compute_seconds == 3.0, "counted once"
    kinds = await h.kinds(run)
    assert kinds.count("step.started:do") == 1 and kinds.count("step.adopted:do:accepted") == 1


async def test_an_assignment_that_never_reached_the_worker_is_posted_again_under_its_id() -> None:
    fake = FakeWorker(script=script())
    h = Harness(worker("do"), workers=[fake])

    async def die_before_the_post(assignment: Assignment) -> None:
        raise Crash

    fake.on_assign = die_before_the_post
    with pytest.raises(Crash):
        await h.start()
    left = await h.stored("run_0001")
    assert left is not None and left.step_run("do").assignment_open
    fake.on_assign = None

    run = await h.resume(left)
    assert run.state is RunState.FINISHED
    assert [a.assignment_id for a in fake.assignments] == ["asg_0001"]
    kinds = await h.kinds(run)
    assert kinds.count("step.assigned:do") == 2 and kinds.count("step.started:do") == 1
    assert "step.adopted:do" not in " ".join(kinds)


async def test_a_late_post_of_the_same_assignment_makes_the_recovering_post_adopt_it() -> None:
    """A runner cut off after `step.assigned` posts late, after the recovering runner asked
    and before it posted: the worker's 409 decides, and one assignment runs."""
    fake = FakeWorker(script=script())
    h = Harness(worker("do"), workers=[fake])
    late: list[Assignment] = []

    async def cut_off(assignment: Assignment) -> None:
        late.append(assignment)
        raise Crash

    fake.on_assign = cut_off
    with pytest.raises(Crash):
        await h.start()
    left = await h.stored("run_0001")
    assert left is not None

    async def the_late_post_lands_first(assignment: Assignment) -> None:
        fake.on_assign = None
        await fake.assign(late[0])

    fake.on_assign = the_late_post_lands_first
    run = await h.resume(left)
    assert run.state is RunState.FINISHED
    assert [a.assignment_id for a in fake.assignments] == ["asg_0001"], "the worker took one"
    assert "step.adopted:do:accepted" in await h.kinds(run)
    assert [a.id for a in run.step_run("do").artifacts] == ["out-1", "out-2", "out-3"]


async def test_a_worker_that_cannot_be_asked_fails_the_step_and_nothing_new_is_handed_over() -> (
    None
):
    fake = DiesAfterAcceptance(script=script())
    h = Harness(worker("do"), workers=[fake])
    with pytest.raises(Crash):
        await h.start()
    left = await h.stored("run_0001")
    assert left is not None
    fake.unreachable = "connection refused"

    run = await h.resume(left)
    assert run.state is RunState.ESCALATED and run.cause is Cause.FAILURE
    do = run.step_run("do")
    assert do.state is StepState.FAILED and do.assignment_open
    assert do.reason is not None and "asg_0001" in do.reason and "may still be running" in do.reason
    assert len(fake.assignments) == 1, "no second assignment"

    fake.unreachable = None
    run = await h.resume(run)
    assert run.state is RunState.FINISHED
    assert len(fake.assignments) == 1, "the resume adopted the first"


async def test_an_adopted_assignment_stopped_by_the_runner_that_gave_it_up_continues() -> None:
    fake = DiesAfterAcceptance(script=script())
    h = Harness(worker("do"), workers=[fake])
    with pytest.raises(Crash):
        await h.start()
    left = await h.stored("run_0001")
    assert left is not None
    # The dead runner's shutdown had asked the worker to stop at its next boundary.
    await fake.stop("asg_0001", StopRequest(reason="shutdown"))

    run = await h.resume(left)
    assert run.state is RunState.FINISHED, "a stop this runner did not ask for stops no run"
    assert [a.assignment_id for a in fake.assignments] == ["asg_0001", "asg_0002"]
    assert fake.assignments[1].context.checkpoint_ref == "ckpt/asg_0001/0"
    assert [a.id for a in run.step_run("do").artifacts] == ["out-1", "out-2", "out-3"]


async def test_a_stream_that_breaks_off_asks_for_a_stop_and_a_resume_adopts_the_rest() -> None:
    fake = FakeWorker(script=script())
    h = Harness(worker("do"), workers=[fake])

    async def break_after_the_first_boundary(event: Event) -> None:
        if event.type == "step.started" and event.seq == 5:
            raise WorkerError("the stream broke off")

    fake.on_event = break_after_the_first_boundary
    run = await h.start()
    assert run.state is RunState.ESCALATED
    do = run.step_run("do")
    assert do.state is StepState.FAILED and do.assignment_open
    assert [s[0] for s in fake.stops] == ["asg_0001"], "no run follows it: it is asked to stop"
    fake.on_event = None

    run = await h.resume(run)
    assert run.state is RunState.FINISHED
    assert "step.adopted:do:stopping" in await h.kinds(run)
    assert [a.id for a in run.step_run("do").artifacts] == ["out-1", "out-2", "out-3"]
    assert run.step_run("do").consumption is not None
    assert run.step_run("do").consumption.compute_seconds == 3.0
