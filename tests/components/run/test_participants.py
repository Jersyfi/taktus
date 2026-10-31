"""An outside participant answers a step through their own channel (UC-1.12, ADR-0155).

A supplier is asked by mail when a delivery comes. The question is an ordinary connector step;
the answer is a `human` step addressed to the participant, waiting in the thread the question
opened. The supplier has no Taktus account. Their answer is matched by its channel and thread,
read by rule, said back, and recorded only once the same account confirms it (ADR-0008).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest
from fakes.maturity import VERIFIED

from components.run.test_engine import BUDGET, TENANT, Harness, rule
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.components.run.application.service import (
    AnswerParticipant,
    ConfirmSteps,
    RunEngine,
    StartRun,
)
from taktus.components.run.domain.model import (
    HumanWork,
    Run,
    RunError,
    RunState,
    StepState,
    UnsupportedWork,
    block,
    parse_work,
)
from taktus.components.run.domain.service import participants
from taktus.components.run.ports import MessageRules
from taktus.ports.connector import (
    CallContext,
    Capabilities,
    Consumption,
    Effect,
    EffectReport,
    Record,
    Result,
)
from taktus.shared.v1 import ExactnessClass, Method, Step

SEND = "channel.mail.send"
CHANNEL = "channel.mail"
QUESTION_ID = "<q-1@mail.example.org>"
SUPPLIER = "sha256:" + "a" * 64
STRANGER = "sha256:" + "b" * 64
LABEL = "Sent by Taktus for the purchasing team."


@dataclass
class Mailbox:
    """A mail channel: sending a message answers its Message-ID, the thread a reply names."""

    calls: list[tuple[str, CallContext, dict[str, Any]]] = field(default_factory=list)

    async def capabilities(self) -> Capabilities:
        return Capabilities.model_validate(
            {
                "contract": "connector/v1",
                "version": "1.0.0",
                "capabilities": [CHANNEL],
                "operations": [
                    {
                        "name": SEND,
                        "capability": CHANNEL,
                        "effect": "delivery",
                        "idempotency": "marked",
                        "demand": {"quota_units": 1},
                        "summary": "send a mail",
                    }
                ],
                "credentials": [{"name": "MAIL_TOKEN", "purpose": "actions"}],
                "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 60},
                "permissions": "passthrough",
            }
        )

    async def call(self, operation: str, context: CallContext, input: Mapping[str, Any]) -> Result:
        self.calls.append((operation, context, dict(input)))
        return Result(
            output={"message_id": QUESTION_ID, "to": input.get("to")},
            effect=EffectReport(
                kind=Effect.DELIVERY,
                replayed=False,
                records=(Record(kind="mail.message", id=QUESTION_ID),),
            ),
            consumption=Consumption(quota_units=1),
        )


@dataclass
class Rules:
    label: str | None = LABEL

    async def rules(self, tenant: str) -> MessageRules:
        return MessageRules(label=self.label, delay_seconds=0, quiet=None, recipient_limit=10)

    async def answered(self, tenant: str, process: str, case: str) -> bool:
        return False


def ask() -> tuple[Step, dict[str, Any]]:
    definition = Step(
        id="ask",
        method=Method.RULE,
        reason="the question is a mail to the supplier",
        rejected=(),
        exactness=ExactnessClass.SOURCED,
    )
    return definition, {
        "rule": "connector",
        "operation": SEND,
        "input": {
            "to": "orders@supplier.example.org",
            "subject": "Delivery date",
            "text": "When will order 4711 be delivered?",
        },
        "credentials": [{"name": "MAIL_TOKEN", "injected_as": "env"}],
    }


def answer(options: tuple[str, ...] = (), **more: Any) -> tuple[Step, dict[str, Any]]:
    definition = Step(
        id="answer",
        method=Method.HUMAN,
        reason="only the supplier knows the date",
        rejected=(),
        depends_on=("ask",),
    )
    work: dict[str, Any] = {
        "participant": "supplier",
        "channel": CHANNEL,
        "thread": {"$from": "ask", "$select": "output.message_id"},
        **more,
    }
    if options:
        work["options"] = list(options)
    return definition, work


def after() -> tuple[Step, dict[str, Any]]:
    return rule(
        "book",
        {"rule": "constant", "value": {"booked": True}},
        after=("answer",),
    )


class Asked(Harness):
    def __init__(
        self, *definitions: tuple[Step, dict[str, Any]], label: str | None = LABEL
    ) -> None:
        super().__init__(*definitions)
        self.mail = Mailbox()
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
            connectors=StaticConnectorPool([("connector.mail", self.mail)]),
            messages=Rules(label),
        )

    async def begin(self, *, rehearsal: bool = False) -> Run:
        return await self.engine.start(
            StartRun(
                plan=self.plan(),
                work=self.work,
                budget=BUDGET,
                process_version="purchasing@1",
                actor="idn_t",
                tenant=TENANT,
                rehearsal=rehearsal,
            )
        )

    async def write(self, run: Run, text: str, account: str = SUPPLIER) -> Any:
        return await self.engine.answer_participant(
            AnswerParticipant(
                run_id=run.id,
                step_id="answer",
                tenant=TENANT,
                channel=CHANNEL,
                account=account,
                text=text,
            )
        )

    async def result(self, run: Run, step_id: str) -> Any:
        step_run = run.step_run(step_id)
        assert step_run.checkpoint is not None and step_run.checkpoint.result_digest is not None
        content = await self.objects.get(step_run.checkpoint.result_digest)
        assert content is not None
        return json.loads(content)


async def test_a_step_addressed_to_a_participant_waits_in_the_thread_its_question_opened() -> None:
    h = Asked(ask(), answer(), after())
    run = await h.begin()
    assert run.state is RunState.WAITING_HUMAN, run.reason
    waiting = run.step_run("answer")
    assert waiting.state is StepState.WAITING_HUMAN
    assert waiting.block is not None and waiting.block.cause == block.AWAITING_PARTICIPANT
    assert waiting.block.account == "wait.external" and waiting.block.role == "supplier"
    assert waiting.block.awaited is not None
    assert (waiting.block.awaited.channel, waiting.block.awaited.thread) == (CHANNEL, QUESTION_ID)
    assert run.step_run("book").state is StepState.PLANNED
    assert "step.awaiting:answer:participant" in await h.kinds(run)


async def test_a_free_answer_is_reflected_and_recorded_only_once_the_participant_confirms() -> None:
    h = Asked(ask(), answer(), after())
    run = await h.begin()
    read = await h.write(run, "Re: Delivery date\n\nOn Friday, 14 November.\n\n> When will")
    assert read.taken and read.outcome == "read"
    assert read.say == (
        "I read your answer as “On Friday, 14 November.”. Reply yes to confirm, or answer "
        f"again.\n\n{LABEL}"
    )
    assert read.run.step_run("answer").state is StepState.WAITING_HUMAN, "nothing is acted on"
    done = await h.write(read.run, "Re: Delivery date\n\nYes")
    assert done.outcome == "recorded" and done.say is not None
    run = done.run
    assert run.state is RunState.FINISHED, run.reason
    answered = run.step_run("answer")
    assert answered.state is StepState.SUCCEEDED and answered.method is Method.HUMAN
    assert await h.result(run, "answer") == {
        "participant": "supplier",
        "answer": "On Friday, 14 November.",
        "option": None,
        "answered_by": {"channel": CHANNEL, "account": SUPPLIER},
    }
    kinds = await h.kinds(run)
    assert "step.answer_read:answer:read" in kinds
    assert "step.finished:answer:succeeded" in kinds
    finished = [e for e in await h.entries(run) if e.kind == "step.finished"]
    assert {e.refs.actor for e in finished if e.refs.step_id == "answer"} == {
        "participant:supplier"
    }
    assert not any(SUPPLIER in e.model_dump_json() for e in await h.entries(run)), (
        "the ledger never carries the channel's account"
    )


async def test_an_answer_that_names_no_option_is_asked_again_and_a_no_withdraws_a_reading() -> None:
    h = Asked(ask(), answer(("confirmed", "delayed")), after())
    run = await h.begin()
    unread = await h.write(run, "We will see.")
    assert unread.outcome == "unread" and "“confirmed”, “delayed”" in (unread.say or "")
    read = await h.write(unread.run, "Delivery is delayed by a week")
    assert read.outcome == "read" and "“delayed”" in (read.say or "")
    withdrawn = await h.write(read.run, "no")
    assert withdrawn.outcome == "withdrawn"
    again = await h.write(withdrawn.run, "yes")
    assert again.outcome == "unread", "a yes with no reading pending is read as an answer"
    read = await h.write(again.run, "confirmed for Friday")
    done = await h.write(read.run, "ja")
    assert done.run.state is RunState.FINISHED
    assert (await h.result(done.run, "answer"))["option"] == "confirmed"


async def test_another_account_in_the_thread_is_not_the_participant() -> None:
    h = Asked(ask(), answer(), after())
    run = await h.begin()
    read = await h.write(run, "Friday.")
    other = await h.write(read.run, "yes", account=STRANGER)
    assert not other.taken and other.say is None
    assert other.run.step_run("answer").state is StepState.WAITING_HUMAN


async def test_nobody_of_the_tenant_answers_for_the_participant() -> None:
    h = Asked(ask(), answer(), after())
    run = await h.begin()
    with pytest.raises(RunError, match="answer is theirs"):
        await h.engine.confirm(
            ConfirmSteps(run_id=run.id, steps=("answer",), actor="idn_t", tenant=TENANT)
        )


async def test_an_answer_in_another_channel_is_refused() -> None:
    h = Asked(ask(), answer(), after())
    run = await h.begin()
    with pytest.raises(RunError, match=r"does not wait for a participant in channel\.chat"):
        await h.engine.answer_participant(
            AnswerParticipant(
                run_id=run.id,
                step_id="answer",
                tenant=TENANT,
                channel="channel.chat",
                account=SUPPLIER,
                text="Friday",
            )
        )


async def test_a_reflection_carries_no_label_where_the_tenant_set_none() -> None:
    h = Asked(ask(), answer(), after(), label=None)
    run = await h.begin()
    read = await h.write(run, "Friday.")
    assert read.say == "I read your answer as “Friday.”. Reply yes to confirm, or answer again."


async def test_a_rehearsal_asks_no_participant() -> None:
    """A thread named outright, so that the rehearsal needs no recording of the question."""
    definition, work = answer()
    definition = definition.model_copy(update={"depends_on": None})
    work["thread"] = QUESTION_ID
    h = Asked((definition, work), after())
    run = await h.begin(rehearsal=True)
    assert run.state is RunState.FINISHED, run.reason
    assert await h.result(run, "answer") == {"participant": "supplier", "rehearsed": True}


async def test_a_thread_that_does_not_resolve_to_a_text_fails_the_step() -> None:
    definition, work = answer()
    work["thread"] = {"$from": "ask", "$select": "output.to"}
    first, question = ask()
    question["input"]["to"] = ["a@example.org", "b@example.org"]
    h = Asked((first, question), (definition, work))
    run = await h.begin()
    assert run.state is RunState.ESCALATED
    assert "not a text" in (run.step_run("answer").reason or "")


def test_a_human_step_without_a_participant_is_performed_inside_the_organisation() -> None:
    """ADR-0167 §1: a person of the step's role performs it; its work names the task at most."""
    definition, _ = answer()
    assert parse_work(definition, {"task": "a person does it"}) == HumanWork(
        task="a person does it"
    )
    with pytest.raises(UnsupportedWork, match=r"work\.note"):
        parse_work(definition, {"note": "a person does it"})


def test_options_are_distinct_words() -> None:
    definition, work = answer(("yes", "YES"))
    with pytest.raises(UnsupportedWork, match="differ"):
        parse_work(definition, work)


def test_the_reading_is_by_rule() -> None:
    assert participants.said("Re: Order\n\nYes!") == "yes"
    assert participants.said("Yes, but only half of it") == "answer"
    assert participants.read("delayed and confirmed", ("confirmed", "delayed")) is None
    reading = participants.read("CONFIRMED.", ("confirmed", "delayed"))
    assert reading is not None and reading.option == "confirmed"
