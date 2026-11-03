"""Method maturation of a step that reads only text, on the ML bench itself (ADR-0183, UC-4.25,
issues #210 and #218).

The run history is written by the run engine with a scripted language model that sorts short
titles into three topics. Maturation reads the titles as texts, the bench embeds them with its
neural encoder, trains a classifier on the embedding twice, tries it on the held-out cases, and
raises the proposal to a person. The moved step then predicts one case with its title through
the pinned model file.
"""

from __future__ import annotations

import json
from typing import Any

from components.run.test_maturation import BUDGET, STARTER, TENANT, World
from components.run.test_maturation import CLASSIFY as NUMBERS_STEP

from taktus.adapters.driven.workers.http import HttpWorker
from taktus.components.run.application.service import ProposeMoves, StartRun
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.components.run.domain.service import maturation
from taktus.shared.v1 import Commissioned, Method, Plan, PlanResult, PlanStatus, Step

from .test_mlbench import Bench
from .test_mlbench import ml_bench as ml_bench  # the fixture
from .test_mlbench_embeddings import TOPICS

PROCESS = "titles@1"
WORK = {
    "purpose": "triage",
    "system": "Answer with the topic only.",
    "prompt": "title=${title}",
    "values": {"title": {"$input": "title"}},
    "max_output_tokens": 8,
}
FILLER = "the a when this our we it after before with today again system page".split()


def title(n: int) -> tuple[str, str]:
    """The n-th title and its topic: two phrases of the topic among filler words, drawn from n."""
    names = sorted(TOPICS)
    topic = names[n % 3]
    phrases = TOPICS[topic]
    words = [FILLER[(n * 7 + k) % len(FILLER)] for k in range(4)]
    words.insert(n % 5, phrases[n % len(phrases)])
    words.insert((n // 3) % 6, phrases[(n // 5) % len(phrases)])
    return " ".join(words), topic


class Titles(World):
    """The world of `test_maturation`, its step reading a title instead of numbers."""

    def plan(self, step: Step = NUMBERS_STEP) -> Plan:
        return Plan(
            id="pln_titles",
            command_id="cmd_titles",
            goal="sort a request by its title",
            autonomy_level=3,
            steps=(step,),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=STARTER, at=self.clock.now()),
        )

    async def titled(self, text: str, topic: str) -> Run:
        self.model.answers[f"title={text}"] = topic
        run = await self.engine.start(
            StartRun(
                plan=self.plan(),
                work={"classify": WORK},
                budget=BUDGET,
                process_version=PROCESS,
                actor=STARTER,
                tenant=TENANT,
                inputs={"title": text},
            )
        )
        assert run.state is RunState.FINISHED, run.reason
        return run


async def proposed(w: Titles) -> Any:
    for n in range(540):
        await w.titled(*title(n))
    (outcome,) = await w.propose.execute(
        ProposeMoves(TENANT, actor=STARTER, budget=BUDGET, process_version=PROCESS)
    )
    return outcome


async def test_a_step_that_reads_text_is_proposed_a_model_the_bench_trained_on_its_embedding(
    ml_bench: Bench,
) -> None:
    async with HttpWorker(ml_bench.endpoint) as bench:
        w = Titles(workers=[bench], uncalibrated_margin=1.0)
        outcome = await proposed(w)
    assert outcome.proposed, outcome.findings
    proposal = outcome.proposal
    assert proposal is not None
    assert proposal.features == () and proposal.texts == ("title",) and proposal.left_out == ()
    e = proposal.evidence
    assert e.held_out == 108 and e.agreement >= maturation.MIN_AGREEMENT
    assert len(e.digests) == 2 and e.digests[0] == e.digests[1], "trained twice, the same model"
    assert e.ml_cost_per_case is not None and e.llm_cost_per_case is not None
    assert e.ml_cost_per_case < e.llm_cost_per_case
    async with w.persistence.transaction(TENANT):
        training = await w.runs.get(TENANT, outcome.training_run or "")
    assert training is not None
    model = training.step_run("train").artifact("model")
    assert model is not None
    content = await w.objects.get(model.digest)
    assert content is not None and set(json.loads(content)["text"]) == {"title"}
    (request,) = await w.proposals()
    assert "the text of title, embedded on the bench" in request.request.situation


async def test_the_moved_step_predicts_its_text_case_and_refuses_an_empty_text(
    ml_bench: Bench,
) -> None:
    async with HttpWorker(ml_bench.endpoint) as bench:
        w = Titles(workers=[bench], uncalibrated_margin=1.0)
        outcome = await proposed(w)
        proposal = outcome.proposal
        assert proposal is not None
        async with w.persistence.transaction(TENANT):
            training = await w.runs.get(TENANT, outcome.training_run or "")
        assert training is not None
        artifact = training.step_run("train").artifact("model")
        assert artifact is not None
        content = await w.objects.get(artifact.digest)
        assert content is not None
        bundle_step = {**NUMBERS_STEP.document(), "work": WORK}
        moved = maturation.moved_step(proposal, bundle_step, content, outcome.request_id or "")
        assert moved["work"]["dataset"] == {
            "values": WORK["values"],
            "features": [],
            "texts": ["title"],
        }
        step = Step.model_validate({k: v for k, v in moved.items() if k != "work"})
        assert step.method is Method.ML

        async def one(text: str) -> Run:
            w.model.answers[f"title={text}"] = "billing"
            return await w.engine.start(
                StartRun(
                    plan=w.plan(step),
                    work={"classify": moved["work"]},
                    budget=BUDGET,
                    process_version="titles@2",
                    actor=STARTER,
                    tenant=TENANT,
                    inputs={"title": text},
                )
            )

        sure = await one("the invoice and the payment amount due today")
        again = await one("the invoice and the payment amount due today")
        empty = await one("   ")
    assert sure.state is RunState.FINISHED, sure.reason
    first, second = await result(w, sure), await result(w, again)
    assert first["text"] == "billing" and first["answered_by"] == "ml", first
    assert first == second, "the same text, the same answer at the pinned model"
    failed = empty.step_run("classify")
    assert failed.state is StepState.FAILED
    assert "the text 'title' is not a text" in (failed.reason or "")


async def result(w: Titles, run: Run) -> dict[str, Any]:
    checkpoint = run.step_run("classify").checkpoint
    assert checkpoint is not None and checkpoint.result_digest is not None
    content = await w.objects.get(checkpoint.result_digest)
    assert content is not None
    document: dict[str, Any] = json.loads(content)
    return document
