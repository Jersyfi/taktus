"""Connector steps in the run engine, against a fake connector with a memory: the action half
of the connector port bound into the run (ADR-0024), and ADR-0005's promise where it meets the
outside.

The tests that matter most: a write repeated after a crash derives the same idempotency key and
is replayed, not repeated; an outward effect is an egress entry the correction anchor finds
(ADR-0022); a failure the connector calls not retryable starts a new attempt on resume, a
retryable one does not; and an operation that cannot recognise a repeat is never repeated by
the run on its own.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest
from fakes import FakeConnector, FakeWorker, InnerStep, failure
from fakes.connector import BLIND, READ, WRITE

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.components.governance.domain.model import ResultRef
from taktus.components.governance.domain.service.egress import left_the_system
from taktus.components.run.application.service import RunEngine
from taktus.components.run.domain.model import (
    Cause,
    NoConnector,
    RunState,
    StepState,
    UnsupportedWork,
)
from taktus.ports.worker import Worker
from taktus.shared.v1 import ExactnessClass, InputKind, Method, Step

from .test_engine import BUDGET, TENANT, Harness, rule, wait, worker

CREDENTIALS = [{"name": "FAKE_TOKEN", "injected_as": "env"}]


def call(
    id: str,
    operation: str,
    input: dict[str, Any] | None = None,
    *,
    after: tuple[str, ...] = (),
    exactness: ExactnessClass = ExactnessClass.SOURCED,
) -> tuple[Step, dict[str, Any]]:
    step = Step(
        id=id,
        method=Method.RULE,
        reason="r",
        rejected=(),
        exactness=exactness,
        depends_on=after or None,
    )
    work = {
        "rule": "connector",
        "operation": operation,
        "input": input or {},
        "credentials": CREDENTIALS,
    }
    return step, work


class ConnectorHarness(Harness):
    def __init__(
        self,
        *definitions: tuple[Step, dict[str, Any]],
        connector: FakeConnector | None = None,
        workers: Sequence[Worker] = (),
    ) -> None:
        super().__init__(*definitions, workers=workers)
        self.connector = connector or FakeConnector()
        self.engine = RunEngine(
            runs=self.runs,
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=self.provenance,
            workers=self.engine._workers,  # the same pool as the base harness
            clock=self.clock,
            ids=self.ids,
            telemetry=self.engine._telemetry,
            connectors=StaticConnectorPool([("connector.fake", self.connector)]),
        )

    async def records(self, run_id: str) -> list[Any]:
        async with self.persistence.transaction(TENANT):
            return list(await self.provenance.of_run(TENANT, run_id))


# --- reads and writes ------------------------------------------------------------------------


async def test_a_read_is_a_sourced_result_with_its_source_in_the_provenance() -> None:
    h = ConnectorHarness(call("read", READ, {"id": "issue-1"}))
    h.connector.reads["issue-1"] = {"id": "issue-1", "title": "Pin the model"}
    run = await h.start()
    assert run.state is RunState.FINISHED
    step_run = run.step_run("read")
    assert step_run.adapter == "connector.fake"
    assert step_run.consumption is not None and step_run.consumption.quota_units == 1
    assert step_run.checkpoint is not None and step_run.checkpoint.result_digest is not None
    content = await h.objects.get(step_run.checkpoint.result_digest)
    assert content is not None and b'"title": "Pin the model"' in content
    context = h.connector.calls[0][1]
    assert context.identity == "idn_t" and context.tenant == TENANT
    assert context.idempotency_key == f"taktus:{run.id}:read:1" and context.attempt == 1
    assert [c.name for c in context.credentials] == ["FAKE_TOKEN"]
    (record,) = await h.records(run.id)
    assert record.adapter == "connector.fake" and record.adapter_version == "1.2.3"
    (source,) = record.inputs
    assert source.kind is InputKind.SOURCE and source.capability == "fake.records"
    assert source.ref is not None and source.ref.startswith("fake.records.read ")
    assert source.digest is not None
    assert "egress.write" not in " ".join(await h.kinds(run))


async def test_a_write_leaves_the_system_as_an_egress_entry_the_anchor_finds() -> None:
    h = ConnectorHarness(
        rule("prep", {"rule": "constant", "value": {"title": "t"}}),
        call("write", WRITE, {"title": {"$from": "prep", "$select": "title"}}, after=("prep",)),
    )
    run = await h.start()
    assert run.state is RunState.FINISHED
    assert h.connector.acted == 1
    assert h.connector.calls[0][2] == {"title": "t"}
    kinds = await h.kinds(run)
    assert kinds[kinds.index("step.finished:write:succeeded") + 1] == "egress.write:write:acted"
    entries = await h.entries(run)
    egress = next(e for e in entries if e.kind == "egress.write")
    assert egress.refs.artifact_ids == ("result",)
    assert egress.content_digest is not None and egress.content_digest.startswith("sha256:")
    assert egress.adapter == "connector.fake"
    # The correction anchor's predicate (ADR-0022 §4): the write's result has left the system,
    # and so has what it was derived from — the value of `prep`, which the write read.
    records = await h.records(run.id)
    prep = run.step_run("prep")
    assert prep.checkpoint is not None and prep.checkpoint.result_digest is not None
    left = left_the_system(
        ResultRef(run_id=run.id, step_id="prep", digest=prep.checkpoint.result_digest),
        records,
        entries,
    )
    assert left is not None and left.kind == "egress.write"
    assert await h.verify()


class Crash(BaseException):
    """The instance dies: not an Exception, so that nothing in the engine catches it."""


async def test_a_write_repeated_after_a_crash_derives_the_same_key_and_is_replayed() -> None:
    """The instance died after the connector had acted and before the answer was persisted:
    the run is left running with the step in flight. The recovered step derives the key of the
    same attempt, the connector answers with the original, and one record exists."""
    h = ConnectorHarness(call("write", WRITE, {"title": "once"}))
    h.connector.crash_after_acting = Crash
    with pytest.raises(Crash):
        await h.start()
    assert h.connector.acted == 1
    left = await h.stored("run_0001")
    assert left is not None and left.state is RunState.RUNNING
    assert left.step_run("write").state is StepState.RUNNING
    recovered = await h.resume(left)
    assert recovered.state is RunState.FINISHED
    assert h.connector.acted == 1, "the target holds one record"
    first, second = (c[1] for c in h.connector.calls)
    assert first.idempotency_key == second.idempotency_key
    assert second.attempt == 1
    kinds = await h.kinds(recovered)
    assert "run.recovered:write" in kinds
    assert kinds[-2:] == ["egress.write:write:replayed", "run.finished::succeeded"]
    assert await h.verify()


# --- failures ----------------------------------------------------------------------------------


async def test_a_failure_that_is_not_retryable_starts_a_new_attempt_on_resume() -> None:
    h = ConnectorHarness(call("write", WRITE, {"title": "t"}))
    h.connector.fail_next[WRITE] = failure("forbidden")
    run = await h.start()
    assert run.state is RunState.ESCALATED and run.cause is Cause.FAILURE
    failed = run.step_run("write")
    assert failed.state is StepState.FAILED and failed.retryable is False
    assert failed.reason is not None and "forbidden" in failed.reason
    assert failed.adapter == "connector.fake"
    resumed = await h.resume(run)
    assert resumed.state is RunState.FINISHED
    assert resumed.step_run("write").attempt == 2
    keys = [c[1].idempotency_key for c in h.connector.calls]
    assert keys == [f"taktus:{run.id}:write:1", f"taktus:{run.id}:write:2"]


async def test_a_retryable_failure_keeps_the_attempt_and_the_key() -> None:
    h = ConnectorHarness(call("write", WRITE, {"title": "t"}))
    h.connector.fail_next[WRITE] = failure("unavailable", retryable=True)
    run = await h.start()
    assert run.state is RunState.ESCALATED
    assert run.step_run("write").retryable is True
    resumed = await h.resume(run)
    assert resumed.state is RunState.FINISHED
    assert resumed.step_run("write").attempt == 1
    keys = {c[1].idempotency_key for c in h.connector.calls}
    assert keys == {f"taktus:{run.id}:write:1"}


async def test_an_operation_that_cannot_recognise_a_repeat_is_never_repeated_by_the_run() -> None:
    h = ConnectorHarness(call("fire", BLIND, {"what": "pipeline"}))
    h.connector.fail_next[BLIND] = failure("unknown", effect="unknown")
    run = await h.start()
    assert run.state is RunState.ESCALATED
    assert h.connector.acted == 0
    reason = run.step_run("fire").reason or ""
    assert "cannot recognise a repeat" in reason and "resuming repeats the call" in reason
    assert len(h.connector.calls) == 1, "nothing retried on its own"


async def test_a_connector_that_is_down_fails_the_step_and_keeps_the_attempt() -> None:
    h = ConnectorHarness(call("read", READ, {"id": "x"}))
    h.connector.unreachable = "the connector at fake did not answer"
    run = await h.start()
    assert run.state is RunState.ESCALATED
    assert run.step_run("read").retryable is True
    h.connector.unreachable = None
    resumed = await h.resume(run)
    assert resumed.state is RunState.FINISHED
    assert resumed.step_run("read").attempt == 1


async def test_a_reported_effect_that_contradicts_the_declaration_fails_the_step() -> None:
    class Lying(FakeConnector):
        async def call(self, operation: str, context: Any, input: Any) -> Any:
            result = await super().call(operation, context, input)
            return result.model_copy(
                update={"effect": result.effect.model_copy(update={"kind": "read"})}
            )

    h = ConnectorHarness(call("write", WRITE, {"title": "t"}), connector=Lying())
    run = await h.start()
    assert run.state is RunState.ESCALATED
    assert "broke its contract" in (run.step_run("write").reason or "")


async def test_a_capability_no_connector_serves_fails_the_step_and_escalates() -> None:
    """A missing connector, or an operation the connector does not declare, is a failed step
    naming what is missing; the run escalates at the boundary and a resume retries."""
    h = ConnectorHarness(call("read", "other.things.read", {"id": "x"}))
    run = await h.start()
    assert run.state is RunState.ESCALATED
    read = run.step_run("read")
    assert read.state is StepState.FAILED and read.retryable is True
    assert read.reason == str(NoConnector("read", "other.things"))
    h = ConnectorHarness(call("read", "fake.records.destroy", {"id": "x"}))
    run = await h.start()
    assert run.state is RunState.ESCALATED
    assert run.step_run("read").reason == str(NoConnector("read", "fake.records.destroy"))


# --- checks, templates, artifacts ---------------------------------------------------------------


async def test_a_check_takes_its_verdict_from_the_values_and_fails_otherwise() -> None:
    h = ConnectorHarness(
        call("read", READ, {"id": "ci"}),
        rule(
            "verify",
            {
                "rule": "check",
                "conditions": [
                    {"value": {"$from": "read", "$select": "output.state"}, "equals": "success"},
                    {"value": {"$from": "read", "$select": "output.runs"}, "matches": "ci"},
                    {"value": {"$from": "read", "$select": "output.note"}, "not_matches": "red"},
                ],
            },
            after=("read",),
        ),
    )
    h.connector.reads["ci"] = {"state": "success", "runs": ["ci"], "note": "green"}
    run = await h.start()
    assert run.state is RunState.FINISHED
    (record,) = [r for r in await h.records(run.id) if r.step_id == "verify"]
    assert [i.kind for i in record.inputs] == [InputKind.RESULT], "one step read, recorded once"

    h.connector.reads["ci"] = {"state": "failure", "runs": ["ci"], "note": "red"}
    failed = await h.start()
    assert failed.state is RunState.ESCALATED
    assert "condition 1 does not hold" in (failed.step_run("verify").reason or "")


async def test_a_template_renders_values_and_names_what_is_missing() -> None:
    h = ConnectorHarness(
        rule("n", {"rule": "constant", "value": 42}),
        rule(
            "body",
            {
                "rule": "template",
                "text": "Closes #${n}.\n\n${summary}",
                "values": {"n": {"$from": "n"}, "summary": "Done."},
            },
            after=("n",),
        ),
    )
    run = await h.start()
    body = run.step_run("body")
    assert body.checkpoint is not None and body.checkpoint.result_digest is not None
    assert await h.objects.get(body.checkpoint.result_digest) == b'"Closes #42.\\n\\nDone."'
    h = ConnectorHarness(rule("body", {"rule": "template", "text": "${nope}", "values": {}}))
    failed = await h.start()
    assert failed.state is RunState.ESCALATED
    assert "'nope'" in (failed.step_run("body").reason or "")


async def test_an_artifact_reference_carries_the_content_and_the_read() -> None:
    fake = FakeWorker(
        script=(InnerStep("one", artifacts=(("changeset", b'{"files": [{"path": "a"}]}'),)),)
    )
    h = ConnectorHarness(
        worker("do"),
        call(
            "push",
            WRITE,
            {"changes": {"$from": "do", "$artifact": "changeset"}},
            after=("do",),
        ),
        workers=[fake],
    )
    run = await h.start()
    assert run.state is RunState.FINISHED
    # The fake worker announces text: the content arrives as text, unparsed.
    assert h.connector.calls[0][2] == {"changes": '{"files": [{"path": "a"}]}'}
    (record,) = [r for r in await h.records(run.id) if r.step_id == "push"]
    assert [(i.kind, i.artifact_id) for i in record.inputs] == [(InputKind.ARTIFACT, "changeset")]


async def test_run_inputs_resolve_and_a_missing_one_is_refused_before_anything_runs() -> None:
    h = ConnectorHarness(call("read", READ, {"id": {"$input": "issue"}}))
    h.connector.reads["7"] = {"id": "7"}
    run = await h.engine.start(
        _start(h, inputs={"issue": "7"}),
    )
    assert run.state is RunState.FINISHED and run.inputs == {"issue": "7"}
    assert h.connector.calls[0][2] == {"id": "7"}
    with pytest.raises(UnsupportedWork, match="no input 'issue'"):
        await h.engine.start(_start(h, inputs={}))


def _start(h: ConnectorHarness, *, inputs: dict[str, Any]) -> Any:
    from taktus.components.run.application.service import StartRun

    return StartRun(
        plan=h.plan(),
        work=h.work,
        budget=BUDGET,
        process_version="p@1",
        actor="idn_t",
        tenant=TENANT,
        inputs=inputs,
    )


# --- waiting on an external state ----------------------------------------------------------------


async def test_a_wait_polls_an_external_state_until_it_is_expected() -> None:
    h = ConnectorHarness(
        (
            wait("ci", 0)[0],
            {
                "until": {
                    "operation": READ,
                    "input": {"id": "ci"},
                    "credentials": CREDENTIALS,
                    "select": "state",
                    "expect": ["success", "failure"],
                    "poll_seconds": 5,
                    "timeout_seconds": 60,
                }
            },
        ),
    )
    h.connector.read_sequence = [{"state": "pending"}, {"state": "pending"}, {"state": "success"}]
    run = await h.start()
    assert run.state is RunState.FINISHED
    assert h.clock.slept == [5, 5]
    ci = run.step_run("ci")
    assert ci.consumption is not None and ci.consumption.quota_units == 3
    assert ci.artifacts == () and ci.checkpoint is not None
    assert ci.checkpoint.result_digest is None, "a wait produces no result (ADR-0018)"


async def test_a_wait_that_runs_out_fails_the_step() -> None:
    h = ConnectorHarness(
        (
            wait("ci", 0)[0],
            {
                "until": {
                    "operation": READ,
                    "input": {"id": "ci"},
                    "credentials": CREDENTIALS,
                    "select": "state",
                    "expect": ["success"],
                    "poll_seconds": 10,
                    "timeout_seconds": 25,
                }
            },
        ),
    )
    h.connector.reads["ci"] = {"state": "pending"}
    run = await h.start()
    assert run.state is RunState.ESCALATED
    assert "waited 30s" in (run.step_run("ci").reason or "")
    assert run.step_run("ci").retryable is True
