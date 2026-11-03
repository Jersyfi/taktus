"""A replay of a recorded run (ADR-0108), seen from the engine and from the comparison.

An engine given a replay resolves every rehearsal from it: an outward operation goes to the
replay and never to a configured connector, finishes `rehearsed` and writes no egress. Such a
rehearsal asks its step boundaries as any run does — an anchor halts it at the step, where a
rehearsal from the tenant's recordings asks none (NTC-0079). The comparison reads whether the
replayed run came where the recorded one came, step by step.
"""

from __future__ import annotations

from collections.abc import Sequence

from fakes import VERIFIED, FakeConnector
from fakes.connector import READ, WRITE

from components.run.test_connector_steps import ConnectorHarness, call
from components.run.test_engine import AT, BUDGET, TENANT, Harness, rule
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Cause, Run, RunState, StepState
from taktus.components.run.domain.service.replay import RecordedEnd, RecordedStep, differences
from taktus.components.run.ports import Draft, Verdict
from taktus.shared.v1 import Anchor


class Recorded:
    """A replay over fakes: what the engine resolves a rehearsal from."""

    def __init__(self, connector: FakeConnector) -> None:
        self.workers = StaticWorkerPool([])
        self.connectors = StaticConnectorPool([("connector.recorded", connector)])
        self.models = StaticModelPool()


class AnchorOnWrites:
    async def ceilings(self, tenant: str, actions: Sequence[str]) -> dict[str, int]:
        return {}

    async def applying(
        self, tenant: str, process: str, actions: Sequence[str]
    ) -> tuple[Anchor, ...]:
        if WRITE not in actions:
            return ()
        return (
            Anchor.model_validate(
                {
                    "id": "anc-write",
                    "class": "legal",
                    "act": "a write",
                    "applies_to": {"actions": [WRITE]},
                    "decider": {"role": "owner"},
                }
            ),
        )


class Requests:
    def __init__(self) -> None:
        self.raised: list[Draft] = []

    async def raise_request(self, tenant: str, draft: Draft) -> None:
        self.raised.append(draft)

    async def verdict(self, tenant: str, request_id: str) -> Verdict | None:
        return Verdict(applied=False)


def harness(
    *, anchored: bool = False
) -> tuple[ConnectorHarness, FakeConnector, RunEngine, Requests]:
    h = ConnectorHarness(
        call("read", READ, {"id": "issue-1"}),
        call(
            "write", WRITE, {"title": {"$from": "read", "$select": "output.title"}}, after=("read",)
        ),
    )
    recorded = FakeConnector(reads={"issue-1": {"id": "issue-1", "title": "As recorded"}})
    requests = Requests()
    engine = RunEngine(
        runs=h.runs,
        work=h.persistence,
        objects=h.objects,
        ledger=h.ledger,
        provenance=h.provenance,
        workers=StaticWorkerPool([]),
        clock=h.clock,
        ids=h.ids,
        telemetry=h.engine._telemetry,
        connectors=StaticConnectorPool([("connector.fake", h.connector)]),
        replay=Recorded(recorded),
        maturities=VERIFIED,
        anchors=AnchorOnWrites() if anchored else None,
        decisions=requests if anchored else None,
    )
    return h, recorded, engine, requests


async def start(h: ConnectorHarness, engine: RunEngine, *, rehearsal: bool = True) -> Run:
    return await engine.start(
        StartRun(
            plan=h.plan(),
            work=h.work,
            budget=BUDGET,
            process_version="p@1",
            actor="idn_t",
            tenant=TENANT,
            rehearsal=rehearsal,
        )
    )


async def test_a_replay_sends_every_call_to_its_recording_and_nothing_outside() -> None:
    h, recorded, engine, _ = harness()
    run = await start(h, engine)
    assert run.state is RunState.FINISHED, run.reason
    assert h.connector.calls == [], "the configured connector is never asked"
    assert [operation for operation, _, _ in recorded.calls] == [READ, WRITE]
    assert recorded.calls[1][2] == {"title": "As recorded"}, "what was read went on"
    kinds = await h.kinds(run)
    assert "step.finished:write:rehearsed" in kinds and "step.finished:read:succeeded" in kinds
    assert not [k for k in kinds if k.startswith("egress.")], "nothing left the system"
    assert all(e.rehearsal is True for e in await h.entries(run))
    assert run.step_run("write").adapter == "connector.recorded"


