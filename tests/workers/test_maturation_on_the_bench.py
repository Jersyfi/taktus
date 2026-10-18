"""Method maturation on the ML bench itself (ADR-0084, issue #217; ADR-0114, issue #218).

The bench is started as a process and reached over HTTP, as the control plane reaches it. The
run history is written by the run engine with a scripted language model; maturation then
trains a candidate on the bench twice, tries it on the cases it held out, and raises the
proposal to a person. The rules — the floor, the verdict, the request's shape — are
`tests/components/run/test_maturation.py`'s, against scripted workers.
"""

from __future__ import annotations

from components.run.test_maturation import BUDGET, PROCESS, STARTER, TENANT, World, separable
from composition.test_method_move import cases_on, moved

from taktus.adapters.driven.workers.http import HttpWorker
from taktus.components.run.application.service import ProposeMoves
from taktus.components.run.domain.model import RunState
from taktus.components.run.domain.service import maturation
from taktus.shared.v1 import Method

from .test_mlbench import Bench
from .test_mlbench import ml_bench as ml_bench  # the fixture


async def test_a_step_on_a_language_model_is_proposed_a_model_the_bench_trained(
    ml_bench: Bench,
) -> None:
    async with HttpWorker(ml_bench.endpoint) as bench:
        w = World(workers=[bench], uncalibrated_margin=1.0)
        await w.history(separable(540))
        (outcome,) = await w.propose.execute(
            ProposeMoves(TENANT, actor=STARTER, budget=BUDGET, process_version=PROCESS)
        )
    assert outcome.proposed, outcome.findings
    proposal = outcome.proposal
    assert proposal is not None
    e = proposal.evidence
    assert e.held_out == 108 and e.agreement >= maturation.MIN_AGREEMENT
    assert len(e.digests) == 2 and e.digests[0] == e.digests[1], "trained twice, the same model"
    assert e.ml_cost_per_case is not None and e.llm_cost_per_case is not None
    assert e.ml_cost_per_case < e.llm_cost_per_case
    # The model file is the training run's artifact, and it is the one the trial pinned.
    async with w.persistence.transaction(TENANT):
        training = await w.runs.get(TENANT, outcome.training_run or "")
        trial = await w.runs.get(TENANT, outcome.trial_run or "")
    assert training is not None and trial is not None
    assert training.state is RunState.FINISHED and trial.state is RunState.FINISHED
    model = training.step_run("train").artifact("model")
    assert model is not None and model.digest == e.digest
    assert trial.step("held-out").method is Method.ML
    assert trial.step("held-out").model == proposal.model
    (request,) = await w.proposals()
    assert request.id == outcome.request_id and e.digest in request.request.situation


async def test_the_accepted_move_runs_on_the_bench_reproducibly_and_measurably_cheaper(
    ml_bench: Bench,
) -> None:
    """The roadmap's `0.4.0` criterion against the bench itself (issue #218, ADR-0114): the
    proposal accepted, the step moved, 100 cases on the new version measured beside the version
    it replaced, and the same case answered the same twice."""
    async with HttpWorker(ml_bench.endpoint) as bench:
        w, _, version = await moved(workers=[bench])
        await cases_on(w, version, maturation.MOVE_CASES, unsure_every=maturation.MOVE_CASES + 1)
        one = await w.run_of(version, 10.2, 0.3, confidence=1.0, kind="k1")
        two = await w.run_of(version, 10.2, 0.3, confidence=1.0, kind="k1")
    (review,) = await w.review.execute(TENANT)
    assert review.verdict == "cheaper", review
    assert review.cost_per_case is not None and review.replaced_cost_per_case is not None
    assert review.cost_per_case < review.replaced_cost_per_case
    first, second = await w.result(one), await w.result(two)
    assert first == second and first["answered_by"] == "ml", "reproducible at the pinned model"
