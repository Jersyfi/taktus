"""A plan worked out in versions, commissioned as an act of its own (ADR-0237, UC-1.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fakes import FakeClock, FakeIdentifiers

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.command.application.service import (
    CommissionDraft,
    OpenDraft,
    PlanDialogue,
    PlanIncomplete,
    ReviseDraft,
    Unestimable,
)
from taktus.components.command.domain.model import PARTS, Estimate, PlanDraft
from taktus.components.ledger.application.service import ChainedLedger
from taktus.shared.v1 import (
    Command,
    ExactnessClass,
    Fallback,
    Intent,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    ReplyTo,
    Step,
)

AT = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
TENANT = "acme"
STEP_A = Step(
    id="a",
    method=Method.RULE,
    reason="a rule reads the invoice",
    rejected=(),
    exactness=ExactnessClass.EXACT,
)
STEP_B = Step(
    id="b",
    method=Method.WORKER,
    reason="a worker drafts the reply",
    rejected=(),
    exactness=ExactnessClass.FREE,
    fallback=Fallback(when="the draft is refused", to=Method.HUMAN),
    requires=("shell.script",),
    depends_on=("a",),
)


class Dialogue:
    def __init__(self) -> None:
        self.persistence = MemoryPersistence()
        self.clock = FakeClock(AT)
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.plans = MemoryRepository(self.persistence, Plan)
        self.dialogue = PlanDialogue(
            MemoryRepository(self.persistence, Command),
            MemoryRepository(self.persistence, PlanDraft),
            self.plans,
            self.ledger,
            self.persistence,
            self.clock,
            FakeIdentifiers(),
        )
        self.command = Command(
            id="cmd_1",
            channel="channel.chat",
            identity="idn_p",
            org_path=(TENANT,),
            intent=Intent(raw="answer supplier invoices"),
            reply_to=ReplyTo(channel="channel.chat", address="C1"),
            received_at=AT,
        )

    async def kinds(self) -> list[str]:
        async with self.persistence.transaction(TENANT):
            return [
                f"{e.kind}:{e.refs.plan_id}:{e.refs.actor}"
                for e in await self.ledger.entries(TENANT)
            ]


async def test_a_plan_lacking_a_part_is_refused_and_the_refusal_names_what_is_missing() -> None:
    d = Dialogue()
    draft = await d.dialogue.open(OpenDraft(command=d.command, tenant=TENANT, goal="g"))
    with pytest.raises(PlanIncomplete) as refused:
        await d.dialogue.commission(CommissionDraft(draft.id, TENANT, by="idn_p"))
    assert refused.value.missing == PARTS[1:]
    for part in PARTS[1:]:
        assert part in str(refused.value)
    assert await d.kinds() == [], "a refusal writes nothing"
    draft = await d.dialogue.revise(
        ReviseDraft(
            draft.id,
            TENANT,
            by="idn_p",
            changes={"steps": [STEP_A], "due": AT + timedelta(days=3), "autonomy_level": 2},
        )
    )
    with pytest.raises(PlanIncomplete, match="the autonomy level with its reason"):
        await d.dialogue.commission(CommissionDraft(draft.id, TENANT, by="idn_p"))


async def test_a_step_that_cannot_be_estimated_refuses_the_plan_before_anything_runs() -> None:
    d = Dialogue()
    draft = await d.dialogue.open(
        OpenDraft(
            command=d.command,
            tenant=TENANT,
            goal="answer supplier invoices",
            steps=(STEP_A, STEP_B),
            due=AT + timedelta(days=1),
            autonomy_level=2,
            autonomy_reason="a person confirms every reply until the drafts are trusted",
            estimates=(Estimate(step_id="a", figure=0.2, basis="the rule's last 30 runs"),),
        )
    )
    with pytest.raises(Unestimable) as refused:
        await d.dialogue.commission(CommissionDraft(draft.id, TENANT, by="idn_p"))
    assert refused.value.steps == ("b",)
    assert await d.kinds() == []


async def test_an_estimate_without_a_basis_is_shown_as_a_guess_never_as_a_figure() -> None:
    founded = Estimate(step_id="a", figure=12, unit="seconds", basis="the median of 20 runs")
    guessed = Estimate(step_id="b", figure=300, unit="tokens")
    assert founded.shown() == "step a: 12 seconds, computed from the median of 20 runs"
    assert not founded.guess and guessed.guess
    assert guessed.shown().startswith("step b: a guess of about 300 tokens")
    assert "computed from nothing" in guessed.shown()
    assert "cannot be estimated" in Estimate(step_id="c").shown()


async def test_commissioning_records_the_version_and_who_and_a_change_needs_it_again() -> None:
    d = Dialogue()
    draft = await d.dialogue.open(
        OpenDraft(
            command=d.command,
            tenant=TENANT,
            goal="answer supplier invoices",
            steps=(STEP_A, STEP_B),
            process_version="invoices@3",
            due=AT + timedelta(days=1),
            autonomy_level=2,
            autonomy_reason="a person confirms every reply until the drafts are trusted",
            estimates=(
                Estimate(step_id="a", figure=0.2, basis="the rule's last 30 runs"),
                Estimate(step_id="b", figure=40),
            ),
        )
    )
    assert not draft.is_commissioned
    plan = await d.dialogue.commission(CommissionDraft(draft.id, TENANT, by="idn_owner"))
    assert plan.id == f"{draft.id}@v1" and plan.status is PlanStatus.COMMISSIONED
    assert plan.commissioned is not None and plan.commissioned.by == "idn_owner"
    assert plan.results_in is PlanResult.RUN and plan.due == AT + timedelta(days=1)
    assert await d.kinds() == [f"plan.commissioned:{draft.id}@v1:idn_owner"]

    revised = await d.dialogue.revise(
        ReviseDraft(draft.id, TENANT, by="idn_p", changes={"due": AT + timedelta(days=2)})
    )
    assert revised.version == 2 and not revised.is_commissioned
    still = await d.dialogue.commissioned(TENANT, draft.id)
    assert still == plan, "what runs is the version that was commissioned, unchanged"
    again = await d.dialogue.commission(CommissionDraft(draft.id, TENANT, by="idn_owner"))
    assert again.id == f"{draft.id}@v2" and again.due == AT + timedelta(days=2)
    assert (await d.dialogue.get(TENANT, draft.id)).is_commissioned
    assert (await d.kinds())[-2:] == [
        f"plan.revised:{draft.id}@v2:idn_p",
        f"plan.commissioned:{draft.id}@v2:idn_owner",
    ]


async def test_a_plan_results_in_a_run_or_in_a_new_process_version() -> None:
    assert {r.value for r in PlanResult} == {"run", "process_version"}
    d = Dialogue()
    draft = await d.dialogue.open(
        OpenDraft(
            command=d.command,
            tenant=TENANT,
            goal="a new process for supplier invoices",
            steps=(STEP_A,),
            due=AT + timedelta(days=7),
            autonomy_level=1,
            autonomy_reason="a new process starts where a person performs every act",
            estimates=(Estimate(step_id="a", figure=1, basis="the rule's declared cost"),),
            results_in=PlanResult.PROCESS_VERSION,
        )
    )
    plan = await d.dialogue.commission(CommissionDraft(draft.id, TENANT, by="idn_p"))
    assert plan.results_in is PlanResult.PROCESS_VERSION
