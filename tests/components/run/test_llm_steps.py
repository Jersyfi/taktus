"""`llm` steps in the run engine, against a fake model: the prompt rendered from references,
the answer checked before it leaves the step, tokens counted, the model that answered in the
provenance."""

from __future__ import annotations

from typing import Any

from fakes import FakeModel

from taktus.adapters.driven.models import StaticModelPool
from taktus.components.run.application.service import RunEngine
from taktus.components.run.domain.model import RunState
from taktus.shared.v1 import ExactnessClass, Fallback, Method, Step

from .test_engine import TENANT, Harness, rule


def llm(
    id: str, work: dict[str, Any], *, after: tuple[str, ...] = ()
) -> tuple[Step, dict[str, Any]]:
    step = Step(
        id=id,
        method=Method.LLM,
        reason="judgement under ambiguity",
        rejected=(),
        exactness=ExactnessClass.SOURCED,
        fallback=Fallback(when="the answer fails the check twice", to=Method.HUMAN),
        depends_on=after or None,
    )
    return step, work


class ModelHarness(Harness):
    def __init__(self, *definitions: tuple[Step, dict[str, Any]], model: FakeModel | None = None):
        super().__init__(*definitions)
        self.model = model or FakeModel()
        self.engine = RunEngine(
            runs=self.runs,
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=self.provenance,
            workers=self.engine._workers,
            clock=self.clock,
            ids=self.ids,
            telemetry=self.engine._telemetry,
            models=StaticModelPool([("model.fake", ["reasoning"], self.model, "fake-model@1")]),
        )


WORK = {
    "purpose": "reasoning",
    "system": "You write acceptance criteria.",
    "prompt": "Issue #${number}: ${title}\n\nWrite acceptance criteria.",
    "values": {
        "number": {"$from": "issue", "$select": "number"},
        "title": {"$from": "issue", "$select": "title"},
    },
    "pattern": r"^## Acceptance criteria",
}


async def test_the_answer_is_the_result_and_the_model_is_in_the_provenance() -> None:
    h = ModelHarness(
        rule("issue", {"rule": "constant", "value": {"number": 11, "title": "Report git"}}),
        llm("refine", WORK, after=("issue",)),
    )
    run = await h.start()
    assert run.state is RunState.FINISHED
    refine = run.step_run("refine")
    assert refine.adapter == "model.fake"
    assert refine.consumption is not None
    assert refine.consumption.tokens_in > 0 and refine.consumption.tokens_out > 0
    assert refine.checkpoint is not None and refine.checkpoint.result_digest is not None
    content = await h.objects.get(refine.checkpoint.result_digest)
    assert content is not None and b"## Acceptance criteria" in content
    prompt = h.model.prompts[0]
    assert prompt.user.startswith("Issue #11: Report git")
    assert prompt.system == "You write acceptance criteria."
    async with h.persistence.transaction(TENANT):
        records = await h.provenance.of_run(TENANT, run.id)
    record = next(r for r in records if r.step_id == "refine")
    assert record.adapter == "model.fake" and record.adapter_version == "fake-model@1"
    assert [i.step_id for i in record.inputs] == ["issue"]
    assert "egress" not in " ".join(await h.kinds(run))


async def test_an_answer_that_fails_the_check_does_not_leave_the_step() -> None:
    h = ModelHarness(
        rule("issue", {"rule": "constant", "value": {"number": 1, "title": "t"}}),
        llm("refine", WORK, after=("issue",)),
        model=FakeModel(answer="Sure! Here are some thoughts."),
    )
    run = await h.start()
    assert run.state is RunState.ESCALATED
    reason = run.step_run("refine").reason or ""
    assert "does not match" in reason and "the check decides" in reason
    assert run.step_run("refine").consumption is not None, "the tokens were spent all the same"


async def test_a_cut_off_answer_and_an_unreachable_model_fail_the_step() -> None:
    h = ModelHarness(
        llm("draft", {**WORK, "values": {}, "prompt": "x"}), model=FakeModel(finish="length")
    )
    run = await h.start()
    assert run.state is RunState.ESCALATED
    assert "output limit" in (run.step_run("draft").reason or "")
    h = ModelHarness(
        llm("draft", {**WORK, "values": {}, "prompt": "x"}),
        model=FakeModel(unreachable="the model endpoint x did not answer"),
    )
    run = await h.start()
    assert run.state is RunState.ESCALATED
    assert "did not answer" in (run.step_run("draft").reason or "")


async def test_a_purpose_without_a_model_fails_the_step_and_names_the_setting() -> None:
    h = ModelHarness(llm("draft", {**WORK, "purpose": "triage", "values": {}, "prompt": "x"}))
    run = await h.start()
    assert run.state is RunState.ESCALATED
    reason = run.step_run("draft").reason or ""
    assert "'triage'" in reason and "TAKTUS_MODEL_ENDPOINT" in reason
    assert h.model.prompts == []
