"""A model reaches a step's real runs only after a trial found the quality held with it on the
cases of the step's process (ADR-0249, UC-8.2, UC-8.9), over the memory stores.

The replacement of the model behind a purpose is a change of configuration. The trial of the
purpose is its validation run: it runs every process that asks the purpose on its cases, and
reports per process whether the quality held. Until it has, the replacement serves no real run.
"""

from __future__ import annotations

from fakes import FakeWorker
from fakes.maturity import VERIFIED

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import MemoryProvenanceStore
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.accounting.application.service import SpendHandler, TrialReports
from taktus.components.run.application.service import RunEngine
from taktus.components.run.domain.model import RunState
from taktus.composition.trials import Trials
from taktus.composition.validation import Validations

from .test_evaluations import SORRY, TENANT, WHO, Speaker, World


class Validating:
    """The evaluations' world, its engine held to validations, with `chain` serving
    `drafting`: `model.good` answers as the case's target does, `model.poor` does not."""

    def __init__(self, world: World, chain: list[str]) -> None:
        self.world = world
        self.good = Speaker(name="good-model-20261101", kind_answer=SORRY)
        self.poor = Speaker(name="poor-model-20261101", kind_answer="Sorry, refunded.")
        speakers = {"model.good": self.good, "model.poor": self.poor}
        members = [(name, ["drafting"], speakers[name], f"{name}@1") for name in chain]
        members += [
            (name, [], speakers[name], f"{name}@1")
            for name in sorted(speakers)
            if name not in chain
        ]
        members.append(("model.fake", ["judging"], world.model, "fake-model@1"))
        self.pool = StaticModelPool(members)
        self.validations = Validations(
            versions=world.versions,
            runs=world.runs,
            ledger=world.ledger,
            objects=world.objects,
            work=world.persistence,
        )
        self.validations.attach(world.evaluations)
        self.provenance = MemoryProvenanceStore(world.persistence)
        world.engine = RunEngine(
            maturities=VERIFIED,
            runs=world.runs,
            work=world.persistence,
            objects=world.objects,
            ledger=world.ledger,
            provenance=self.provenance,
            workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
            clock=world.clock,
            ids=world.ids,
            telemetry=NoTelemetry(),
            queue=world.queue,
            connectors=StaticConnectorPool([]),
            models=self.pool,
            evaluated=self.validations,
        )
        spend = SpendHandler(world.ledger, world.objects, world.persistence)
        self.trials = Trials(
            processes=world.processes,
            versions=world.versions,
            runs=world.runs,
            evaluations=world.evaluations,
            commission=world.commission,
            engine=world.engine,
            identities=world.identity.directory,
            models=self.pool,
            reports=TrialReports(world.ledger, spend, world.persistence),
            ledger=world.ledger,
            objects=world.objects,
            work=world.persistence,
            clock=world.clock,
            ids=world.ids,
            validations=self.validations,
        )


async def validating(chain: list[str]) -> Validating:
    return Validating(await World().setup(), chain)


async def test_a_replacement_reaches_real_runs_only_after_its_validation_run_held() -> None:
    """UC-8.9: replacing the provider behind a purpose is a configuration change followed by a
    validation run of every process that uses the purpose; the replacement reaches runs for real
    only after it has reported, per process, whether the quality held."""
    v = await validating(["model.good"])
    before = await v.world.real_run({"message": "late"})
    assert before.state is not RunState.FINISHED
    assert v.good.prompts == [], "no real run reached the model before its validation"
    (offer,) = await v.trials.offers(TENANT)
    assert (offer.occasion, offer.model) == ("introduced", "model.good")

    trial = await v.trials.start(TENANT, "drafting", ["model.good"], WHO, occasion="introduced")
    pending = await v.trials.read(TENANT, trial.id)
    assert [x.verdict for x in pending.validations] == ["pending"]
    await v.world.drain()
    read = await v.trials.read(TENANT, trial.id)
    (validation,) = read.validations
    assert (validation.process, validation.model, validation.verdict) == (
        "replies",
        "model.good",
        "held",
    )
    assert validation.scores == {"draft": 1.0} and validation.baseline == {"draft": 1.0}

    asked = len(v.good.prompts)
    after = await v.world.real_run({"message": "late"})
    assert after.state is RunState.FINISHED
    assert len(v.good.prompts) == asked + 1


async def test_a_step_is_routed_past_a_model_whose_quality_fell_on_its_cases() -> None:
    """UC-8.2: a model is eligible for a step only after it passed the step's evaluation. The
    first member fell on the process's cases; the route passes over it, says why, and takes
    the one that held."""
    v = await validating(["model.poor", "model.good"])
    trial = await v.trials.start(TENANT, "drafting", ["model.poor", "model.good"], WHO)
    await v.world.drain()
    read = await v.trials.read(TENANT, trial.id)
    verdicts = {x.model: (x.verdict, x.fell) for x in read.validations}
    assert verdicts == {"model.good": ("held", ()), "model.poor": ("fell", ("draft",))}

    poor, good = len(v.poor.prompts), len(v.good.prompts)
    run = await v.world.real_run({"message": "late"})
    assert run.state is RunState.FINISHED
    assert (len(v.poor.prompts), len(v.good.prompts)) == (poor, good + 1)
    async with v.world.persistence.transaction(TENANT):
        (record,) = await v.provenance.of_run(TENANT, run.id)
    assert record.route is not None and record.route.adapter == "model.good"
    assert [(s.adapter, s.reason) for s in record.route.skipped] == [
        ("model.poor", "not_evaluated")
    ]


async def test_a_rehearsal_is_not_held_to_validations() -> None:
    """A rehearsal acts on nothing: it may run on a model no trial validated yet."""
    v = await validating(["model.good"])
    proposal = await v.world.propose("Reply kindly and briefly to: ${message}")
    _, evaluation = await v.world.evaluated(proposal)
    assert evaluation.state.value == "scored"
    assert v.good.prompts, "the evaluation's rehearsals ran on the model"
