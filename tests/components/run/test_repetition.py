"""A stop to repetition (UC-8.12 §2, ADR-0132 §4 to §5).

A step that would make the same outward connector call with the same arguments more often than
the tenant's limit within one run is stopped at its boundary, and so is a step whose model would
answer once more than the limit without a tool result between. The stop names the action, the
count and the limit, and raises an incident. Both are rules over the run's ledger: an engine
that never saw the earlier calls stops the step just the same.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from fakes import FakeConnector, FakeModel, failure
from fakes.connector import READ, WRITE
from fakes.maturity import VERIFIED

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.models import StaticModelPool
from taktus.components.run.application.service import RunEngine
from taktus.components.run.domain.model import Cause, Run, RunState, StepState
from taktus.components.run.domain.service import repetition
from taktus.components.run.ports import Repeated, RepetitionLimits

from .test_connector_steps import call
from .test_engine import Harness, rule
from .test_llm_steps import WORK, llm


class Limits:
    """The tenant's limits and the incidents the stops raised, as the run's port answers."""

    def __init__(self, calls: int = 3, model_calls: int = 3) -> None:
        self.limits = RepetitionLimits(calls=calls, model_calls=model_calls)
        self.stops: list[Repeated] = []

    async def limits_of(self, tenant: str) -> RepetitionLimits:
        return self.limits

    async def stopped(self, tenant: str, repeated: Repeated) -> str | None:
        self.stops.append(repeated)
        return f"inc_{len(self.stops)}"


class Port:
    def __init__(self, limits: Limits) -> None:
        self._limits = limits

    async def limits(self, tenant: str) -> RepetitionLimits:
        return await self._limits.limits_of(tenant)

    async def stopped(self, tenant: str, repeated: Repeated) -> str | None:
        return await self._limits.stopped(tenant, repeated)


class Repeating(Harness):
    def __init__(
        self,
        *definitions: tuple[Any, dict[str, Any]],
        limits: Limits | None = None,
        connector: FakeConnector | None = None,
        model: FakeModel | None = None,
    ) -> None:
        super().__init__(*definitions)
        self.limits = limits or Limits()
        self.connector = connector or FakeConnector()
        self.model = model or FakeModel()
        self.engine = self.fresh_engine()

    def fresh_engine(self) -> RunEngine:
        """An engine that holds nothing in memory of the runs before it."""
        return RunEngine(
            maturities=VERIFIED,
            runs=self.runs,
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=self.provenance,
            workers=self.engine._workers,
            clock=self.clock,
            ids=self.ids,
            telemetry=self.engine._telemetry,
            options=self.engine._options,
            connectors=StaticConnectorPool([("connector.fake", self.connector)]),
            models=StaticModelPool([("model.fake", ["reasoning"], self.model, "fake-model@1")]),
            repetition=Port(self.limits),
        )

    async def stop_record(self, run: Run) -> dict[str, Any]:
        entry = next(e for e in await self.entries(run) if e.kind == repetition.STOPPED)
        assert entry.content_digest is not None
        document: dict[str, Any] = json.loads(await self.objects.get(entry.content_digest) or b"")
        return document


async def test_the_same_outward_call_beyond_the_limit_is_stopped_at_its_boundary() -> None:
    h = Repeating(
        call("open", WRITE, {"title": "fix the build"}),
        limits=Limits(calls=3),
    )
    # The write fails, and may be retried: every resume repeats the same call.
    h.connector.fail_each[WRITE] = [failure("unavailable", retryable=True)] * 5
    run = await h.start()
    for _ in range(2):
        assert run.state is RunState.ESCALATED
        run = await h.resume(run)
    assert run.state is RunState.ESCALATED
    assert len([c for c in h.connector.calls if c[0] == WRITE]) == 3
    # A fresh engine reads the calls from the ledger, not from its memory.
    h.engine = h.fresh_engine()
    run = await h.resume(run)
    assert run.state is RunState.HALTED and run.cause is Cause.REPEATED
    assert len([c for c in h.connector.calls if c[0] == WRITE]) == 3, "the fourth was not made"
    stopped = run.step_run("open")
    assert stopped.state is StepState.REJECTED
    reason = stopped.reason or ""
    assert WRITE in reason and "3 time(s)" in reason and "limit is 3" in reason
    kinds = await h.kinds(run)
    assert kinds.count("connector.called:open:called") == 3
    assert "step.rejected:open:rejected_by_repetition" in kinds
    assert "repetition.stopped:open:calls" in kinds
    assert await h.stop_record(run) == {
        "rule": "repetition.calls",
        "run_id": run.id,
        "step_id": "open",
        "process_version": "p@1",
        "action": WRITE,
        "count": 3,
        "limit": 3,
    }
    (stop,) = h.limits.stops
    assert (stop.rule, stop.action, stop.count, stop.limit) == ("calls", WRITE, 3, 3)
    # A resume stops it again: only a raised limit lets the call through.
    run = await h.resume(run)
    assert run.cause is Cause.REPEATED
    h.limits.limits = RepetitionLimits(calls=4, model_calls=3)
    h.connector.fail_each[WRITE] = []
    run = await h.resume(run)
    assert run.state is RunState.FINISHED
    assert await h.verify()


async def test_the_same_call_from_another_step_counts_and_other_arguments_do_not() -> None:
    h = Repeating(
        call("first", WRITE, {"title": "a"}),
        call("other", WRITE, {"title": "b"}, after=("first",)),
        call("again", WRITE, {"title": "a"}, after=("other",)),
        limits=Limits(calls=1),
    )
    run = await h.start()
    assert run.state is RunState.HALTED and run.cause is Cause.REPEATED
    assert run.step_run("first").state is StepState.SUCCEEDED
    assert run.step_run("other").state is StepState.SUCCEEDED
    assert run.step_run("again").state is StepState.REJECTED
    assert h.connector.acted == 2


async def test_a_read_is_never_counted() -> None:
    h = Repeating(
        call("one", READ, {"id": "x"}),
        call("two", READ, {"id": "x"}, after=("one",)),
        limits=Limits(calls=1),
    )
    run = await h.start()
    assert run.state is RunState.FINISHED
    assert not [k for k in await h.kinds(run) if k.startswith("connector.called")]


async def test_a_model_asked_again_without_a_tool_result_beyond_the_limit_is_stopped() -> None:
    h = Repeating(
        rule("issue", {"rule": "constant", "value": {"number": 1, "title": "t"}}),
        llm("refine", WORK, after=("issue",)),
        limits=Limits(model_calls=2),
        model=FakeModel(answer="Sure! Here are some thoughts."),
    )
    run = await h.start()
    assert run.state is RunState.ESCALATED, "the answer failed its check"
    run = await h.resume(run)
    assert run.state is RunState.ESCALATED
    assert len(h.model.prompts) == 2
    run = await h.resume(run)
    assert run.state is RunState.HALTED and run.cause is Cause.REPEATED
    assert len(h.model.prompts) == 2, "the third call was not made"
    assert "without a new tool result" in (run.step_run("refine").reason or "")
    assert (await h.kinds(run)).count("model.called:refine:answered") == 2
    record = await h.stop_record(run)
    assert record["rule"] == "repetition.model_calls" and record["count"] == 2
    assert h.limits.stops[0].action == "purpose reasoning"


async def test_a_provider_at_its_rate_limit_answered_nothing_and_is_not_counted() -> None:
    h = Repeating(
        llm("draft", {**WORK, "values": {}, "prompt": "x"}),
        limits=Limits(model_calls=1),
        model=FakeModel(at_limit=1),
    )
    run = await h.start()
    assert run.cause is Cause.CAPACITY
    h.clock.current += timedelta(seconds=120)  # past the model's cool-down
    run = await h.resume(run)
    assert run.state is RunState.FINISHED
    assert (await h.kinds(run)).count("model.called:draft:answered") == 1
