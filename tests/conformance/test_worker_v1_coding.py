"""The suite against the coding worker, in both authentication modes and with every fault.

The worker is run against the fake agent (`workers/claudecode/fake_agent.py`), which speaks the
real agent's stream and does what its calls say, so that the worker's mechanics — boundaries,
consumption per step, refusal, stop and resume, authentication — are proven without a
subscription and deterministically. The real agent is not exercised here. Its live test is
`tests/workers/test_coding_worker_live.py` (#68): one file in an empty workspace, through
`taktusctl run`, under the cap per run of the environment `live`. It runs in the workflow
`live` on `main`, monthly and by dispatch, never on a pull request (DEC-0048, DEC-0058), and
skips wherever the key and the cap are not both set. Until it was written, this description
named a live test that did not exist (DEC-0046).
"""

from __future__ import annotations

from dataclasses import replace
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


@pytest.mark.parametrize("late", [False, True], ids=["streamed", "in-the-total"])
async def test_the_reported_output_is_every_message_once(
    start_coding_worker: StartWorker, late: bool
) -> None:
    """The fake agent streams each of its seven messages in two lines; the first carries a
    twentieth of the message's output, the last all of it — or, late, still the twentieth, and
    only the session total in the final line holds the rest. Either way the worker reports the
    output of every message once: 40 + n for the calls n = 1..6 and for the closing message
    n = 99 — not the first line's, not both lines' (#278)."""
    agent_env = {"FAKE_AGENT_LATE_USAGE": "1"} if late else {}
    worker = start_coding_worker(auth="api-key", agent_env=agent_env)
    events = await one_assignment(worker)
    assert events[-1]["outcome"] == "succeeded"
    reported = [e for e in events if e["type"] == "consumption.reported"]
    assert sum(e.get("tokens_out", 0) for e in reported) == sum(40 + n for n in [*range(1, 7), 99])


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


async def test_money_is_reported_per_step_and_a_money_limit_halts_at_the_boundary(
    start_coding_worker: StartWorker,
) -> None:
    """Every step reports its tokens per model and price kind, and their money at the worker's
    price table; the running total of money is held at every boundary (DEC-0202). With the
    fake agent's usage a hundredfold, its steps cost about 0.29, 0.36 and 0.43 usd at the
    prices of the model it names: under 1 usd the worker halts at the boundary of the third,
    names the limit `currency`, and keeps the checkpoint. The resume continues from it."""
    worker = start_coding_worker(auth="api-key", agent_env={"FAKE_AGENT_USAGE_FACTOR": "100"})
    events = await one_assignment(worker, limits={"currency": {"usd": 1.0}})
    finished = events[-1]
    assert finished["outcome"] == "stopped" and finished["limit"] == "currency", finished
    reported = [e for e in events if e["type"] == "consumption.reported"]
    assert all("currency" in e for e in reported), "money at every boundary"
    agent = [e for e in reported if e.get("tokens_by_model")]
    assert agent and all(set(e["tokens_by_model"]) == {"claude-haiku-4-5-20251001"} for e in agent)
    first = agent[0]["tokens_by_model"]["claude-haiku-4-5-20251001"]
    assert first == {"input": 300, "cache_read": 500000, "cache_write": 110000, "output": 4100}
    assert agent[0]["currency"]["usd"] == round((300 + 50000 + 220000 + 20500) / 1e6, 6)
    money = [e["currency"]["usd"] for e in reported]
    assert sum(money) >= 1.0 and sum(money[:-1]) < 1.0, "halted at the boundary that reached it"
    boundaries = [e for e in events if e["type"] == "step.boundary"]
    assert boundaries[-1]["checkpoint_ref"] == finished["checkpoint_ref"]
    assert boundaries[-1]["seq"] == finished["seq"] - 1, "no step started after the boundary"
    resumed = await one_assignment(
        worker, assignment_id="asg_resume03", checkpoint_ref=finished["checkpoint_ref"]
    )
    assert resumed[-1]["outcome"] == "succeeded"
    before = {e["artifact_id"] for e in events if e["type"] == "artifact.produced"}
    after = {e["artifact_id"] for e in resumed if e["type"] == "artifact.produced"}
    assert before and not before & after


async def test_an_agent_at_its_limit_of_turns_stops_at_its_boundary_and_resumes(
    start_coding_worker: StartWorker,
) -> None:
    """#380: the agent ends on its limit of turns, two here, with an error and no text. The
    assignment ends `stopped` at the last boundary with its checkpoint, not `failed`, names no
    limit of the assignment's, and reports the money the agent's result holds beyond its
    steps. Each resume continues the same session for two more turns until the work is done;
    nothing is done or announced twice."""
    worker = start_coding_worker(auth="api-key", agent_env={"CODING_AGENT_MAX_TURNS": "2"})
    events = await one_assignment(worker)
    finished = events[-1]
    assert finished["outcome"] == "stopped", finished
    assert "limit" not in finished and "limit of 2 turns" in finished["reason"]
    boundaries = [e for e in events if e["type"] == "step.boundary"]
    assert boundaries[-1]["checkpoint_ref"] == finished["checkpoint_ref"]
    reported = [e for e in events if e["type"] == "consumption.reported"]
    priced = sum(e["currency"]["usd"] for e in reported[:-1])
    assert reported[-1]["currency"]["usd"] == round(0.04 - priced, 6), "the agent's own total"
    seen = {e["artifact_id"] for e in events if e["type"] == "artifact.produced"}
    outcomes = []
    checkpoint = finished["checkpoint_ref"]
    for n in range(1, 4):
        resumed = await one_assignment(
            worker, assignment_id=f"asg_turns{n:02d}", checkpoint_ref=checkpoint
        )
        produced = {e["artifact_id"] for e in resumed if e["type"] == "artifact.produced"}
        assert not produced & seen, "nothing announced twice"
        seen |= produced
        outcomes.append(resumed[-1]["outcome"])
        if resumed[-1]["outcome"] != "stopped":
            break
        checkpoint = resumed[-1]["checkpoint_ref"]
    assert outcomes == ["stopped", "succeeded"], outcomes
    assert {"summary", "changeset"} <= seen and any(i.startswith("change-") for i in seen)


