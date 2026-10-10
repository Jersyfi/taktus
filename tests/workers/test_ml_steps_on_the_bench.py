"""A step of method `ml` runs on the ML bench itself (ADR-0076, issue #216).

The bench is started as a process and reached over HTTP, as the control plane reaches it; the
engine runs on the in-memory stores of `tests/components/run/test_engine.py`. A model is trained
on the bench first, then a run predicts with it, pinned by its digest. What the engine does with
a prediction — the threshold, the fallback, the refusals — is
`tests/components/run/test_ml_steps.py`'s, against a scripted worker.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from components.run.test_engine import Harness, rule

from taktus.adapters.driven.workers.http import HttpWorker
from taktus.components.run.domain.model import RunState, StepState
from taktus.ports.worker import ComputeLimit, Limits
from taktus.shared.v1 import ExactnessClass, Fallback, Method, Step

from .test_mlbench import Bench, dataset, digest, train
from .test_mlbench import ml_bench as ml_bench  # the fixture

BUDGET = Limits(compute=ComputeLimit(seconds=600, resource_class="cpu.small"))


def classify(model: dict[str, Any], when: str, hosts: tuple[str, ...] = ()) -> Any:
    step = Step(
        id="classify",
        method=Method.ML,
        reason="three fixed classes, a classifier trained on them",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        fallback=Fallback(when=when, to=Method.HUMAN),
        model="kinds-clf@1.0.0",
        requires=("data.read", "ml.predict"),
        depends_on=("rows",),
    )
    work = {
        "model": model,
        "dataset": {"csv": {"$from": "rows"}},
        "allowed_hosts": list(hosts),
    }
    return step, work


async def predict(ml: Bench, model: dict[str, Any], when: str, hosts: tuple[str, ...] = ()) -> Any:
    rows = dataset(rows=12, labelled=False, seed=3).decode()
    async with HttpWorker(ml.endpoint) as worker:
        h = Harness(
            rule("rows", {"rule": "constant", "value": rows}),
            classify(model, when, hosts),
            workers=[worker],
        )
        return h, await h.start(budget=BUDGET)


async def test_a_step_of_method_ml_predicts_on_the_bench_reproducibly(ml_bench: Bench) -> None:
    _, _, trained = ml_bench.run(train(ml_bench, dataset(rows=900)))
    model = trained["model"]
    pinned = {"base64": base64.b64encode(model).decode(), "digest": digest(model)}
    # With three classes the likeliest one has a probability of at least a third: below 0.3
    # the model is never unsure, and the prediction is the step's result.
    h, run = await predict(ml_bench, pinned, "confidence < 0.3")
    assert run.state is RunState.FINISHED, run.reason
    step_run = run.step_run("classify")
    assert step_run.adapter is not None and step_run.consumption is not None
    assert step_run.checkpoint is not None and step_run.checkpoint.result_digest is not None
    content = await h.objects.get(step_run.checkpoint.result_digest)
    assert content is not None
    result = json.loads(content)
    assert result["model"] == "kinds-clf@1.0.0" and result["model_digest"] == digest(model)
    assert len(result["rows"]) == 12
    assert {row["class"] for row in result["rows"]} <= {"k0", "k1", "k2"}
    assert result["confidence"] == min(row["confidence"] for row in result["rows"])

    _, rerun = await predict(ml_bench, pinned, "confidence < 0.3")
    checkpoint = rerun.step_run("classify").checkpoint
    assert checkpoint is not None
    assert checkpoint.result_digest == step_run.checkpoint.result_digest, "the same result"

    # Asked to be sure of everything, the step goes to a person instead.
    _, unsure = await predict(ml_bench, pinned, "confidence <= 1")
    assert unsure.state is RunState.WAITING_HUMAN
    assert unsure.step_run("classify").state is StepState.WAITING_HUMAN


async def test_a_model_behind_a_uri_that_does_not_match_its_digest_fails_the_step(
    ml_bench: Bench,
) -> None:
    _, _, trained = ml_bench.run(train(ml_bench, dataset(rows=300), epochs=1))
    served = {**ml_bench.serve("model.json", trained["model"]), "digest": "sha256:" + "0" * 64}
    _, run = await predict(ml_bench, served, "confidence < 0.9", hosts=(ml_bench.host,))
    assert run.state is RunState.ESCALATED
    step_run = run.step_run("classify")
    assert step_run.state is StepState.FAILED and "digest" in (step_run.reason or "")
    assert not any(a.id in ("predictions", "result") for a in step_run.artifacts)
