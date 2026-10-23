"""A change held to its evaluation cases, and drift measured on the same cases (UC-4.18 §2,
ADR-0134, issues #431 and #408), over the memory stores.

A proposal that changes a step is run on the process's cases beside the active version when it
is rehearsed, and commissioned only once its evaluation passed, or against a regression with a
person's reason. A judge scores inside a run and falls back to its rule. The same cases run on
the process's schedule with no change, and a fall beyond the tolerance is a drift, an incident
where the process sends outward. Every evaluation names the model the provider reported. A
corrected draft is proposed as a case, reduced to what scoring needs, and enters the set once a
person confirmed it; one that would keep personal data the tenant does not allow is withheld.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fakes import FakeIdentifiers, FakeModel, FakeWorker
from fakes.identity import directory
from fakes.maturity import VERIFIED

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryObjectStore,
    MemoryPersistence,
    MemoryProvenanceStore,
    MemoryQueue,
    MemoryRepository,
)
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.command.application.service import CommissionPlan, CommissionPlanHandler
from taktus.components.governance.application.service import ConfigureWatch, Drifts, ExpectedRuns
from taktus.components.governance.domain.model import Incident, IncidentKind, WatchConfiguration
from taktus.components.process.application.service.proposals import (
    ProposalError,
    Proposals,
    Propose,
)
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import (
    CaseState,
    CorrectedCase,
    Evaluation,
    InvalidProcess,
    Process,
    ProcessVersion,
    Proposal,
)
from taktus.components.process.domain.model.evaluation import EvaluationState, Side, Verdict
from taktus.components.run.application.service import (
    CorrectResult,
    CorrectResultHandler,
    ResumeRun,
    RunEngine,
    StartRun,
)
from taktus.components.run.domain.model import Run
from taktus.composition.evaluations import Evaluations
from taktus.composition.proposals import ProposalActs
from taktus.ports.model import Completion, Prompt
from taktus.ports.worker import Limits
from taktus.shared.v1 import Command, Intent, Plan, PriceKinds, ReplyTo

TENANT = "t"
WHO = "idn_ada"
KIND = "Reply kindly to: ${message}"
SHORT = "Reply in one line to: ${message}"
SORRY = "We are sorry it came late. We refund the shipping costs."


class Clock:
    def __init__(self) -> None:
        self.current = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    async def sleep(self, seconds: float) -> None:
        return None


@dataclass
class Speaker(FakeModel):
    """A model whose draft follows its prompt, and whose judgement is what the test sets."""

    name: str = "draft-model-20261001"
    kind_answer: str = SORRY
    judgement: str = "0.9"

    async def complete(self, prompt: Prompt) -> Completion:
        self.prompts.append(prompt)
        if prompt.user.startswith("Criterion:"):
            text = self.judgement
        elif "kindly" in prompt.user:
            text = self.kind_answer
        else:
            text = "No."
        words = len(prompt.user.split())
        return Completion(
            text=text,
            model=self.name,
            tokens_in=words,
            tokens_out=len(text.split()),
            by_kind=PriceKinds(input=words, output=len(text.split())),
            finish="stop",
        )


def scorer(**over: Any) -> dict[str, Any]:
    return {
        "step": "draft",
        "method": "rule",
        "reason": "the reply must say what the target says, in words a rule can count",
        "exactness": "exact",
        "rule": {"kind": "overlap"},
        **over,
    }


JUDGE = scorer(
    method="llm",
    reason="whether a reply is kind is meaning, not words",
    rejected=[{"method": "rule", "why": "a kind reply can use any words"}],
    exactness="tolerant",
    fallback={"when": "the judge gives no number", "to": "rule"},
    rule={"kind": "contains"},
    purpose="judging",
    criterion="Is the reply as kind and as helpful as the target?",
)


def bundle(
    version: str,
    *,
    prompt: str = KIND,
    scorers: list[dict[str, Any]] | None = None,
    schedule: str | None = None,
    scoped: bool = False,
    cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    work: dict[str, Any] = {
        "purpose": "drafting",
        "prompt": prompt,
        "values": {"message": {"$input": "message"}},
    }
    inputs: dict[str, Any] = {
        "message": {"description": "what the customer wrote", "example": "late"},
        "mailbox": {"description": "where it arrived", "example": "support", "required": False},
    }
    if scoped:
        work["scope"] = {"subject": {"$input": "customer"}}
        inputs["customer"] = {"description": "the customer's number", "example": "c-1"}
    evaluation: dict[str, Any] = {
        "cases": cases
        if cases is not None
        else [
            {
                "id": "late",
                "inputs": {"message": "My parcel came a week late."}
                | ({"customer": "c-7"} if scoped else {}),
                "targets": {"draft": SORRY},
            }
        ],
        "scorers": scorers or [scorer()],
    }
    if schedule is not None:
        evaluation["schedule"] = schedule
    return {
        "id": "replies",
        "version": version,
        "name": "Replies",
        "autonomy": {"level": 2, "reason": "a test", "toward_next": "nothing"},
        "inputs": inputs,
        "steps": [
            {
                "id": "draft",
                "method": "llm",
                "reason": "a reply is written in the customer's words",
                "rejected": [{"method": "rule", "why": "no rule writes a reply"}],
                "exactness": "tolerant",
                "fallback": {"when": "the answer fails twice", "to": "human"},
                "work": work,
            }
        ],
        "limits": {"compute": {"seconds": 10, "resource_class": "cpu.small"}},
        "evaluation": evaluation,
    }


class World:
    def __init__(self, *, outward: bool = True) -> None:
        self.clock = Clock()
        self.ids = FakeIdentifiers()
        self.persistence = MemoryPersistence()
        self.runs = MemoryRepository(self.persistence, Run)
        self.identity = directory((TENANT,), persistence=self.persistence, clock=self.clock)
        self.ledger = self.identity.ledger
        self.queue = MemoryQueue(self.persistence, self.clock, lease_seconds=60)
        self.objects = MemoryObjectStore()
        self.model = Speaker()
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.runs,
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=MemoryProvenanceStore(self.persistence),
            workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
            clock=self.clock,
            ids=self.ids,
            telemetry=NoTelemetry(),
            queue=self.queue,
            connectors=StaticConnectorPool([]),
            models=StaticModelPool(
                [("model.fake", ["drafting", "judging"], self.model, "fake-model@1")]
            ),
        )
        self.processes = MemoryRepository(self.persistence, Process)
        self.versions = MemoryRepository(self.persistence, ProcessVersion)
        self.register = RegisterProcessVersionHandler(
            self.versions, self.persistence, self.processes, ledger=self.ledger
        )
        self.proposals = Proposals(
            self.versions,
            self.processes,
            MemoryRepository(self.persistence, Proposal),
            self.persistence,
            self.clock,
            self.ids,
        )
        self.commission = CommissionPlanHandler(
            MemoryRepository(self.persistence, Command),
            MemoryRepository(self.persistence, Plan),
            self.persistence,
            self.clock,
            self.ids,
        )
        self.incidents = MemoryRepository(self.persistence, Incident)
        self.watch = ExpectedRuns(
            self.incidents,
            MemoryRepository(self.persistence, WatchConfiguration),
            None,  # type: ignore[arg-type]  # configuring reads no ledger store
            self.ledger,
            self.persistence,
            self.clock,
        )
        self.outward = outward

        async def sends(version: ProcessVersion) -> bool:
            return self.outward

        self.evaluations = Evaluations(
            processes=self.processes,
            versions=self.versions,
            evaluations=MemoryRepository(self.persistence, Evaluation),
            cases=MemoryRepository(self.persistence, CorrectedCase),
            runs=self.runs,
            commission=self.commission,
            engine=self.engine,
            identities=self.identity.directory,
            drifts=Drifts(
                self.incidents,
                MemoryRepository(self.persistence, WatchConfiguration),
                self.ledger,
                self.persistence,
                self.clock,
            ),
            ledger=self.ledger,
            objects=self.objects,
            work=self.persistence,
            clock=self.clock,
            ids=self.ids,
            outward=sends,
        )
        self.acts = ProposalActs(
            proposals=self.proposals,
            processes=self.processes,
            versions=self.versions,
            runs=self.runs,
            register=self.register,
            commission=self.commission,
            engine=self.engine,
            identities=self.identity.directory,
            ledger=self.ledger,
            work=self.persistence,
            clock=self.clock,
            ids=self.ids,
            evaluations=self.evaluations,
        )

    async def setup(self, **over: Any) -> World:
        await self.identity.directory.add(TENANT, WHO, (TENANT, "support"))
        await self.register.execute(
            RegisterProcessVersion(bundle("1", **over), tenant=TENANT, by=WHO)
        )
        return self

    async def propose(self, prompt: str) -> Proposal:
        return await self.proposals.propose(
            Propose(TENANT, "replies", bundle("2", prompt=prompt), by=WHO)
        )

    async def drain(self) -> list[Run]:
        """Every queued run, run through."""
        ran: list[Run] = []
        while True:
            async with self.persistence.transaction(TENANT):
                jobs = await self.queue.claim(TENANT, "runner-a", 10)
            if not jobs:
                return ran
            for job in jobs:
                ran.append(
                    await self.engine.resume(
                        ResumeRun(
                            run_id=job.payload["run_id"],
                            actor="runner-a",
                            tenant=TENANT,
                            on_claim=True,
                        )
                    )
                )

    async def real_run(self, inputs: dict[str, Any]) -> Run:
        """A run of the active version that is no rehearsal: what a person corrects."""
        async with self.persistence.transaction(TENANT):
            version = await self.versions.get(TENANT, "replies@1")
        assert version is not None
        command = Command(
            id=self.ids.new("cmd"),
            channel="channel.web",
            identity=WHO,
            org_path=(TENANT, "support"),
            intent=Intent(raw="reply", recognised="process.run"),
            context={"inputs": inputs},
            reply_to=ReplyTo(channel="channel.web", address="ledger"),
            received_at=self.clock.now(),
        )
        plan = await self.commission.execute(
            CommissionPlan(
                command=command,
                tenant=TENANT,
                goal="reply",
                autonomy_level=3,
                steps=version.ordered(),
            )
        )
        run = await self.engine.submit(
            StartRun(
                plan=plan,
                work=version.work,
                budget=Limits.model_validate(dict(version.limits or {})),
                process_version=version.ref,
                actor=WHO,
                tenant=TENANT,
                inputs=inputs,
            )
        )
        await self.drain()
        async with self.persistence.transaction(TENANT):
            done = await self.runs.get(TENANT, run.id)
        assert done is not None
        return done

    async def kinds(self, prefix: str) -> list[str]:
        async with self.persistence.transaction(TENANT):
            entries = await self.ledger.entries(TENANT)
        return [f"{e.kind}:{e.outcome}" for e in entries if e.kind.startswith(prefix)]

    async def evaluated(self, proposal: Proposal) -> tuple[Proposal, Evaluation]:
        rehearsed, _ = await self.acts.rehearse(
            TENANT, "replies", proposal.id, WHO, {"message": "Where is my parcel?"}
        )
        assert rehearsed.evaluation is not None
        await self.drain()
        evaluation = await self.evaluations.advance(TENANT, rehearsed.evaluation)
        if evaluation.state is EvaluationState.JUDGING:
            await self.drain()
            evaluation = await self.evaluations.advance(TENANT, rehearsed.evaluation)
        return rehearsed, evaluation


async def test_a_change_runs_on_the_cases_beside_the_active_version_as_rehearsals() -> None:
    world = await World().setup()
    proposal = await world.propose(SHORT)
    rehearsed, _ = await world.acts.rehearse(
        TENANT, "replies", proposal.id, WHO, {"message": "Where is my parcel?"}
    )
    assert rehearsed.evaluation is not None
    evaluation = await world.evaluations.get(TENANT, "replies", rehearsed.evaluation)
    assert [(r.case, r.side) for r in evaluation.runs] == [
        ("late", Side.ACTIVE),
        ("late", Side.PROPOSED),
    ]
    async with world.persistence.transaction(TENANT):
        runs = [await world.runs.get(TENANT, r.run_id or "") for r in evaluation.runs]
    assert [(r.process_version, r.rehearsal) for r in runs if r is not None] == [
        ("replies@1", True),
        (f"replies@proposal-{proposal.id}", True),
    ]
    assert await world.kinds("evaluation.") == ["evaluation.started:change"]


async def test_a_regression_is_not_commissioned_unless_a_person_overrides_it_with_a_reason() -> (
    None
):
    world = await World().setup()
    proposal = await world.propose(SHORT)
    _, evaluation = await world.evaluated(proposal)
    assert evaluation.verdict is Verdict.REGRESSED
    active, proposed = evaluation.side(Side.ACTIVE), evaluation.side(Side.PROPOSED)
    assert active is not None and active.score == 1.0
    assert proposed is not None and proposed.score is not None and proposed.score < 0.95
    with pytest.raises(ProposalError) as refused:
        await world.acts.commission(TENANT, "replies", proposal.id, WHO)
    assert refused.value.kind == "regressed"
    assert "tolerance of 0.05" in str(refused.value)
    reason = "a one-line reply is what the customers asked for"
    version = await world.acts.commission(TENANT, "replies", proposal.id, WHO, override=reason)
    assert version.version == "2"
    overridden = await world.evaluations.get(TENANT, "replies", evaluation.id)
    assert overridden.override is not None
    assert overridden.override.reason == reason
    kinds = await world.kinds("evaluation.")
    assert kinds == [
        "evaluation.started:change",
        "evaluation.scored:regressed",
        "evaluation.overridden:regressed",
    ]
    async with world.persistence.transaction(TENANT):
        entries = await world.ledger.entries(TENANT)
    (entry,) = [e for e in entries if e.kind == "evaluation.overridden"]
    assert entry.refs.actor == WHO and entry.content_digest is not None
    assert await world.objects.get(entry.content_digest) == reason.encode()


async def test_a_change_that_holds_its_score_is_commissioned() -> None:
    world = await World().setup()
    proposal = await world.propose("Reply kindly and briefly to: ${message}")
    _, evaluation = await world.evaluated(proposal)
    assert evaluation.verdict is Verdict.PASSED
    version = await world.acts.commission(TENANT, "replies", proposal.id, WHO)
    assert version.version == "2"


async def test_a_change_not_yet_evaluated_is_not_commissioned() -> None:
    world = await World().setup()
    proposal = await world.propose(SHORT)
    rehearsed, _ = await world.acts.rehearse(
        TENANT, "replies", proposal.id, WHO, {"message": "Where is my parcel?"}
    )
    # Only the rehearsal itself runs through; the evaluation's runs wait in the queue.
    async with world.persistence.transaction(TENANT):
        jobs = await world.queue.claim(TENANT, "runner-a", 10)
    rehearsal = next(j for j in jobs if j.payload["run_id"] == rehearsed.rehearsal_run)
    await world.engine.resume(
        ResumeRun(
            run_id=rehearsal.payload["run_id"], actor="runner-a", tenant=TENANT, on_claim=True
        )
    )
    with pytest.raises(ProposalError) as refused:
        await world.acts.commission(TENANT, "replies", proposal.id, WHO, override="trust me")
    assert refused.value.kind == "unevaluated"


async def test_a_judge_scores_inside_a_run_and_falls_back_to_its_rule() -> None:
    world = await World().setup(scorers=[JUDGE])
    proposal = await world.propose("Reply kindly and briefly to: ${message}")
    _, evaluation = await world.evaluated(proposal)
    assert evaluation.state is EvaluationState.SCORED
    scores = [s for r in evaluation.results for s in r.scores]
    assert {(s.how, s.score, s.exactness.value) for s in scores} == {("judge", 0.9, "tolerant")}
    judged = [r for r in evaluation.runs if r.judges]
    assert len(judged) == 2
    async with world.persistence.transaction(TENANT):
        judge = await world.runs.get(TENANT, next(iter(judged[0].judges.values())))
    assert judge is not None and judge.rehearsal
    assert [s.method.value for s in judge.steps] == ["llm"]
    # A judge whose answer is no number from 0 to 1 falls back to its rule.
    world.model.judgement = "rather kind"
    proposal = await world.proposals.propose(
        Propose(TENANT, "replies", bundle("3", prompt="Reply kindly, please: ${message}"), by=WHO)
    )
    _, evaluation = await world.evaluated(proposal)
    scores = [s for r in evaluation.results for s in r.scores]
    assert {(s.how, s.score) for s in scores} == {("fallback", 1.0)}


async def test_a_judge_that_falls_back_to_a_person_leaves_the_verdict_incomplete() -> None:
    to_person = JUDGE | {"fallback": {"when": "no number", "to": "human"}}
    to_person.pop("rule")
    world = await World().setup(scorers=[to_person])
    world.model.judgement = "rather kind"
    proposal = await world.propose("Reply kindly and briefly to: ${message}")
    _, evaluation = await world.evaluated(proposal)
    assert evaluation.verdict is Verdict.INCOMPLETE
    with pytest.raises(ProposalError) as refused:
        await world.acts.commission(TENANT, "replies", proposal.id, WHO)
    assert refused.value.kind == "incomplete"
    await world.acts.commission(TENANT, "replies", proposal.id, WHO, override="read it myself")


async def test_drift_is_measured_on_the_schedule_and_raises_an_incident_where_it_speaks_out() -> (
    None
):
    world = await World().setup(schedule="hourly")
    started = await world.evaluations.look(TENANT)
    assert [e.purpose.value for e in started] == ["drift"]
    assert await world.evaluations.look(TENANT) == [], "one evaluation per slot"
    await world.drain()
    (first,) = await world.evaluations.look(TENANT)
    assert first.verdict is Verdict.FIRST
    (result,) = first.results
    assert result.models == {"draft": "draft-model-20261001"}
    # The provider changes the model behind the same name; nobody changes the process.
    world.model.name = "draft-model-20261101"
    world.model.kind_answer = "Parcels are sometimes late."
    world.clock.current += timedelta(hours=1)
    (second,) = await world.evaluations.look(TENANT)
    await world.drain()
    (scored,) = await world.evaluations.look(TENANT)
    assert scored.id == second.id and scored.verdict is Verdict.DRIFT
    assert scored.compared_with == first.id and scored.previous_score == 1.0
    (incident,) = await _incidents(world)
    assert incident.kind is IncidentKind.DRIFT
    assert incident.facts["model:draft"] == "draft-model-20261101"
    assert incident.facts["model:draft@before"] == "draft-model-20261001"
    assert "incident.raised:drift" in await world.kinds("incident.")
    assert await world.kinds("evaluation.scored") == [
        "evaluation.scored:first",
        "evaluation.scored:drift",
    ]


async def test_a_drift_of_a_process_that_sends_nothing_outward_raises_no_incident() -> None:
    world = await World(outward=False).setup(schedule="hourly")
    await world.evaluations.look(TENANT)
    await world.drain()
    await world.evaluations.look(TENANT)
    world.model.kind_answer = "Parcels are sometimes late."
    world.clock.current += timedelta(hours=1)
    await world.evaluations.look(TENANT)
    await world.drain()
    (scored,) = await world.evaluations.look(TENANT)
    assert scored.verdict is Verdict.DRIFT
    assert await _incidents(world) == []


async def test_a_corrected_draft_is_proposed_as_a_case_and_enters_the_set_once_confirmed() -> None:
    world = await World().setup()
    run = await world.real_run({"message": "It broke.", "mailbox": "support"})
    await CorrectResultHandler(world.runs, world.persistence, world.objects, world.ledger).execute(
        CorrectResult(TENANT, run.id, "draft", "We are sorry. We send a new one.", actor=WHO)
    )
    (proposed,) = await world.evaluations.propose_cases(TENANT)
    assert proposed.state is CaseState.PROPOSED
    assert proposed.case is not None
    assert dict(proposed.case.inputs) == {"message": "It broke."}, "only what a step reads"
    assert proposed.left_out == ("mailbox",)
    assert dict(proposed.case.targets) == {"draft": "We are sorry. We send a new one."}
    assert await world.evaluations.propose_cases(TENANT) == [], "proposed once"
    version = await _active(world)
    cases, _ = await world.evaluations.evaluation_set(TENANT, version)
    assert [c.id for c in cases] == ["late"], "a proposed case is not in the set"
    confirmed = await world.evaluations.confirm(TENANT, "replies", proposed.id, WHO)
    assert confirmed.state is CaseState.CONFIRMED
    cases, _ = await world.evaluations.evaluation_set(TENANT, version)
    assert [c.id for c in cases] == ["late", proposed.id]
    assert await world.kinds("evaluation.case") == [
        "evaluation.case_proposed:proposed",
        "evaluation.case_confirmed:confirmed",
    ]


async def test_a_case_keeps_no_personal_input_the_tenant_does_not_allow() -> None:
    world = await World().setup(scoped=True)
    version = await _active(world)
    cases, left_out = await world.evaluations.evaluation_set(TENANT, version)
    assert cases == () and "customer" in left_out["late"]
    run = await world.real_run({"message": "It broke.", "customer": "c-9"})
    await CorrectResultHandler(world.runs, world.persistence, world.objects, world.ledger).execute(
        CorrectResult(TENANT, run.id, "draft", "We are sorry.", actor=WHO)
    )
    (withheld,) = await world.evaluations.propose_cases(TENANT)
    assert withheld.state is CaseState.WITHHELD and withheld.case is None
    assert withheld.withheld is not None and "customer" in withheld.withheld
    assert await world.kinds("evaluation.case") == ["evaluation.case_withheld:personal"]
    # Once the tenant allows it, the case keeps its subject.
    await world.watch.configure(ConfigureWatch(TENANT, evaluation_subjects=True), by=WHO)
    cases, left_out = await world.evaluations.evaluation_set(TENANT, version)
    assert [c.id for c in cases] == ["late"] and left_out == {}


async def test_a_change_of_no_step_is_not_held_to_the_cases() -> None:
    world = await World().setup()
    changed = bundle("2")
    changed["autonomy"] = {"level": 1, "reason": "lower", "toward_next": "nothing"}
    proposal = await world.proposals.propose(Propose(TENANT, "replies", changed, by=WHO))
    rehearsed, _ = await world.acts.rehearse(
        TENANT, "replies", proposal.id, WHO, {"message": "Where is my parcel?"}
    )
    assert rehearsed.evaluation is None
    await world.drain()
    await world.acts.commission(TENANT, "replies", proposal.id, WHO)


@pytest.mark.parametrize(
    ("scorers", "finding"),
    [
        ([scorer(method="statistics")], "a scorer is a rule, or a language model"),
        ([JUDGE | {"rejected": []}], "it rejects `rule` and says why"),
        ([{k: v for k, v in JUDGE.items() if k != "fallback"}], "names a fallback"),
        ([JUDGE | {"exactness": "exact"}], "never from llm"),
        ([scorer(step="send")], "not a step of this process that produces a result"),
        ([scorer(rule={"kind": "pattern"})], "names the `pattern`"),
    ],
)
async def test_a_scorer_has_a_method_of_its_own_and_a_rule_comes_first(
    scorers: list[dict[str, Any]], finding: str
) -> None:
    world = World()
    with pytest.raises(InvalidProcess) as refused:
        await world.register.execute(
            RegisterProcessVersion(bundle("1", scorers=scorers), tenant=TENANT, by=WHO)
        )
    assert any(finding in f for f in refused.value.findings), refused.value.findings


async def test_a_case_gives_every_input_the_version_requires() -> None:
    world = World()
    with pytest.raises(InvalidProcess) as refused:
        await world.register.execute(
            RegisterProcessVersion(
                bundle("1", cases=[{"id": "empty", "targets": {"draft": SORRY}}]),
                tenant=TENANT,
                by=WHO,
            )
        )
    assert any("gives no value for the input(s) message" in f for f in refused.value.findings)


async def _incidents(world: World) -> list[Incident]:
    async with world.persistence.transaction(TENANT):
        return list(await world.incidents.list(TENANT))


async def _active(world: World) -> ProcessVersion:
    async with world.persistence.transaction(TENANT):
        version = await world.versions.get(TENANT, "replies@1")
    assert version is not None
    return version
