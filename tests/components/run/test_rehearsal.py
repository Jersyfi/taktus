"""Rehearsal runs (ADR-0030), against the fake connector with a memory: an outward operation is
never sent; the step answers with the recorded response of the last real call, finishes
`rehearsed`, writes no egress entry, and every ledger entry of the run says it is a rehearsal.
Reads are real. A recording is never taken from a rehearsal, and none at all is a failed step.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from fakes.connector import READ, WRITE

from components.run.test_connector_steps import ConnectorHarness, call
from components.run.test_engine import AT, BUDGET, TENANT
from taktus.components.governance.domain.model import ResultRef
from taktus.components.governance.domain.service.egress import left_the_system
from taktus.components.run.application.query import ProvenanceOfRun, ProvenanceQuery
from taktus.components.run.application.service import StartRun
from taktus.components.run.domain.model import (
    Checkpoint,
    Run,
    RunState,
    StepState,
)
from taktus.components.run.domain.service.rehearsal import recording
from taktus.shared.v1 import InputKind, LedgerEntry, LedgerRefs, Step


async def start(h: ConnectorHarness, *, rehearsal: bool) -> Run:
    return await h.engine.start(
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


async def result_of(h: ConnectorHarness, run: Run, step: str) -> dict[str, object]:
    checkpoint = run.step_run(step).checkpoint
    assert checkpoint is not None and checkpoint.result_digest is not None
    content = await h.objects.get(checkpoint.result_digest)
    document: dict[str, object] = json.loads(content or b"null")
    return document


def process() -> ConnectorHarness:
    """A read, then a write that carries what was read: the shape of every real process here."""
    h = ConnectorHarness(
        call("read", READ, {"id": "issue-1"}),
        call(
            "write",
            WRITE,
            {"title": {"$from": "read", "$select": "output.title"}},
            after=("read",),
        ),
    )
    h.connector.reads["issue-1"] = {"id": "issue-1", "title": "Pin the model"}
    return h


async def test_a_rehearsal_answers_an_outward_call_from_the_last_real_one_and_sends_nothing() -> (
    None
):
    h = process()
    real = await start(h, rehearsal=False)
    assert real.state is RunState.FINISHED and h.connector.acted == 1
    calls_before = len(h.connector.calls)

    rehearsed = await start(h, rehearsal=True)
    assert rehearsed.state is RunState.FINISHED, rehearsed.reason
    assert rehearsed.rehearsal
    assert h.connector.acted == 1, "nothing outside was acted on"
    sent = [operation for operation, _, _ in h.connector.calls[calls_before:]]
    assert sent == [READ], "the read is real; the write was never sent"

    real_write = await result_of(h, real, "write")
    replayed = await result_of(h, rehearsed, "write")
    assert replayed["output"] == real_write["output"]
    assert replayed["effect"] == real_write["effect"]
    assert replayed["rehearsed_from"] == {"run_id": real.id, "step_id": "write"}
    assert rehearsed.step_run("write").consumption is None, "a replay consumes nothing"
    assert rehearsed.step_run("write").adapter == "connector.fake"

    entries = await h.entries(rehearsed)
    assert entries and all(e.rehearsal is True for e in entries), "every entry says so"
    assert not [e for e in await h.entries(real) if e.rehearsal], "a real run's entries do not"
    kinds = await h.kinds(rehearsed)
    assert "step.finished:write:rehearsed" in kinds
    assert "step.finished:read:succeeded" in kinds
    assert not [k for k in kinds if k.startswith("egress.")], "nothing left the system"
    assert await h.verify()

    # The provenance names the recording as what the step read, and the chain holds.
    records = await h.records(rehearsed.id)
    write = next(r for r in records if r.step_id == "write")
    recorded = next(i for i in write.inputs if i.run_id == real.id)
    assert recorded.kind is InputKind.RESULT and recorded.step_id == "write"
    query = ProvenanceQuery(h.provenance, h.runs, h.ledger, h.persistence)
    verification = await query.verify(ProvenanceOfRun(run_id=rehearsed.id, tenant=TENANT))
    assert verification.intact, verification.findings

    # The correction anchor sees nothing of the rehearsal outside.
    checkpoint = rehearsed.step_run("write").checkpoint
    assert checkpoint is not None and checkpoint.result_digest is not None
    async with h.persistence.transaction(TENANT):
        every = list(await h.ledger.entries(TENANT))
        all_records = list(await h.provenance.of_run(TENANT, rehearsed.id))
    assert (
        left_the_system(
            ResultRef(run_id=rehearsed.id, step_id="write", digest=checkpoint.result_digest),
            all_records,
            every,
        )
        is None
    )


async def test_a_rehearsal_without_a_recording_fails_the_step_and_sends_nothing() -> None:
    h = process()
    run = await start(h, rehearsal=True)
    assert run.state is RunState.ESCALATED
    write = run.step_run("write")
    assert write.state is StepState.FAILED
    assert "no recorded response for fake.records.create through connector.fake" in (
        write.reason or ""
    )
    assert [operation for operation, _, _ in h.connector.calls] == [READ]
    assert h.connector.acted == 0
    assert all(e.rehearsal is True for e in await h.entries(run))


async def test_a_recording_is_never_taken_from_a_rehearsal() -> None:
    """A real run, then two rehearsals: the second answers from the real run, not from the
    more recent first rehearsal. A second real run then becomes the recording."""
    h = process()
    first = await start(h, rehearsal=False)
    one = await start(h, rehearsal=True)
    two = await start(h, rehearsal=True)
    for rehearsal in (one, two):
        assert (await result_of(h, rehearsal, "write"))["rehearsed_from"] == {
            "run_id": first.id,
            "step_id": "write",
        }
    second = await start(h, rehearsal=False)
    assert h.connector.acted == 2
    three = await start(h, rehearsal=True)
    replayed = await result_of(h, three, "write")
    assert replayed["rehearsed_from"] == {"run_id": second.id, "step_id": "write"}
    assert replayed["output"] == (await result_of(h, second, "write"))["output"]


# --- the rule, as a table ----------------------------------------------------------------------


def run_of(
    id: str,
    *,
    rehearsal: bool = False,
    adapter: str = "connector.fake",
    operation: str = WRITE,
    state: StepState = StepState.SUCCEEDED,
    minute: int = 0,
) -> Run:
    step = Step(id="write", method="rule", reason="r", rejected=(), exactness="sourced")
    fresh = Run(
        id=id,
        plan_id="pln",
        process_version="p@1",
        tenant=TENANT,
        identity="idn_t",
        autonomy_level=2,
        budget=BUDGET,
        steps=(step,),
        work={"write": {"rule": "connector", "operation": operation, "input": {}}},
        rehearsal=rehearsal,
        created_at=AT,
        updated_at=AT,
    )
    at = AT + timedelta(minutes=minute)
    step_run = fresh.step_run("write").to(StepState.ADMITTED).to(StepState.RUNNING, adapter=adapter)
    if state is StepState.SUCCEEDED:
        step_run = step_run.to(
            StepState.SUCCEEDED,
            checkpoint=Checkpoint(
                ref=f"ckpt/{id}/write",
                step_id="write",
                taken_at=at,
                result_digest="sha256:" + id[-1] * 64,
            ),
            finished_at=at,
        )
    else:
        step_run = step_run.to(state, finished_at=at)
    return fresh.with_step_run(step_run)


@pytest.mark.parametrize(
    ("runs", "chosen"),
    [
        ([], None),
        ([run_of("run_1")], "run_1"),
        # The most recent real call wins.
        ([run_of("run_1", minute=5), run_of("run_2", minute=9)], "run_2"),
        ([run_of("run_2", minute=9), run_of("run_1", minute=5)], "run_2"),
        # A rehearsal is never a recording, however recent.
        ([run_of("run_1"), run_of("run_2", rehearsal=True, minute=9)], "run_1"),
        ([run_of("run_2", rehearsal=True)], None),
        # Only the same operation through the same adapter, and only a call that succeeded.
        ([run_of("run_1", adapter="connector.other")], None),
        ([run_of("run_1", operation="fake.records.fire")], None),
        ([run_of("run_1", state=StepState.FAILED)], None),
    ],
)
def test_the_recording_is_the_last_real_successful_call_of_the_operation_through_the_adapter(
    runs: list[Run], chosen: str | None
) -> None:
    found = recording(runs, "connector.fake", WRITE)
    assert (None if found is None else found.run_id) == chosen


def test_an_egress_entry_of_a_rehearsal_would_not_count_as_leaving() -> None:
    """A rehearsal writes none; if one ever claimed to, the anchor's predicate ignores it."""
    entry = LedgerEntry(
        seq=1,
        ts=AT,
        kind="egress.write",
        prev_hash=None,
        hash="sha256:" + "0" * 64,
        refs=LedgerRefs(run_id="run_1", step_id="write", artifact_ids=("result",)),
        rehearsal=True,
    )
    ref = ResultRef(run_id="run_1", step_id="write", artifact_id="result")
    assert left_the_system(ref, [], [entry]) is None
    assert left_the_system(ref, [], [entry.model_copy(update={"rehearsal": None})]) is not None
