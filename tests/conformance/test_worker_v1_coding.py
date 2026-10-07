"""The suite against the coding worker, in both authentication modes and with every fault.

The worker is run against the fake agent (`workers/claudecode/fake_agent.py`), which speaks the
real agent's stream and does what its calls say, so that the worker's mechanics — boundaries,
consumption per step, refusal, stop and resume, authentication — are proven without a
subscription and deterministically. The real agent is not exercised here: a live test against
it is written when CI has a key of its own for the agent (NEED-0012, DEC-0046). Until then a
live run with `tools/first_run.sh` is the only check against the real agent.
"""

from __future__ import annotations

from typing import Any

import pytest

from taktus.conformance import Status
from taktus.conformance.client import WorkerClient
from taktus.conformance.rules import CHECKS

from .conftest import HOST, TASK, RunningWorker, StartWorker, coding_faults

type Json = dict[str, Any]
FAULTS = coding_faults()


async def one_assignment(
    worker: RunningWorker,
    *,
    assignment_id: str = "asg_coding01",
    checkpoint_ref: str | None = None,
    credential: str | None = None,
    limits: Json | None = None,
) -> list[Json]:
    """Post one assignment in a frame that allows everything the worker offers, and read its
    stream to the end: the events, for assertions the report does not carry."""
    async with WorkerClient(worker.endpoint, timeout=90.0, idle_timeout=30.0) as client:
        declared = (await client.get("/v1/capabilities")).json or {}
        context: Json = {}
        if checkpoint_ref is not None:
            context["checkpoint_ref"] = checkpoint_ref
        accepted = await client.post(
            "/v1/assignments",
            {
                "assignment_id": assignment_id,
                "task": dict(TASK),
                "context": context,
                "frame": {
                    "autonomy_level": 2,
                    "allowed_tools": list(declared["capabilities"]),
                    "allowed_hosts": [HOST],
                    "max_steps": 40,
                },
                "limits": limits or {"currency": {"usd": 5.0}, "quota": {"units": 50}},
                "credentials": [
                    {"name": credential or worker.credential_name, "injected_as": "env"}
                ],
                "callback": {"events": "sse"},
            },
        )
        assert accepted.status == 201, accepted.text
        stream = await client.stream(assignment_id)
        assert not stream.problems, stream.problems
        return stream.events


@pytest.mark.parametrize("auth", ["api-key", "session"])
async def test_the_coding_worker_passes_in_both_authentication_modes(
    start_coding_worker: StartWorker, auth: str
) -> None:
    worker = start_coding_worker(auth=auth)
    report = await worker.run_suite()
    statuses = {c.id: c.status for c in report.checks}
    assert report.failed == [], report.render()
    assert report.inconclusive == [], report.render()
    assert statuses.pop("W-12") is Status.PENDING
    assert set(statuses.values()) == {Status.PASSED}
    runs = {r.purpose: r for r in report.runs}
    assert runs["stopped"].outcome == "stopped" and runs["resumed"].outcome == "succeeded"
    assert runs["tight"].outcome == "stopped", "the fake agent overruns; the limit halts it"
    assert worker.credential_value not in report.to_json()
    assert worker.credential_value not in worker.log.read_text()
    events = await one_assignment(worker)
    kinds = {e["type"] for e in events}
    assert {"step.started", "tool.called", "consumption.reported", "step.boundary"} <= kinds
    patches = [e for e in events if e["type"] == "artifact.produced" and e["kind"] == "patch"]
    assert patches, "every step that changed the workspace produced its change as a patch"
    reported = [e for e in events if e["type"] == "consumption.reported"]
    quantity = "currency" if auth == "api-key" else "quota_units"
    assert any(quantity in e for e in reported), f"{auth} settles in {quantity}"
    assert events[-1]["outcome"] == "succeeded"


def test_every_runtime_check_has_a_fault() -> None:
    broken = {check for _, check in FAULTS}
    assert broken == set(CHECKS) - {"W-12"}


@pytest.mark.parametrize(("fault", "check"), FAULTS, ids=[f for f, _ in FAULTS])
async def test_fault_fails_exactly_its_check(
    start_coding_worker: StartWorker, fault: str, check: str
) -> None:
    worker = start_coding_worker(fault=fault)
    report = await worker.run_suite()
    failed = {c.id for c in report.failed}
    assert failed == {check}, report.render()
    for other in report.checks:
        if other.id != check:
            assert other.status in {Status.PASSED, Status.INCONCLUSIVE, Status.PENDING}
    assert report.exit_code == 1


