"""Steps that run when a run escalates (ADR-0097): a process gives back what it took before it
goes to a person, and a run that finishes never runs them."""

from __future__ import annotations

import json
from typing import Any

import pytest

from components.run.test_engine import TENANT, Harness, rule
from taktus.components.run.application.query import ProvenanceOfRun, ProvenanceQuery
from taktus.components.run.domain.model import Cause, RunState, StepState, UnsupportedWork

FAIL = {"rule": "check", "conditions": [{"value": 1, "equals": 2}]}


def aside(work: dict[str, Any]) -> dict[str, Any]:
    return {**work, "on_escalation": True}


async def result(h: Harness, run: Any, step_id: str) -> Any:
    checkpoint = run.step_run(step_id).checkpoint
    assert checkpoint is not None and checkpoint.result_digest is not None
    return json.loads(await h.objects.get(checkpoint.result_digest) or b"")


async def test_a_failed_step_runs_the_steps_on_escalation_before_the_run_escalates() -> None:
    h = Harness(
        rule("claim", {"rule": "constant", "value": "claimed"}),
        rule("work", FAIL, after=("claim",)),
        rule("after", {"rule": "constant", "value": "never"}, after=("work",)),
        rule(
            "say-why",
            aside(
                {
                    "rule": "template",
                    "text": "run ${run} gives it back: ${step} failed: ${reason}",
                    "values": {
                        "run": {"$run": "id"},
                        "step": {"$run": "failed", "$select": "step"},
                        "reason": {"$run": "failed.reason"},
                    },
                }
            ),
            after=("claim",),
        ),
        rule("give-back", aside({"rule": "constant", "value": "released"}), after=("say-why",)),
    )
    run = await h.start()
    assert run.state is RunState.ESCALATED and run.cause is Cause.FAILURE
    assert run.reason == run.step_run("work").reason, "the run escalates for the step that failed"
    assert run.step_run("after").state is StepState.PLANNED
    said = await result(h, run, "say-why")
    assert said.startswith(f"run {run.id} gives it back: work failed: ")
    assert "1" in said and run.step_run("give-back").state is StepState.SUCCEEDED
    kinds = await h.kinds(run)
    assert kinds.index("step.finished:work:failed") < kinds.index("step.finished:say-why:succeeded")
    assert kinds[-3:] == [
        "step.finished:give-back:succeeded",
        "run.escalated::failure",
        "run.ended::error",
    ]
    assert await h.verify()
    provenance = ProvenanceQuery(h.provenance, h.runs, h.ledger, h.persistence)
    verification = await provenance.verify(ProvenanceOfRun(run_id=run.id, tenant=TENANT))
    assert verification.intact, verification.findings
    assert verification.records == 3, "claim and the two steps on escalation"


async def test_a_step_on_escalation_whose_dependency_did_not_succeed_stays_planned() -> None:
    h = Harness(
        rule("admit", FAIL),
        rule("claim", {"rule": "constant", "value": "claimed"}, after=("admit",)),
        rule("give-back", aside({"rule": "constant", "value": "released"}), after=("claim",)),
    )
    run = await h.start()
    assert run.state is RunState.ESCALATED
    assert run.step_run("give-back").state is StepState.PLANNED, "nothing was taken to give back"


async def test_a_run_that_finishes_skips_its_steps_on_escalation() -> None:
    h = Harness(
        rule("claim", {"rule": "constant", "value": "claimed"}),
        rule("give-back", aside({"rule": "constant", "value": "released"}), after=("claim",)),
        rule("work", {"rule": "constant", "value": 1}, after=("claim",)),
    )
    run = await h.start()
    assert run.state is RunState.FINISHED
    assert await result(h, run, "give-back") == {
        "skipped": True,
        "because": "the run did not escalate",
    }
    kinds = await h.kinds(run)
    assert kinds.index("step.finished:work:succeeded") < kinds.index(
        "step.finished:give-back:skipped"
    ), "a step on escalation never runs inside the sequence"


async def test_a_step_on_escalation_that_fails_keeps_the_others_running() -> None:
    h = Harness(
        rule("work", FAIL),
        rule("first", aside(FAIL)),
        rule("second", aside({"rule": "constant", "value": "released"})),
    )
    run = await h.start()
    assert run.state is RunState.ESCALATED
    assert run.step_run("first").state is StepState.FAILED
    assert run.step_run("second").state is StepState.SUCCEEDED
    assert run.reason == run.step_run("work").reason


async def test_a_step_of_the_sequence_may_not_depend_on_a_step_on_escalation() -> None:
    h = Harness(
        rule("give-back", aside({"rule": "constant", "value": "released"})),
        rule("work", {"rule": "constant", "value": 1}, after=("give-back",)),
    )
    with pytest.raises(UnsupportedWork, match="runs on escalation"):
        await h.start()


async def test_a_step_on_escalation_asks_nobody() -> None:
    h = Harness(
        rule("work", {"rule": "constant", "value": 1}),
        rule(
            "give-back",
            aside({"rule": "constant", "value": "released", "ask": {"question": "may I?"}}),
        ),
    )
    with pytest.raises(UnsupportedWork, match="asks nobody"):
        await h.start()


async def test_the_run_record_names_no_failure_while_none_happened() -> None:
    h = Harness(
        rule(
            "who",
            {
                "rule": "template",
                "text": "${run} ${failed}",
                "values": {"run": {"$run": "id"}, "failed": {"$run": "failed"}},
            },
        ),
    )
    run = await h.start()
    assert await result(h, run, "who") == f"{run.id} null"
