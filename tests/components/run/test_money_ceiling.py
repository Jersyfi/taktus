"""A worker's money is the run's: its ceiling, and what admission reserves for it (DEC-0202).

ADR-0005, seventh amendment. A worker that reports money per step halts at its boundary
before it crosses what is left of the run's money, not at its own reservation; a halted step
keeps its checkpoint, and a person resumes it with a raised limit from there. A worker step
whose own estimate fits is admitted with its calibrated reservation cut to what is left,
never refused for the error another step of the same worker once made.
"""

from __future__ import annotations

from fakes import FakeWorker, InnerStep

from taktus.components.run.domain.model import Cause, RunState, StepState
from taktus.ports.worker import Limits

from .test_engine import Harness, worker


def spending(*usd: float, estimate: float = 1.0) -> FakeWorker:
    return FakeWorker(
        estimate_usd=estimate,
        script=tuple(InnerStep(f"inner-{n}", usd=amount) for n, amount in enumerate(usd, 1)),
    )


async def test_a_worker_may_use_what_is_left_of_the_runs_money_not_only_its_reservation() -> None:
    """Estimated at 1 usd and using 2.4: with its reservation as its ceiling it halted at 1.6
    and needed a person, although the run had 5 usd for it."""
    fake = spending(0.8, 0.8, 0.8)
    h = Harness(worker("do"), workers=[fake])
    run = await h.start(Limits(currency={"usd": 5.0}))
    assert run.state is RunState.FINISHED
    assert fake.assignments[-1].limits.currency == {"usd": 5.0}
    reservation = run.step_run("do").reservation
    assert reservation is not None and reservation.currency == {"usd": 1.0}, "admission as before"


async def test_at_the_runs_limit_the_worker_halts_keeps_its_work_and_a_person_resumes_it() -> None:
    """2 usd for four steps of 0.75: the third crosses the line and is the one inner step the
    limit yields by. The run halts with cause `limit` — a runner completes its job, nothing
    restarts it — and the step keeps its checkpoint. Resumed with 4 usd, it continues after
    the third step, with the money left as its ceiling."""
    fake = spending(0.75, 0.75, 0.75, 0.75)
    h = Harness(worker("do"), workers=[fake])
    run = await h.start(Limits(currency={"usd": 2.0}))
    assert run.state is RunState.HALTED and run.cause is Cause.LIMIT
    do = run.step_run("do")
    assert do.state is StepState.STOPPED and do.checkpoint is not None
    assert do.consumption is not None and do.consumption.currency == {"usd": 2.25}
    halted_at = do.checkpoint.ref

    resumed = await h.resume(run, budget=Limits(currency={"usd": 4.0}))
    assert resumed.state is RunState.FINISHED
    again = fake.assignments[-1]
    assert again.context.checkpoint_ref == halted_at, "from its checkpoint, not from the start"
    assert again.limits.currency is not None
    assert round(again.limits.currency["usd"], 6) == 1.75, "what is left of 4 usd after 2.25"
    assert len(fake.assignments) == 2


async def test_a_step_whose_estimate_fits_is_admitted_with_what_is_left_reserved() -> None:
    """The first run measures the worker at 4.5 times its estimate. Under 3 usd its calibrated
    reservation, 4.5, does not fit, its estimate of 1 does: it is admitted with 3 reserved,
    halts at the line, and the ledger says the reservation was capped. An estimate that does
    not fit is still refused."""
    fake = spending(1.5, 1.5, 1.5)
    h = Harness(worker("do"), workers=[fake])
    measured = await h.start(Limits(currency={"usd": 10.0}))
    assert measured.state is RunState.FINISHED

    capped = await h.start(Limits(currency={"usd": 3.0}))
    do = capped.step_run("do")
    assert do.reservation is not None and do.reservation.currency == {"usd": 3.0}
    assert "step.reserved:do:capped" in await h.kinds(capped)
    assert capped.state is RunState.HALTED and capped.cause is Cause.LIMIT
    assert do.state is StepState.STOPPED and do.checkpoint is not None

    refused = await h.start(Limits(currency={"usd": 0.5}))
    assert refused.state is RunState.HALTED and refused.cause is Cause.LIMIT
    assert refused.step_run("do").state is StepState.REJECTED


async def test_a_run_halts_at_the_step_boundary_where_its_money_is_spent_not_at_its_end() -> None:
    """The beta condition "a budget that holds during a run" (docs/roadmap.md, ADR-0005): three
    steps of 0.75 usd under 2 usd. The first two finish; the third does not fit what is left and
    never starts. The run halts there with cause `limit`, before its last step, and the ledger
    holds nothing of the third step but its refusal."""
    fake = spending(0.75)
    h = Harness(worker("a"), worker("b", after=("a",)), worker("c", after=("b",)), workers=[fake])
    run = await h.start(Limits(currency={"usd": 2.0}))
    assert run.state is RunState.HALTED and run.cause is Cause.LIMIT
    assert [run.step_run(s).state for s in ("a", "b")] == [StepState.SUCCEEDED] * 2
    assert run.step_run("c").state is StepState.REJECTED
    assert len(fake.assignments) == 2, "the third step was never handed to the worker"
    kinds = await h.kinds(run)
    assert "step.started:c" not in kinds
    assert kinds[-2:] == ["step.rejected:c:rejected_by_admission", "run.halted::limit"]