async def test_a_session_that_expires_mid_run_halts_at_the_boundary(
    start_coding_worker: StartWorker,
) -> None:
    """The agent's token stops working after the second tool call: the assignment ends
    `stopped` at the last boundary with the cause, and the resumed one continues from there
    once the credential works again. Not an abort, not a silent retry."""
    worker = start_coding_worker(auth="session", agent_env={"FAKE_AGENT_EXPIRE_AFTER": "2"})
    events = await one_assignment(worker)
    finished = events[-1]
    assert finished["type"] == "assignment.finished" and finished["outcome"] == "stopped"
    assert "authentication" in finished["reason"] and "expired" in finished["reason"].lower()
    assert finished["checkpoint_ref"].startswith("ckpt/")
    boundaries = [e for e in events if e["type"] == "step.boundary"]
    assert boundaries and boundaries[-1]["checkpoint_ref"] == finished["checkpoint_ref"]
    starts = [e for e in events if e["type"] == "step.started"]
    assert len(starts) == 3, "the hosts step and two tool calls, then the token expired"
    # Resumed from that checkpoint, the agent continues after its second call.
    resumed = await one_assignment(
        worker, assignment_id="asg_resume01", checkpoint_ref=finished["checkpoint_ref"]
    )
    assert resumed[-1]["outcome"] == "succeeded"
    ids = [e["artifact_id"] for e in resumed if e["type"] == "artifact.produced"]
    assert "change-2" not in ids and any(i.startswith("change-") for i in ids)


async def test_an_exhausted_window_blocks_at_the_boundary(start_coding_worker: StartWorker) -> None:
    worker = start_coding_worker(auth="session", agent_env={"FAKE_AGENT_WINDOW_AFTER": "1"})
    events = await one_assignment(worker)
    finished = events[-1]
    assert finished["outcome"] == "stopped" and "window" in finished["reason"]


async def test_an_assignment_that_does_not_name_the_credential_is_rejected_before_it_starts(
    start_coding_worker: StartWorker,
) -> None:
    """The worker never assumes a login: an assignment that does not reference the credential
    its authentication needs is rejected with the name of what is missing — before the agent
    is started, and although the worker's own environment happens to carry it."""
    worker = start_coding_worker(auth="api-key")
    events = await one_assignment(worker, credential="SOMETHING_ELSE")
    assert events[-1]["outcome"] == "rejected"
    assert "CODING_AGENT_API_KEY" in events[-1]["reason"]
    assert len(events) == 1


async def test_a_token_limit_halts_at_the_boundary_and_the_resume_continues(
    start_coding_worker: StartWorker,
) -> None:
    """The reservation is the worker's hard ceiling. The fake agent's calls use about 6 000 to
    32 000 input tokens each; under a limit equal to the estimate, 60 000, the worker ends the
    agent at the first boundary where the running total has reached it — the call that
    crossed it is the one step the limit yields by — and finishes `stopped` with the
    checkpoint and `limit`. The resumed assignment, with a limit of its own, continues from
    there and repeats nothing."""
    worker = start_coding_worker(auth="api-key")
    limits: Json = {"currency": {"usd": 5.0}, "tokens": {"in": 60000}}
    events = await one_assignment(worker, limits=limits)
    finished = events[-1]
    assert finished["outcome"] == "stopped" and finished["limit"] == "tokens", finished
    boundaries = [e for e in events if e["type"] == "step.boundary"]
    assert boundaries[-1]["checkpoint_ref"] == finished["checkpoint_ref"]
    assert boundaries[-1]["seq"] == finished["seq"] - 1, "no step started after the boundary"
    reported = [e for e in events if e["type"] == "consumption.reported"]
    used = sum(e.get("tokens_in", 0) for e in reported)
    assert used >= 60000
    assert used - reported[-1]["tokens_in"] < 60000, "the limit was reached with the last step"
    resumed = await one_assignment(
        worker, assignment_id="asg_resume02", checkpoint_ref=finished["checkpoint_ref"]
    )
    assert resumed[-1]["outcome"] == "succeeded"
    before = {e["artifact_id"] for e in events if e["type"] == "artifact.produced"}
    after = {e["artifact_id"] for e in resumed if e["type"] == "artifact.produced"}
    assert before and not before & after


async def test_an_agent_within_its_estimate_leaves_w14_inconclusive(
    start_coding_worker: StartWorker,
) -> None:
    """With the fake agent's usage scaled down it never exceeds the worker's estimate, and no
    limit the estimate fits can be crossed: the suite says so instead of claiming a pass."""
    worker = start_coding_worker(agent_env={"FAKE_AGENT_USAGE_FACTOR": "0.01"})
    report = await worker.run_suite()
    w14 = next(c for c in report.checks if c.id == "W-14")
    assert w14.status is Status.INCONCLUSIVE, report.render()
    assert "never exceeded the estimate" in w14.observed
    assert report.failed == []
