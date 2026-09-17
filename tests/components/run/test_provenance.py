"""The provenance chain (ADR-0021): written for every completed step, unbroken, bounded, and
kept across a stop and a recovery. The engine runs against fakes and the memory stores; the
domain's `verify` is held to broken chains it must find."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from fakes import FakeWorker, InnerStep

from components.run.test_engine import AT, TENANT, Harness, rule, wait, worker
from taktus.components.run.application.query import ChainOf, ProvenanceOfRun, ProvenanceQuery
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.components.run.domain.service import provenance as chain
from taktus.ports.persistence import DuplicateProvenance, SpoiltTransaction
from taktus.ports.worker import Event
from taktus.shared.v1 import (
    ExactnessClass,
    InputKind,
    LedgerEntry,
    Method,
    Provenance,
    ProvenanceInput,
)


class Crash(Exception):
    pass


def digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


async def records(h: Harness, run: Run) -> list[Provenance]:
    async with h.persistence.transaction(TENANT):
        return list(await h.provenance.of_run(TENANT, run.id))


def query(h: Harness) -> ProvenanceQuery:
    return ProvenanceQuery(h.provenance, h.runs, h.ledger, h.persistence)


# --- every step, unbroken -----------------------------------------------------------------------


async def test_every_completed_step_has_one_record_bound_to_its_ledger_entry() -> None:
    fake = FakeWorker(script=(InnerStep("one", 1.0, (("out-1", b"42\n"), ("out-2", b"x"))),))
    h = Harness(
        rule("prep", {"rule": "constant", "value": {"n": 42}}),
        worker("do", {"$from": "prep"}, after=("prep",)),
        wait("pause", 0, after=("do",)),
        rule(
            "check",
            {"rule": "verify_artifact", "step": "do", "artifact": "out-1", "pattern": "^42$"},
            after=("pause",),
        ),
        workers=[fake],
    )
    run = await h.start()
    assert run.state is RunState.FINISHED
    found = await records(h, run)
    assert [r.step_id for r in found] == ["prep", "do", "pause", "check"], "one per step, in order"
    entries = await h.entries(run)
    by_seq = {e.seq: e for e in entries}
    for record in found:
        entry = by_seq[record.ledger_seq]
        assert entry.kind == "step.finished" and entry.outcome == "succeeded"
        assert entry.refs.step_id == record.step_id
        assert record.process_version == "p@1"

    prep, do, pause, check = found
    assert prep.method is Method.RULE and prep.exactness is ExactnessClass.EXACT
    assert prep.inputs == () and prep.outputs == ("result",)
    assert prep.result_digest is not None and prep.adapter is None

    assert do.method is Method.WORKER and do.exactness is ExactnessClass.TOLERANT
    assert do.adapter == "worker.fake.0" and do.adapter_version == "0.9.0"
    assert do.outputs == ("out-1", "out-2") and do.result_digest is None
    assert [i.model_copy(update={"observed_at": AT}) for i in do.inputs] == [
        ProvenanceInput(
            kind=InputKind.RESULT,
            run_id=run.id,
            step_id="prep",
            digest=prep.result_digest,
            observed_at=AT,
        ),
    ], "a $from of a rule's value is a result input by digest"
    produced, finished = run.step_run("prep").finished_at, run.step_run("do").finished_at
    assert produced is not None and finished is not None
    assert produced <= do.inputs[0].observed_at <= finished, "read after it was produced"

    assert pause.method is Method.WAIT and pause.exactness is None
    assert pause.inputs == () and pause.outputs == ()

    assert [i.model_copy(update={"observed_at": AT}) for i in check.inputs] == [
        ProvenanceInput(
            kind=InputKind.ARTIFACT,
            run_id=run.id,
            step_id="do",
            artifact_id="out-1",
            digest=digest(b"42\n"),
            observed_at=AT,
        ),
    ], "a verified artifact is an artifact input"
    assert check.result_digest is not None and check.outputs == ("result",)

    verification = await query(h).verify(ProvenanceOfRun(run_id=run.id, tenant=TENANT))
    assert verification.intact, verification.findings
    assert verification.records == 4


async def test_a_from_of_a_worker_step_lists_every_artifact_read() -> None:
    first = FakeWorker(script=(InnerStep("one", 1.0, (("a", b"1"), ("b", b"2"))),))
    h = Harness(
        worker("produce"),
        worker("consume", {"$from": "produce"}, after=("produce",)),
        workers=[first],
    )
    run = await h.start()
    consume = (await records(h, run))[1]
    assert [(i.kind, i.artifact_id, i.digest) for i in consume.inputs] == [
        (InputKind.ARTIFACT, "a", digest(b"1")),
        (InputKind.ARTIFACT, "b", digest(b"2")),
    ]


async def test_a_failed_or_rejected_step_leaves_no_record() -> None:
    h = Harness(
        rule("prep", {"rule": "constant", "value": 1}),
        worker("big", after=("prep",)),
        workers=[FakeWorker(estimate_seconds=11)],
    )
    run = await h.start()
    assert run.step_run("big").state is StepState.REJECTED
    assert [r.step_id for r in await records(h, run)] == ["prep"]
    verification = await query(h).verify(ProvenanceOfRun(run_id=run.id, tenant=TENANT))
    assert verification.intact, "a chain with no record for an unfinished step is whole"


# --- the chain behind an artifact --------------------------------------------------------------


async def test_the_chain_behind_an_artifact_leads_back_to_the_first_input() -> None:
    fake = FakeWorker(script=(InnerStep("one", 1.0, (("out-1", b"42\n"),)),))
    h = Harness(
        rule("prep", {"rule": "constant", "value": {"n": 42}}),
        rule("aside", {"rule": "constant", "value": "unrelated"}),
        worker("do", {"$from": "prep"}, after=("prep", "aside")),
        rule(
            "check",
            {"rule": "verify_artifact", "step": "do", "artifact": "out-1"},
            after=("do",),
        ),
        workers=[fake],
    )
    run = await h.start()
    walked = await query(h).chain(ChainOf(run_id=run.id, artifact_id="out-1", tenant=TENANT))
    assert [r.step_id for r in walked] == ["do", "prep"], "producer first, then what it read"
    assert walked[0].adapter_version == "0.9.0" and walked[0].method is Method.WORKER
    assert walked[1].method is Method.RULE and walked[1].exactness is ExactnessClass.EXACT
    assert "aside" not in {r.step_id for r in walked}, "a step not read is not in the chain"
    assert await query(h).chain(ChainOf(run_id=run.id, artifact_id="nope", tenant=TENANT)) == []


# --- a stop and a recovery leave no gap ----------------------------------------------------------


async def test_the_chain_is_whole_across_a_stop_and_a_resume() -> None:
    fake = FakeWorker(
        script=(
            InnerStep("one", 1.0, (("out-1", b"1"),)),
            InnerStep("two", 1.0, (("out-2", b"2"),)),
        )
    )
    h = Harness(
        rule("prep", {"rule": "constant", "value": {"n": 1}}),
        worker("do", {"$from": "prep"}, after=("prep",)),
        wait("after", 0, after=("do",)),
        workers=[fake],
    )
    seen: list[str] = []

    async def stop_after_first_inner_step(event: Event) -> None:
        seen.append(event.type)
        if event.type == "step.started" and len(seen) == 1:
            await h.engine.request_stop("run_0001")

    fake.on_event = stop_after_first_inner_step
    run = await h.start()
    assert run.state is RunState.HALTED
    assert [r.step_id for r in await records(h, run)] == ["prep"], "a stopped step has none yet"

    fake.on_event = None
    run = await h.resume(run)
    assert run.state is RunState.FINISHED
    found = await records(h, run)
    assert [r.step_id for r in found] == ["prep", "do", "after"]
    do = found[1]
    assert do.outputs == ("out-1", "out-2"), "both parts of the step, once each"
    assert [i.step_id for i in do.inputs] == ["prep"]
    verification = await query(h).verify(ProvenanceOfRun(run_id=run.id, tenant=TENANT))
    assert verification.intact, verification.findings


async def test_the_chain_is_whole_across_a_crash_and_a_recovery() -> None:
    fake = FakeWorker(
        script=(
            InnerStep("one", 1.0, (("out-1", b"1"),)),
            InnerStep("two", 1.0, (("out-2", b"2"),)),
            InnerStep("three", 1.0, (("out-3", b"3"),)),
        )
    )
    h = Harness(
        rule("prep", {"rule": "constant", "value": 1}),
        worker("do", after=("prep",)),
        rule(
            "check", {"rule": "verify_artifact", "step": "do", "artifact": "out-3"}, after=("do",)
        ),
        workers=[fake],
    )

    async def die_inside_the_second_inner_step(event: Event) -> None:
        if event.type == "step.started" and event.seq == 5:
            raise Crash

    fake.on_event = die_inside_the_second_inner_step
    with pytest.raises(Crash):
        await h.start()
    left = await h.stored("run_0001")
    assert left is not None
    before = await records(h, left)
    assert [r.step_id for r in before] == ["prep"]

    fake.on_event = None
    run = await h.resume(left)
    assert run.state is RunState.FINISHED
    found = await records(h, run)
    assert found[0] == before[0], "the record before the crash is unchanged"
    assert [r.step_id for r in found] == ["prep", "do", "check"]
    assert found[1].outputs == ("out-1", "out-2", "out-3")
    assert found[2].inputs[0].artifact_id == "out-3"
    verification = await query(h).verify(ProvenanceOfRun(run_id=run.id, tenant=TENANT))
    assert verification.intact, verification.findings


# --- growth stays within the bound --------------------------------------------------------------


async def test_growth_per_run_stays_within_the_documented_bound() -> None:
    fake = FakeWorker(
        script=(InnerStep("one", 1.0, tuple((f"out-{n}", bytes([n])) for n in range(1, 21))),)
    )
    h = Harness(
        rule("prep", {"rule": "constant", "value": {"n": 42}}),
        worker("produce", {"$from": "prep"}, after=("prep",)),
        worker("consume", {"$from": "produce"}, after=("produce",)),
        wait("pause", 0, after=("consume",)),
        rule(
            "check",
            {"rule": "verify_artifact", "step": "produce", "artifact": "out-7"},
            after=("pause",),
        ),
        workers=[fake, FakeWorker(script=(InnerStep("one", 1.0, (("summary", b"s"),)),))],
    )
    run = await h.start()
    assert run.state is RunState.FINISHED
    found = await records(h, run)
    entries = await h.entries(run)
    # Rows: exactly one per completed step, never more than a third of the run's ledger.
    assert len(found) == len(run.steps) == 5
    assert len(found) * 3 <= len(entries)
    # Bytes: the fixed part plus what the inputs and outputs the step really had add.
    for record in found:
        assert chain.size_bytes(record) <= chain.size_bound(record), record.step_id
    consume = next(r for r in found if r.step_id == "consume")
    assert len(consume.inputs) == 20, "the step read twenty artifacts, so twenty inputs"
    assert chain.size_bytes(consume) <= chain.FIXED_BYTES + 20 * chain.BYTES_PER_INPUT + 80


async def test_a_step_run_is_recorded_once() -> None:
    h = Harness(rule("prep", {"rule": "constant", "value": 1}))
    run = await h.start()
    first = (await records(h, run))[0]
    again = first.model_copy(update={"id": "prov_other", "ledger_seq": first.ledger_seq + 1})
    with pytest.raises(SpoiltTransaction):
        async with h.persistence.transaction(TENANT):
            with pytest.raises(DuplicateProvenance):
                await h.provenance.append(TENANT, again)
    assert await records(h, run) == [first]


# --- what verify finds ---------------------------------------------------------------------------


async def _finished_run() -> tuple[Harness, Run, list[Provenance], list[LedgerEntry]]:
    fake = FakeWorker(script=(InnerStep("one", 1.0, (("out-1", b"42\n"),)),))
    h = Harness(
        rule("prep", {"rule": "constant", "value": {"n": 42}}),
        worker("do", {"$from": "prep"}, after=("prep",)),
        rule(
            "check", {"rule": "verify_artifact", "step": "do", "artifact": "out-1"}, after=("do",)
        ),
        workers=[fake],
    )
    run = await h.start()
    return h, run, await records(h, run), list(await h.entries(run))


async def test_verify_finds_a_missing_record() -> None:
    _, run, found, entries = await _finished_run()
    verification = chain.verify(run, [r for r in found if r.step_id != "do"], entries)
    assert not verification.intact
    assert "do: completed without a record" in verification.findings
    assert any(
        f.startswith("check: reads 'do', which has no record") for f in verification.findings
    )


async def test_verify_finds_a_record_that_disagrees_with_its_step_run() -> None:
    _, run, found, entries = await _finished_run()
    prep, do, check = found
    forged = do.model_copy(update={"adapter": "worker.other", "outputs": ("out-1", "planted")})
    verification = chain.verify(run, [prep, forged, check], entries)
    assert not verification.intact
    assert any("do: adapter is 'worker.other'" in f for f in verification.findings)
    assert any("do: outputs is ('out-1', 'planted')" in f for f in verification.findings)
    assert any("in ledger entry" in f for f in verification.findings), "the ledger disagrees too"


async def test_verify_finds_an_input_that_names_what_was_never_produced() -> None:
    _, run, found, entries = await _finished_run()
    prep, do, check = found
    wrong = check.model_copy(
        update={
            "inputs": (
                check.inputs[0].model_copy(update={"artifact_id": "out-9"}),
                ProvenanceInput(
                    kind=InputKind.RESULT,
                    run_id=run.id,
                    step_id="prep",
                    digest="sha256:" + "f" * 64,
                    observed_at=datetime(2026, 9, 16, tzinfo=UTC),
                ),
            )
        }
    )
    verification = chain.verify(run, [prep, do, wrong], entries)
    assert not verification.intact
    assert "check: reads artifact 'out-9' of 'do', which its record does not list" in (
        verification.findings
    )
    assert "check: reads 'prep', which is not a step before it" not in verification.findings, (
        "prep is an ancestor of check through do"
    )
    assert "check: reads the result of 'prep' under a digest its record does not carry" in (
        verification.findings
    )


async def test_verify_finds_a_record_for_a_step_that_did_not_complete_and_a_stray_one() -> None:
    _, run, found, entries = await _finished_run()
    prep, do, check = found
    stray = check.model_copy(update={"step_id": "ghost", "id": "prov_ghost"})
    twice = do.model_copy(update={"id": "prov_twice"})
    verification = chain.verify(run, [prep, do, twice, check, stray], entries)
    assert "do: recorded twice" in verification.findings
    assert "ghost: record for a step the run does not have" in verification.findings
    halted = run.with_step_run(run.step_run("check").model_copy(update={"state": "failed"}))
    verification = chain.verify(halted, [prep, do, check], entries)
    assert "check: recorded although it is failed" in verification.findings


async def test_verify_holds_a_record_to_its_ledger_entry() -> None:
    _, run, found, entries = await _finished_run()
    prep, do, check = found
    off = do.model_copy(update={"ledger_seq": do.ledger_seq - 1})  # step.started, not finished
    verification = chain.verify(run, [prep, off, check], entries)
    assert any("is step.started , not step.finished succeeded" in f for f in verification.findings)
    missing = do.model_copy(update={"ledger_seq": 999})
    verification = chain.verify(run, [prep, missing, check], entries)
    assert "do: names ledger entry 999, which does not exist" in verification.findings
    assert chain.verify(run, found, None).intact, "without entries, the run alone is checked"