async def test_a_run_that_is_not_a_rehearsal_is_never_answered_by_the_replay() -> None:
    h, recorded, engine, _ = harness()
    h.connector.reads["issue-1"] = {"id": "issue-1", "title": "Real"}
    run = await start(h, engine, rehearsal=False)
    assert run.state is RunState.FINISHED
    assert recorded.calls == [] and h.connector.acted == 1


async def test_a_replay_asks_its_anchors_and_waits_at_the_anchored_step() -> None:
    h, recorded, engine, requests = harness(anchored=True)
    run = await start(h, engine)
    assert run.state is RunState.WAITING_HUMAN, run.reason
    assert run.step_run("write").state is StepState.WAITING_HUMAN
    assert [d.step for d in requests.raised] == ["write"]
    assert [operation for operation, _, _ in recorded.calls] == [READ], (
        "nothing is decided for a person"
    )


def recorded(**states: str) -> list[RecordedStep]:
    return [RecordedStep(step_id=k, state=StepState(v)) for k, v in states.items()]


def a_run(states: dict[str, StepState], state: RunState, cause: Cause | None = None) -> Run:
    """A run of three rules, `b` after `a` and `c` after `b`, in the given states."""
    h = Harness(
        rule("a", {"rule": "constant", "value": 1}),
        rule("b", {"rule": "constant", "value": 1}, after=("a",)),
        rule("c", {"rule": "constant", "value": 1}, after=("b",)),
    )
    run = Run(
        id="run_1",
        plan_id="pln_1",
        process_version="p@1",
        tenant=TENANT,
        identity="idn_t",
        autonomy_level=3,
        budget=BUDGET,
        steps=h.plan().steps,
        work=h.work,
        created_at=AT,
        updated_at=AT,
    )
    return run.model_copy(
        update={
            "state": state,
            "cause": cause,
            "step_runs": tuple(
                s.model_copy(update={"state": states.get(s.step_id, StepState.PLANNED)})
                for s in run.step_runs
            ),
        }
    )


FINISHED = RecordedEnd(state=RunState.FINISHED)
DONE = {"a": StepState.SUCCEEDED, "b": StepState.SUCCEEDED, "c": StepState.SUCCEEDED}


def test_a_replay_that_came_where_its_recording_came_differs_in_nothing() -> None:
    steps = recorded(a="succeeded", b="succeeded", c="succeeded")
    assert differences(steps, FINISHED, a_run(DONE, RunState.FINISHED)) == ()


def test_every_difference_names_its_step() -> None:
    steps = recorded(a="succeeded", b="succeeded", c="succeeded", gone="succeeded")
    run = a_run(
        {"a": StepState.SUCCEEDED, "b": StepState.FAILED}, RunState.ESCALATED, Cause.FAILURE
    )
    found = differences(steps, FINISHED, run)
    assert found == (
        "b: recorded succeeded, replayed failed",
        "c: recorded succeeded, replayed planned",
        "gone: recorded succeeded, and the bundle no longer has the step",
        "the run: recorded finished, replayed escalated (failure)",
    )


def test_a_step_the_recording_does_not_know_is_a_difference() -> None:
    steps = recorded(a="succeeded", b="succeeded")
    (line,) = differences(steps, FINISHED, a_run(DONE, RunState.FINISHED))
    assert line.startswith("c: the recording has no such step")


def test_a_step_that_waits_for_a_person_as_recorded_has_reached_its_boundary() -> None:
    """What comes after it is not reached in a replay, which decides nothing for a person."""
    steps = [
        RecordedStep(step_id="a", state=StepState.SUCCEEDED),
        RecordedStep(step_id="b", state=StepState.SUCCEEDED, met_a_person=True),
        RecordedStep(step_id="c", state=StepState.SUCCEEDED),
    ]
    run = a_run({"a": StepState.SUCCEEDED, "b": StepState.WAITING_HUMAN}, RunState.WAITING_HUMAN)
    assert differences(steps, FINISHED, run) == ()
    unrecorded = [s.model_copy(update={"met_a_person": False}) for s in steps]
    assert (
        differences(unrecorded, FINISHED, run)[0] == "b: recorded succeeded, replayed waiting_human"
    )
