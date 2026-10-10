"""A step of method `ml`: a prediction on a worker, and its fallback when the model is unsure
(ADR-0076, issue #216).

The worker here is the scripted fake, offering `ml.predict` and producing the predictions it is
given. What the ML bench itself predicts is `tests/workers/test_ml_steps_on_the_bench.py`'s.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

import pytest
from fakes import FakeWorker, InnerStep

from taktus.components.run.application.service import ConfirmSteps
from taktus.components.run.domain.model import (
    Cause,
    RunError,
    RunState,
    StepState,
    UnsupportedWork,
)
from taktus.components.run.domain.service import prediction
from taktus.shared.v1 import ExactnessClass, Fallback, InputKind, Method, Step

from .test_engine import TENANT, Harness, rule

MODEL = b'{"weights": [1, 2, 3]}'
MODEL_DIGEST = "sha256:" + hashlib.sha256(MODEL).hexdigest()
ROWS = "a,b\n1.0,2.0\n3.0,4.0\n"
PERSON = "idn_person"


def predictions(*rows: tuple[str, float]) -> bytes:
    lines = ["row,class,confidence"]
    lines += [f"{n},{label},{confidence:.6f}" for n, (label, confidence) in enumerate(rows, 1)]
    return ("\n".join(lines) + "\n").encode()


def bench(*rows: tuple[str, float]) -> FakeWorker:
    return FakeWorker(
        capabilities_offered=("data.read", "ml.predict"),
        script=(InnerStep("predict", artifacts=(("predictions", predictions(*rows)),)),),
    )


def ml(
    id: str = "classify",
    *,
    when: str | None = "confidence < 0.9",
    to: Method = Method.HUMAN,
    requires: tuple[str, ...] = ("data.read", "ml.predict"),
    model: dict[str, Any] | None = None,
    after: tuple[str, ...] = ("rows",),
    dataset: dict[str, Any] | None = None,
) -> tuple[Step, dict[str, Any]]:
    step = Step(
        id=id,
        method=Method.ML,
        reason="six fixed classes, a classifier trained on them",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        fallback=None if when is None else Fallback(when=when, to=to),
        model="cost-centre-clf@1.0.0",
        requires=requires,
        depends_on=after or None,
    )
    pinned = {"base64": base64.b64encode(MODEL).decode(), "digest": MODEL_DIGEST}
    work = {
        "model": pinned if model is None else model,
        "dataset": {"csv": {"$from": "rows"}} if dataset is None else dataset,
    }
    return step, work


def source() -> tuple[Step, dict[str, Any]]:
    return rule("rows", {"rule": "constant", "value": ROWS})


def after_it(id: str = "use") -> tuple[Step, dict[str, Any]]:
    return rule(
        id,
        {"rule": "template", "text": "${v}", "values": {"v": {"$from": "classify"}}},
        after=("classify",),
    )


async def confirm(h: Harness, run_id: str, *, performed: bool) -> Any:
    return await h.engine.confirm(
        ConfirmSteps(
            run_id=run_id, steps=("classify",), actor=PERSON, tenant=TENANT, performed=performed
        )
    )


async def test_a_sure_prediction_is_the_steps_result_and_names_its_model() -> None:
    worker = bench(("k1", 0.97), ("k2", 0.91))
    h = Harness(source(), ml(), after_it(), workers=[worker])
    run = await h.start()
    assert run.state is RunState.FINISHED, run.reason
    task = worker.assignments[0].task
    assert task.inputs is not None
    assert task.inputs["operation"] == "predict"
    assert task.inputs["model"]["digest"] == MODEL_DIGEST
    assert base64.b64decode(task.inputs["dataset"]["base64"]).decode() == ROWS
    assert worker.assignments[0].frame.allowed_tools == ("data.read", "ml.predict")
    step_run = run.step_run("classify")
    assert step_run.checkpoint is not None and step_run.checkpoint.result_digest is not None
    content = await h.objects.get(step_run.checkpoint.result_digest)
    assert content is not None
    result = json.loads(content)
    assert result == {
        "model": "cost-centre-clf@1.0.0",
        "model_digest": MODEL_DIGEST,
        "confidence": 0.91,
        "threshold": "confidence < 0.9",
        "rows": [
            {"row": 1, "class": "k1", "confidence": 0.97},
            {"row": 2, "class": "k2", "confidence": 0.91},
        ],
    }
    assert [a.id for a in step_run.artifacts] == ["predictions", "result"]
    used = run.step_run("use")
    assert used.checkpoint is not None and used.checkpoint.result_digest is not None
    passed_on = await h.objects.get(used.checkpoint.result_digest)
    assert passed_on is not None and "k1" in json.loads(passed_on), "$from carried the result"
    kinds = await h.kinds(run)
    assert "step.admitted:classify" in kinds, "estimated and admitted like any worker step"
    assert "step.finished:classify:succeeded" in kinds
    assert step_run.consumption is not None and step_run.consumption.compute_seconds
    assert await h.verify()


async def test_its_provenance_names_the_model_and_the_rows_it_read() -> None:
    h = Harness(source(), ml(), workers=[bench(("k1", 0.95))])
    run = await h.start()
    assert run.state is RunState.FINISHED, run.reason
    async with h.persistence.transaction(TENANT):
        records = await h.provenance.of_run(TENANT, run.id)
    record = next(r for r in records if r.step_id == "classify")
    sources = {(i.kind, i.ref, i.digest) for i in record.inputs if i.kind is InputKind.SOURCE}
    assert (InputKind.SOURCE, "model cost-centre-clf@1.0.0", MODEL_DIGEST) in sources
    assert any(i.kind is InputKind.RESULT and i.step_id == "rows" for i in record.inputs)


async def test_the_same_model_and_rows_give_the_same_result() -> None:
    first = await Harness(source(), ml(), workers=[bench(("k1", 0.95))]).start()
    second = await Harness(source(), ml(), workers=[bench(("k1", 0.95))]).start()
    one, two = first.step_run("classify").checkpoint, second.step_run("classify").checkpoint
    assert one is not None and two is not None
    assert one.result_digest == two.result_digest


async def test_an_unsure_prediction_goes_to_a_person_and_never_leaves_the_step() -> None:
    h = Harness(source(), ml(), after_it(), workers=[bench(("k1", 0.97), ("k2", 0.71))])
    run = await h.start()
    assert run.state is RunState.WAITING_HUMAN and run.cause is Cause.PERSON
    step_run = run.step_run("classify")
    assert step_run.state is StepState.WAITING_HUMAN
    assert step_run.block is not None and step_run.block.cause == "fell_back"
    assert step_run.block.account == "wait.human"
    checkpoint = step_run.checkpoint
    assert checkpoint is None or checkpoint.result_digest is None, "no result of the step"
    assert step_run.reason is not None and "0.71" in step_run.reason
    held = run.step_run("use")
    assert held.state is StepState.PLANNED and held.block is not None
    assert held.block.cause == "held_back"
    entries = await h.entries(run)
    awaiting = next(e for e in entries if e.kind == "step.awaiting")
    assert awaiting.outcome == "fell_back" and awaiting.content_digest is not None
    document = await h.objects.get(awaiting.content_digest)
    assert document is not None
    fallback = json.loads(document)
    assert fallback["confidence"] == 0.71 and fallback["threshold"] == "confidence < 0.9"
    assert fallback["to"] == "human" and fallback["model_digest"] == MODEL_DIGEST
    assert fallback["predictions"] == step_run.artifacts[0].digest

    with pytest.raises(RunError, match="Perform it yourself"):
        await confirm(h, run.id, performed=False)
    run = await confirm(h, run.id, performed=True)
    assert run.state is RunState.FINISHED, run.reason
    done = run.step_run("classify")
    assert done.state is StepState.SUCCEEDED and done.confirmed_by == PERSON
    used = run.step_run("use")
    assert used.checkpoint is not None and used.checkpoint.result_digest is not None
    passed_on = await h.objects.get(used.checkpoint.result_digest)
    assert passed_on == b'"null"', "the dependant received nothing of the model's answer"
    assert "step.performed:classify" in await h.kinds(run)
    assert await h.verify()


async def test_a_dependant_cannot_reach_the_unsure_predictions_by_their_artifact() -> None:
    reads = rule(
        "use",
        {
            "rule": "template",
            "text": "${v}",
            "values": {"v": {"$from": "classify", "$artifact": "predictions"}},
        },
        after=("classify",),
    )
    h = Harness(source(), ml(), reads, workers=[bench(("k1", 0.5))])
    run = await h.start()
    run = await confirm(h, run.id, performed=True)
    assert run.state is RunState.ESCALATED
    assert run.step_run("use").state is StepState.FAILED
    assert "performed by a person" in (run.step_run("use").reason or "")


@pytest.mark.parametrize(
    ("when", "falls_back"),
    [
        ("confidence < 0.9", False),
        ("confidence <= 0.9", True),
        ("confidence<0.95", True),
        ("confidence < 0.5", False),
    ],
)
async def test_the_threshold_is_compared_as_written(when: str, falls_back: bool) -> None:
    h = Harness(source(), ml(when=when), workers=[bench(("k1", 0.9))])
    run = await h.start()
    expected = StepState.WAITING_HUMAN if falls_back else StepState.SUCCEEDED
    assert run.step_run("classify").state is expected


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"when": None}, "names its fallback"),
        ({"to": Method.LLM}, "falls back to a person in this version"),
        ({"when": "tests failed twice"}, "not a threshold the engine evaluates"),
        ({"when": "confidence < 1.5"}, "not a threshold the engine evaluates"),
        ({"requires": ("data.read",)}, "requires ml.predict"),
        ({"model": {"base64": "e30="}}, "digest"),
        ({"model": {"base64": "e30=", "digest": MODEL_DIGEST}}, "do not match"),
        ({"dataset": {"$from": "rows"}}, "dataset"),
    ],
)
async def test_an_ml_step_that_cannot_run_as_written_is_refused_before_the_run_starts(
    changes: dict[str, Any], reason: str
) -> None:
    worker = bench(("k1", 0.99))
    h = Harness(source(), ml(**changes), workers=[worker])
    with pytest.raises(UnsupportedWork, match=reason):
        await h.start()
    assert worker.assignments == []


async def test_predictions_that_cannot_be_read_fail_the_step() -> None:
    worker = FakeWorker(
        capabilities_offered=("data.read", "ml.predict"),
        script=(InnerStep("predict", artifacts=(("predictions", b"row,class,confidence\n"),)),),
    )
    run = await Harness(source(), ml(), workers=[worker]).start()
    assert run.state is RunState.ESCALATED
    step_run = run.step_run("classify")
    assert step_run.state is StepState.FAILED
    assert "no row" in (step_run.reason or "")


def test_the_steps_confidence_is_the_lowest_of_its_rows() -> None:
    rows = prediction.rows(predictions(("a", 0.99), ("b", 0.42), ("c", 0.8)))
    assert prediction.lowest(rows) == 0.42


@pytest.mark.parametrize(
    "content",
    [None, b"", b"row,label,p\n1,a,0.5\n", b"row,class,confidence\n1,a,1.5\n", b"\xff"],
)
def test_what_is_not_a_prediction_is_unreadable(content: bytes | None) -> None:
    with pytest.raises(prediction.Unreadable):
        prediction.rows(content)
