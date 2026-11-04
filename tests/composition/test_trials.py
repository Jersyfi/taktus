"""A model tried on fixed cases before it is introduced, proposed or changed (#448, ADR-0149),
over the memory stores.

A trial runs every evaluation case of the processes that ask for a purpose once per candidate,
as a rehearsal with the purpose bound to the candidate for that run alone. The report sets the
candidates side by side. A trial is offered when a purpose's model has answered no step yet,
when Taktus proposes another model, and when the model a member answers as changes its
version; it is never started on its own, and it binds nothing beyond its runs.
"""

from __future__ import annotations

import pytest
from fakes import FakeWorker
from fakes.maturity import VERIFIED

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import MemoryProvenanceStore
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.accounting.application.service import (
    NamedCase,
    SpendHandler,
    TrialError,
    TrialReports,
)
from taktus.components.run.application.service import RunEngine
from taktus.composition.trials import Trials
from taktus.ports.ledger import Fact

from .test_evaluations import SORRY, TENANT, WHO, Speaker, World


class Trying:
    """The evaluations' world, with a second model configured that serves no purpose yet."""

    def __init__(self, world: World) -> None:
        self.world = world
        self.other = Speaker(name="other-model-20261101", kind_answer="Sorry, refunded.")
        self.pool = StaticModelPool(
            [
                ("model.fake", ["drafting", "judging"], world.model, "fake-model@1"),
                ("model.other", [], self.other, "other-model@1"),
            ]
        )
        world.engine = RunEngine(
            maturities=VERIFIED,
            runs=world.runs,
            work=world.persistence,
            objects=world.objects,
            ledger=world.ledger,
            provenance=MemoryProvenanceStore(world.persistence),
            workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
            clock=world.clock,
            ids=world.ids,
            telemetry=NoTelemetry(),
            queue=world.queue,
            connectors=StaticConnectorPool([]),
            models=self.pool,
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
        )


async def trying() -> Trying:
    return Trying(await World().setup())


async def test_a_trial_runs_each_case_once_per_candidate_and_sets_them_side_by_side() -> None:
    """The verification of #448: for a purpose, the fixed cases run with each candidate, and
    the report states per candidate the cases passed, money, tokens in and out, wall time and
    the results side by side; the case whose results differ is named."""
    t = await trying()
    trial = await t.trials.start(TENANT, "drafting", ["model.fake", "model.other"], WHO)
    assert trial.cases[0].key == "replies/late"
    assert set(trial.runs) == {"model.fake", "model.other"}
    ran = await t.world.drain()
    assert len(ran) == 2 and all(run.rehearsal for run in ran)
    assert {run.bindings["drafting"] for run in ran} == {"model.fake", "model.other"}
    assert len(t.world.model.prompts) == 1 and len(t.other.prompts) == 1
    read = await t.trials.read(TENANT, trial.id)
    assert read.settled
    fake, other = read.report.candidates
    assert (fake.model, other.model) == ("model.fake", "model.other")
    assert fake.passed == other.passed == 1
    assert fake.tokens_in > 0 and other.tokens_out > 0
    assert read.report.differing == ("replies/late",)
    async with t.world.persistence.transaction(TENANT):
        started = [e for e in await t.world.ledger.entries(TENANT) if e.kind == "trial.started"]
    assert [(e.outcome, e.refs.actor) for e in started] == [("asked", WHO)]


async def test_a_trial_binds_nothing_beyond_its_own_runs() -> None:
    """Choosing a model stays the person's act: after a trial the purpose routes as configured."""
    t = await trying()
    await t.trials.start(TENANT, "drafting", ["model.other"], WHO)
    await t.world.drain()
    real = await t.world.real_run({"message": "late"})
    assert real.bindings == {}
    assert (await t.pool.chain("drafting"))[0].adapter == "model.fake"
    assert t.world.model.prompts and t.other.prompts
    assert SORRY  # the active version's own answer is unchanged


@pytest.mark.parametrize(
    ("purpose", "candidates", "kind"),
    [
        ("drafting", [], "invalid"),
        ("drafting", ["model.absent"], "invalid"),
        ("summarising", ["model.fake"], "empty"),
    ],
)
async def test_a_trial_without_candidates_or_cases_is_refused(
    purpose: str, candidates: list[str], kind: str
) -> None:
    t = await trying()
    with pytest.raises(TrialError) as refused:
        await t.trials.start(TENANT, purpose, candidates, WHO)
    assert refused.value.kind == kind


async def test_a_trial_is_offered_when_a_purpose_s_model_has_answered_nothing_yet() -> None:
    t = await trying()
    (offer,) = await t.trials.offers(TENANT)
    assert (offer.purpose, offer.occasion, offer.model) == ("drafting", "introduced", "model.fake")
    assert offer.candidates == ("model.fake", "model.other")
    await t.trials.start(TENANT, "drafting", list(offer.candidates), WHO, occasion="introduced")
    assert await t.trials.offers(TENANT) == []


async def test_a_trial_is_offered_when_taktus_proposes_another_model() -> None:
    t = await trying()
    await t.trials.start(TENANT, "drafting", ["model.fake"], WHO)
    await t.trials.propose(TENANT, "drafting", "model.other", "cheaper for the same cases")
    (offer,) = await t.trials.offers(TENANT)
    assert (offer.occasion, offer.model, offer.reason) == (
        "proposed",
        "model.other",
        "cheaper for the same cases",
    )
    assert offer.candidates == ("model.other", "model.fake")
    with pytest.raises(TrialError):
        await t.trials.propose(TENANT, "drafting", "model.absent", "x")