FETCHED = {"FAKE_AGENT_FETCH": f"https://{HOST}/index.json"}
"""The agent fetches a page of the host the suite allows, as the real agent did on the instance:
the host is named by the agent's call, not by the task (#424)."""


def fetching(worker: RunningWorker) -> RunningWorker:
    """The suite run against an agent that reaches its host itself: a task that names no host,
    and the host the suite allows in `main` and withdraws in `narrowed-hosts`."""
    task = {k: v for k, v in TASK.items() if k != "inputs"}
    return replace(worker, task=task, hosts=(HOST,))


async def test_a_tool_and_a_host_not_offered_pass_by_the_stated_reach(
    start_coding_worker: StartWorker,
) -> None:
    """Since #425 the agent is offered only the frame's tools, and no fetch where no host may
    be reached. In the narrowed runs it therefore never calls the fetch the suite withdrew, and
    no refusal can be observed: the suite ended `incomplete` against the real agent. The worker
    states its reach before the work begins (ADR-0098), and W-07 and W-13 pass on that
    statement and on the absence of any call to what it leaves out."""
    worker = fetching(start_coding_worker(agent_env=FETCHED))
    report = await worker.run_suite()
    assert report.failed == [] and report.inconclusive == [], report.render()
    checks = {c.id: c for c in report.checks}
    assert "did not offer 'web.fetch'" in checks["W-07"].observed, checks["W-07"].observed
    assert f"did not put {HOST!r} within reach" in checks["W-13"].observed
    runs = {r.purpose: r for r in report.runs}
    assert runs["narrowed"].outcome == "succeeded"
    assert runs["narrowed-hosts"].outcome == "succeeded"
    events = await one_assignment(worker)
    assert events[0]["type"] == "reach.stated" and "web.fetch" in events[0]["tools"]
    assert "hosts" not in events[0], "a fetch is offered: the hosts are bounded at the call"


@pytest.mark.parametrize("fault", ["W-07", "W-13"])
async def test_a_worker_that_offers_what_the_frame_took_out_and_does_not_refuse_still_fails(
    start_coding_worker: StartWorker, fault: str
) -> None:
    """The statement passes a check only where it leaves the tool or the host out and no call
    to it occurred. A worker that offers the withdrawn fetch, states so, and lets the agent's
    call through unrefused fails the check exactly as before (#424)."""
    worker = fetching(start_coding_worker(fault=fault, agent_env=FETCHED))
    report = await worker.run_suite()
    assert {c.id for c in report.failed} == {fault}, report.render()


PARALLEL = {"FAKE_AGENT_PARALLEL": "1"}
"""The agent makes two calls in one message, both before either result, as the real agent did
on the instance on 2026-10-15: the suite failed W-04 for the first call of such a pair."""


@pytest.mark.parametrize("order", ["1", "reversed"], ids=["in-order", "reversed"])
async def test_calls_made_in_parallel_are_steps_one_after_the_other(
    start_coding_worker: StartWorker, order: str
) -> None:
    """A message with two calls was two steps open at once: the second call replaced the first
    as the running step, the first result closed the second, and the first never reported its
    consumption (W-04). Each call is a step of its own, in the agent's order: the next starts
    once the one before has reported its consumption and reached its boundary, also where
    the later call's result arrives first."""
    worker = fetching(start_coding_worker(agent_env={**FETCHED, "FAKE_AGENT_PARALLEL": order}))
    report = await worker.run_suite()
    assert report.failed == [] and report.inconclusive == [], report.render()
    events = await one_assignment(worker)
    assert events[-1]["outcome"] == "succeeded"
    started = [e["step_id"] for e in events if e["type"] == "step.started"]
    reported = [e["step_id"] for e in events if e["type"] == "consumption.reported"]
    assert started == reported[: len(started)], "every step reports before the next starts"
    tools = [e["summary"].split(":")[0] for e in events if e["type"] == "step.started"]
    plan = ["WebFetch", "Glob", "Write", "Bash", "Read", "Edit", "Bash"]
    assert tools[1:8] == plan, "every call of the agent a step, in the agent's order"


async def test_a_stop_between_calls_made_in_parallel_lands_on_a_boundary(
    start_coding_worker: StartWorker,
) -> None:
    """With two calls in every message, the suite's stop still lands on a boundary with its
    checkpoint (W-06), and the resume from it announces nothing twice (W-11): a call that
    waits for the running step is no step yet, and a stop there leaves it unannounced."""
    worker = start_coding_worker(agent_env=PARALLEL)
    report = await worker.run_suite()
    assert report.failed == [], report.render()
    runs = {r.purpose: r for r in report.runs}
    assert runs["stopped"].outcome == "stopped" and runs["resumed"].outcome == "succeeded"
