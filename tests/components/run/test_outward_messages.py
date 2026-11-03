"""An outward message is labelled, checked by a step of its own, and held by rule (UC-7.6,
ADR-0142).

A support reply as UC-03 B-3.02 drafts it: the customer's account read through a tool, a reply
drafted by a model, scored on named dimensions, checked by a step of its own against the raw
tool result, classified for promises, and sent through a mail channel. The run holds it to the
frame before the channel is called.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from typing import Any

import pytest
from fakes import FakeModel
from fakes.maturity import VERIFIED

from components.run.test_case_scope import ACCOUNT, MAIL, SCOPE, CustomerConnector, step
from components.run.test_engine import BUDGET, TENANT, Harness, rule
from components.run.test_llm_steps import llm
from components.run.test_replay import Requests
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.models import StaticModelPool
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Cause, RunState, StepState, UnsupportedWork
from taktus.components.run.domain.service import messages
from taktus.components.run.ports import MessageRules, QuietHours
from taktus.ports.model import Completion, Prompt
from taktus.shared.v1 import PriceKinds

LABEL = "This reply was written by an AI system."
RULES = MessageRules(label=LABEL, delay_seconds=600, quiet=None, recipient_limit=10)


@dataclass
class Scripted(FakeModel):
    """A model that answers by the step's system prompt: the draft, the check, the
    classification."""

    answers: dict[str, str] = field(default_factory=dict)

    async def complete(self, prompt: Prompt) -> Completion:
        self.prompts.append(prompt)
        text = self.answers.get(prompt.system or "", "")
        return Completion(
            text=text,
            model=self.name,
            tokens_in=10,
            tokens_out=10,
            by_kind=PriceKinds(input=10, output=10),
            finish="stop",
        )


@dataclass
class Told:
    """The tenant's message rules and the cases a person answered in, as the run's port reads
    them."""

    rules_: MessageRules = RULES
    cases: set[tuple[str, str]] = field(default_factory=set)

    async def rules(self, tenant: str) -> MessageRules:
        return self.rules_

    async def answered(self, tenant: str, process: str, case: str) -> bool:
        return (process, case) in self.cases


DRAFT, CHECK, CLASSIFY = "You draft a reply.", "You check a draft.", "You classify a draft."


def support(
    *,
    checks: dict[str, Any] | None = None,
    frame: dict[str, Any] | None = None,
    recipients: Any = None,
) -> list[tuple[Any, dict[str, Any]]]:
    """The support reply: read, draft, score, check, classify, send."""
    message: dict[str, Any] = {
        "text": "text",
        "checks": checks
        or {
            "facts": {"value": {"$from": "score", "$select": "facts"}, "equals": "yes"},
            "tone": {"value": {"$from": "score", "$select": "tone"}, "equals": "yes"},
        },
        "check": "verify",
        "classification": "promises",
        "case": {"$input": "ticket"},
    }
    if frame is not None:
        message = frame
    extra: dict[str, Any] = {"message": message}
    if recipients is not None:
        extra["recipients"] = recipients
    return [
        step("account", ACCOUNT, {"account": {"$input": "customer"}}, scope=SCOPE),
        llm(
            "draft",
            {
                "purpose": "reasoning",
                "system": DRAFT,
                "prompt": "${a}",
                "values": {"a": {"$from": "account"}},
            },
            after=("account",),
        ),
        rule(
            "score",
            {"rule": "constant", "value": {"facts": "yes", "tone": "yes"}},
            after=("draft",),
        ),
        llm(
            "verify",
            {
                "purpose": "reasoning",
                "system": CHECK,
                "prompt": "${d} against ${a}",
                "values": {
                    "d": {"$from": "draft", "$select": "text"},
                    "a": {"$from": "account", "$select": "output"},
                },
            },
            after=("draft",),
        ),
        llm(
            "promises",
            {
                "purpose": "reasoning",
                "system": CLASSIFY,
                "prompt": "${d}",
                "values": {"d": {"$from": "draft"}},
            },
            after=("draft",),
        ),
        step(
            "reply",
            MAIL,
            {"to": "customer@example.org", "text": {"$from": "draft", "$select": "text"}},
            after=("score", "verify", "promises"),
            **extra,
        ),
    ]


class Outward(Harness):
    def __init__(
        self,
        definitions: list[tuple[Any, dict[str, Any]]],
        *,
        check: str = "send",
        classified: str = "none",
        told: Told | None = None,
        level: int = 3,
        at: datetime | None = None,
    ) -> None:
        super().__init__(*definitions)
        if at is not None:
            self.clock.current = at
        self.customers = CustomerConnector()
        self.model = Scripted(
            answers={DRAFT: "Your plan is team. Best regards", CHECK: check, CLASSIFY: classified}
        )
        self.requests = Requests()
        self.told = told or Told()
        self.level = level
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.runs,
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=self.provenance,
            workers=self.engine._workers,
            clock=self.clock,
            ids=self.ids,
            telemetry=self.engine._telemetry,
            options=self.engine._options,
            connectors=StaticConnectorPool([("connector.customers", self.customers)]),
            models=StaticModelPool([("model.fake", ["reasoning"], self.model, "fake-model@1")]),
            decisions=self.requests,
            messages=self.told,
        )

    async def begin(self) -> Any:
        plan = self.plan().model_copy(update={"autonomy_level": self.level})
        return await self.engine.start(
            StartRun(
                plan=plan,
                work=self.work,
                budget=BUDGET,
                process_version="support@1",
                actor="idn_t",
                tenant=TENANT,
                inputs={"customer": "cust-1", "ticket": "T-17"},
            )
        )

    def sent(self) -> list[dict[str, Any]]:
        return [input for operation, _, input in self.customers.calls if operation == MAIL]

    async def until_sent(self, run: Any) -> Any:
        """The run resumed at the moment its held message is checked next, as its runner would."""
        held = run.step_run("reply").block
        assert run.cause is Cause.PARKED and held is not None and held.next_check_at is not None
        self.clock.current = held.next_check_at
        return await self.resume(run)


# --- the label --------------------------------------------------------------------------------


async def test_a_message_a_model_drafted_carries_the_tenant_s_label() -> None:
    h = Outward(support())
    run = await h.until_sent(await h.begin())
    assert run.state is RunState.FINISHED, run.reason
    (sent,) = h.sent()
    assert sent["text"] == f"Your plan is team. Best regards\n\n{LABEL}"


async def test_a_message_a_model_drafted_without_a_label_is_refused_before_the_port() -> None:
    h = Outward(support(), told=Told(rules_=MessageRules(None, 600, None, 10)))
    run = await h.begin()
    assert run.state is RunState.ESCALATED
    reply = run.step_run("reply")
    assert reply.state is StepState.FAILED and reply.retryable is False
    assert "no label" in (reply.reason or "")
    assert h.sent() == []
    assert "message.held:reply:unlabelled" in await h.kinds(run)


async def test_a_label_withdrawn_while_the_message_waited_refuses_it_at_the_call() -> None:
    told = Told()
    h = Outward(support(), told=told)
    run = await h.begin()
    told.rules_ = MessageRules(None, 600, None, 10)
    run = await h.until_sent(run)
    assert run.state is RunState.ESCALATED
    assert h.sent() == []
    assert "message.held:reply:unlabelled" in await h.kinds(run)


async def test_a_delivery_a_model_drafted_without_a_frame_is_refused() -> None:
    definitions = support()
    reply, work = definitions[-1]
    definitions[-1] = (reply, {k: v for k, v in work.items() if k != "message"})
    h = Outward(definitions)
    run = await h.begin()
    assert run.state is RunState.ESCALATED
    assert h.sent() == []
    assert "message.held:reply:undeclared" in await h.kinds(run)


# --- the send decision is a rule over named checks -----------------------------------------------


async def test_one_check_failing_sends_nothing() -> None:
    checks = {
        "facts": {"value": {"$from": "score", "$select": "facts"}, "equals": "yes"},
        "tone": {"value": {"$from": "score", "$select": "tone"}, "equals": "no"},
    }
    h = Outward(support(checks=checks))
    run = await h.begin()
    assert run.state is RunState.ESCALATED
    assert h.sent() == []
    reason = run.step_run("reply").reason or ""
    assert "tone:" in reason and "facts:" not in reason
    assert "message.held:reply:checks" in await h.kinds(run)


# --- the independent check -----------------------------------------------------------------------


@pytest.mark.parametrize("answer", ["reject", "send it, I think", ""])
async def test_a_check_that_does_not_answer_send_sends_nothing(answer: str) -> None:
    h = Outward(support(), check=answer)
    run = await h.begin()
    assert run.state is RunState.ESCALATED
    assert h.sent() == []
    assert "message.held:reply:rejected" in await h.kinds(run)


async def test_the_check_is_a_call_of_its_own_on_the_draft_and_the_raw_tool_result() -> None:
    h = Outward(support())
    await h.until_sent(await h.begin())
    checked = next(p for p in h.model.prompts if p.system == CHECK)
    assert checked.user.startswith("Your plan is team. Best regards against ")
    assert '"plan": "team"' in checked.user, "the raw result of the tool"
    assert len([p for p in h.model.prompts if p.system == DRAFT]) == 1


async def test_a_check_that_drafted_the_message_is_refused_before_the_run_starts() -> None:
    definitions = support()
    reply, work = definitions[-1]
    definitions[-1] = (reply, {**work, "message": {**work["message"], "check": "draft"}})
    h = Outward(definitions)
    with pytest.raises(UnsupportedWork, match="drafted the message"):
        await h.begin()


async def test_a_check_that_reads_anything_but_the_draft_and_the_tools_is_refused() -> None:
    definitions = support()
    verify, work = definitions[3]
    definitions[3] = (
        verify.model_copy(update={"depends_on": ("draft", "score")}),
        {**work, "values": {**work["values"], "s": {"$from": "score"}}},
    )
    h = Outward(definitions)
    with pytest.raises(UnsupportedWork, match="reads score"):
        await h.begin()


# --- the delay and the quiet hours ---------------------------------------------------------------


async def test_a_message_is_sent_no_earlier_than_its_delay_after_approval() -> None:
    h = Outward(support())
    run = await h.begin()
    assert run.state is RunState.HALTED and run.cause is Cause.PARKED
    held = run.step_run("reply").block
    assert held is not None and held.cause == "holding_message" and held.next_check_at is not None
    assert (held.next_check_at - held.since).total_seconds() >= 600
    assert h.sent() == []
    h.clock.current = held.next_check_at - timedelta(seconds=120)
    early = await h.resume(run)
    assert early.cause is Cause.PARKED and h.sent() == [], "woken early, it waits on"
    run = await h.until_sent(early)
    assert run.state is RunState.FINISHED and len(h.sent()) == 1
    assert "message.delayed:reply:delay" in await h.kinds(run)


async def test_a_message_approved_at_night_is_sent_in_the_morning() -> None:
    night = datetime(2026, 10, 23, 21, 30, tzinfo=UTC)  # 23:30 in Berlin
    quiet = QuietHours(begins=time(22, 0), ends=time(7, 0), zone="Europe/Berlin")
    h = Outward(support(), told=Told(rules_=MessageRules(LABEL, 600, quiet, 10)), at=night)
    run = await h.begin()
    held = run.step_run("reply").block
    assert held is not None and held.next_check_at == datetime(2026, 10, 24, 5, 0, tzinfo=UTC)
    run = await h.until_sent(run)
    assert run.state is RunState.FINISHED and len(h.sent()) == 1
    assert "message.delayed:reply:quiet_hours" in await h.kinds(run)


# --- a person's answer in the case ---------------------------------------------------------------


async def test_a_person_s_answer_during_the_delay_stops_the_message_and_every_later_one() -> None:
    told = Told()
    h = Outward(support(), told=told)
    run = await h.begin()
    told.cases.add(("support", "T-17"))
    run = await h.until_sent(run)
    assert run.state is RunState.FINISHED, run.reason
    reply = run.step_run("reply")
    assert reply.state is StepState.SUCCEEDED and "answered in the case" in (reply.reason or "")
    assert h.sent() == []
    assert "message.held:reply:answered" in await h.kinds(run)
    again = await h.begin()
    assert again.step_run("reply").state is StepState.SUCCEEDED
    assert h.sent() == [], "the process sends nothing more in that case"


# --- promises and mass sending -------------------------------------------------------------------


@pytest.mark.parametrize("classified", ["date", "feature, legal_advice", "maybe", ""])
async def test_a_promise_or_a_message_that_cannot_be_classified_waits_for_a_person(
    classified: str,
) -> None:
    h = Outward(support(), classified=classified, level=4)
    run = await h.begin()
    assert run.state is RunState.WAITING_HUMAN, run.reason
    assert run.step_run("reply").state is StepState.WAITING_HUMAN
    (draft,) = h.requests.raised
    assert draft.anchor == "anc-promise" and draft.class_ == "legal"
    assert h.sent() == []


async def test_a_message_without_a_classification_is_held_as_if_it_promised() -> None:
    definitions = support()
    reply, work = definitions[-1]
    message = {k: v for k, v in work["message"].items() if k != "classification"}
    definitions[-1] = (reply, {**work, "message": message})
    h = Outward(definitions, level=4)
    run = await h.begin()
    assert run.state is RunState.WAITING_HUMAN
    (draft,) = h.requests.raised
    assert draft.anchor == "anc-promise"
    assert h.sent() == []


@pytest.mark.parametrize(
    "recipients", [[f"r{n}@example.org" for n in range(11)], 11, {"list": "everyone"}]
)
async def test_more_recipients_than_the_limit_wait_for_a_person_at_every_level(
    recipients: Any,
) -> None:
    h = Outward(support(recipients=recipients), level=4)
    run = await h.begin()
    assert run.state is RunState.WAITING_HUMAN
    assert [d.anchor for d in h.requests.raised] == ["anc-mass-sending"]
    assert h.sent() == []


async def test_an_outward_step_no_model_wrote_is_held_by_the_recipient_limit_too() -> None:
    h = Outward(
        [step("notice", MAIL, {"to": "x", "text": "t"}, recipients=["a", "b", "c"])],
        told=Told(rules_=MessageRules(None, 600, None, 2)),
        level=4,
    )
    run = await h.begin()
    assert [d.anchor for d in h.requests.raised] == ["anc-mass-sending"]
    assert run.state is RunState.WAITING_HUMAN and h.sent() == []


async def test_a_delivery_no_model_wrote_is_sent_as_the_process_says() -> None:
    h = Outward([step("notice", MAIL, {"to": "x", "text": "t"})])
    run = await h.begin()
    assert run.state is RunState.FINISHED, run.reason
    assert h.sent() == [{"to": "x", "text": "t"}]


# --- the egress entry ----------------------------------------------------------------------------


async def test_every_message_sent_is_an_egress_entry_with_its_case_checks_and_label() -> None:
    h = Outward(support())
    run = await h.until_sent(await h.begin())
    entries = await h.entries(run)
    egress = [e for e in entries if e.kind == "egress.delivery"]
    sent = [e for e in entries if e.kind == messages.SENT]
    assert len(egress) == 1 and len(sent) == 1
    assert sent[0].refs.step_id == egress[0].refs.step_id == "reply"
    assert sent[0].content_digest is not None
    content = await h.objects.get(sent[0].content_digest)
    assert content is not None
    record = json.loads(content)
    assert record["case"] == "T-17"
    assert record["checks"] == {"facts": True, "tone": True}
    assert record["check"] == {"step": "verify", "verdict": "send"}
    assert record["classification"] == {"step": "promises", "promises": []}
    assert record["label"] == LABEL and record["drafted_by_model"] is True


# --- the case ------------------------------------------------------------------------------


async def test_a_case_taken_from_a_step_s_output_is_refused_before_the_run_starts() -> None:
    definitions = support()
    reply, work = definitions[-1]
    message = {**work["message"], "case": {"$from": "account"}}
    definitions[-1] = (reply, {**work, "message": message})
    h = Outward(definitions)
    with pytest.raises(UnsupportedWork, match="the case is one of the run's inputs"):
        await h.begin()