async def test_a_trial_is_offered_when_the_model_a_member_answers_as_changes_version() -> None:
    t = await trying()
    await t.world.real_run({"message": "late"})
    assert await t.trials.offers(TENANT) == []
    t.world.model.name = "draft-model-20261201"
    t.world.clock.current = t.world.clock.current.replace(hour=11)
    await t.world.real_run({"message": "late"})
    (offer,) = await t.trials.offers(TENANT)
    assert (offer.occasion, offer.model) == ("changed", "model.fake")
    assert "draft-model-20261001" in offer.reason and "draft-model-20261201" in offer.reason
    t.world.clock.current = t.world.clock.current.replace(hour=12)
    await t.trials.start(TENANT, "drafting", ["model.fake"], WHO, occasion="changed")
    assert await t.trials.offers(TENANT) == []


# --- a person declines an offer, and names cases of their own (ADR-0149 amended, #448) --------


async def test_a_declined_offer_is_not_offered_again_until_its_occasion_arises_anew() -> None:
    t = await trying()
    await t.trials.start(TENANT, "drafting", ["model.fake"], WHO)
    await t.trials.propose(TENANT, "drafting", "model.other", "cheaper for the same cases")
    t.world.clock.current = t.world.clock.current.replace(hour=11)
    await t.trials.decline(TENANT, "drafting", "proposed", "model.other", WHO, "not now")
    assert await t.trials.offers(TENANT) == []
    async with t.world.persistence.transaction(TENANT):
        declined = [e for e in await t.world.ledger.entries(TENANT) if e.kind == "trial.declined"]
    assert [(e.outcome, e.refs.actor) for e in declined] == [("proposed", WHO)]
    t.world.clock.current = t.world.clock.current.replace(hour=12)
    await t.trials.propose(TENANT, "drafting", "model.other", "cheaper again")
    (offer,) = await t.trials.offers(TENANT)
    assert (offer.occasion, offer.reason) == ("proposed", "cheaper again"), "proposed anew"


async def test_only_an_offer_that_stands_can_be_declined() -> None:
    t = await trying()
    with pytest.raises(TrialError) as no_offer:
        await t.trials.decline(TENANT, "drafting", "proposed", "model.other", WHO, "")
    assert no_offer.value.kind == "unknown"
    with pytest.raises(TrialError) as asked:
        await t.trials.decline(TENANT, "drafting", "asked", "model.fake", WHO, "")
    assert asked.value.kind == "invalid"
    await t.trials.decline(TENANT, "drafting", "introduced", "model.fake", WHO, "known model")
    assert await t.trials.offers(TENANT) == []


async def test_a_case_a_person_names_runs_beside_the_evaluation_cases() -> None:
    t = await trying()
    own = [NamedCase(process="replies", inputs={"message": "where is my parcel"})]
    trial = await t.trials.start(TENANT, "drafting", ["model.fake", "model.other"], WHO, own=own)
    assert [c.key for c in trial.cases] == ["replies/late", "replies/named-1"]
    assert trial.cases[1].named and not trial.cases[0].named
    ran = await t.world.drain()
    assert len(ran) == 4
    assert {run.inputs["message"] for run in ran} == {
        "My parcel came a week late.",
        "where is my parcel",
    }, "the evaluation case's inputs and the person's"
    read = await t.trials.read(TENANT, trial.id)
    assert all(c.passed == 2 for c in read.report.candidates)
    with pytest.raises(TrialError) as elsewhere:
        await t.trials.start(
            TENANT, "drafting", ["model.fake"], WHO, own=[NamedCase(process="absent")]
        )
    assert elsewhere.value.kind == "invalid" and "case 1" in str(elsewhere.value)


# --- model routing proposes a trial of a member it switched to (ADR-0200, #448) ---------------


async def test_a_member_routing_switched_to_is_proposed_for_a_trial_once() -> None:
    t = await trying()
    t.pool = StaticModelPool(
        [
            ("model.fake", ["drafting", "judging"], t.world.model, "fake-model@1"),
            ("model.other", ["drafting"], t.other, "other-model@1"),
        ]
    )
    t.trials._models = t.pool
    run = await t.world.real_run({"message": "late"})
    assert await t.trials.routed(TENANT) == [], "the first member answered: nothing switched"
    async with t.world.persistence.transaction(TENANT):
        (answered,) = [
            e
            for e in await t.world.ledger.entries(TENANT, run.id)
            if e.kind == "step.finished" and e.adapter == "model.fake"
        ]
        await t.world.ledger.record(
            TENANT,
            Fact(
                kind="step.finished",
                refs=answered.refs,
                method=answered.method,
                adapter="model.other",
                outcome="succeeded",
            ),
        )
    assert await t.trials.routed(TENANT) == [("drafting", "model.other")]
    offers = [o for o in await t.trials.offers(TENANT) if o.occasion == "proposed"]
    (offer,) = offers
    assert offer.model == "model.other" and "routing switched drafting" in offer.reason
    assert await t.trials.routed(TENANT) == [], "proposed once"
