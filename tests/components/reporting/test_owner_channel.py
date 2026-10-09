"""The owner-facing channel (UC-6.11 §2, ADR-0045): one event, three renderings that agree, and
the owner's answer filed only once its reading is confirmed, and only from the owner or someone
the owner named.

Each case runs the identity, decision and reporting components over memory, wired as the
composition root wires them, with a carrier that records what it was told to deliver. The same
path against the chat connector and the fake of its service is
`tests/adapters/connectors/test_owner_channel_chat.py`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from fakes.owner_channel import (
    ADDRESS,
    CHANNEL,
    NAMED,
    OUTSIDER,
    OWNER,
    SECRET,
    TENANT,
    OwnerChannel,
    owner_channel,
    people,
)

from taktus.components.decision.domain.model import RegisterEntry
from taktus.components.reporting.application.query import view
from taktus.components.reporting.application.service import (
    ChannelRefused,
    CloseTask,
    ConfigureChannel,
    DeliverReport,
    NoChannel,
    NotSent,
    RaiseReport,
)
from taktus.components.reporting.domain.model import (
    DeliveryChannel,
    DeliveryState,
    Report,
    ReportKind,
    ReportState,
)
from taktus.components.reporting.domain.service.rendering import repository_text
from taktus.shared.v1 import DecisionStatus

ROOT = Path(__file__).resolve().parents[3]
GERMAN = json.loads(
    (ROOT / "src/taktus/composition/phrasebooks/de.json").read_text(encoding="utf-8")
)
ENGLISH = json.loads(
    (ROOT / "src/taktus/composition/phrasebooks/en.json").read_text(encoding="utf-8")
)


@pytest.fixture
async def given() -> OwnerChannel:
    channel = owner_channel()
    await people(channel)
    await channel.configure()
    return channel


async def every_kind(given: OwnerChannel) -> list[Report]:
    decision = await given.decision()
    assert decision is not None
    return [decision, await given.need(), await given.date(), await given.failure()]


def the_message(given: OwnerChannel, report: Report) -> str:
    sent = [
        s.text for s in given.deliveries.said if s.thread is None and f"({report.id})" in s.text
    ]
    assert len(sent) == 1, "one message per report, said once"
    return sent[0]


# --- three renderings ----------------------------------------------------------------------------


async def test_every_kind_produces_three_renderings_that_agree(given: OwnerChannel) -> None:
    """A decision request, a need, a date and a failure: each repository text, message and
    view carries the same identifier, the same needed items and the same date."""
    reports = await every_kind(given)
    assert [r.kind for r in reports] == [
        ReportKind.DECISION,
        ReportKind.NEED,
        ReportKind.DATE,
        ReportKind.FAILURE,
    ]
    for report in reports:
        stored = await given.owner.queries.one(TENANT, report.id)
        assert stored is not None
        text = repository_text(stored)
        said = the_message(given, stored)
        seen = view(stored, OWNER)
        due = stored.due.isoformat()
        assert stored.id in text and stored.id in said and seen["id"] == stored.id
        assert due in text and due in said and seen["due"] == due
        assert tuple(seen["needed"]) == stored.needed
        for item in (*stored.needed, *stored.steps, *stored.standing_still):
            assert item in text, item
            assert item in said, item
        assert tuple(seen["steps"]) == stored.steps
        assert tuple(seen["standing_still"]) == stored.standing_still


async def test_a_decision_request_reaches_the_owner_through_the_run_s_decision_port(
    given: OwnerChannel,
) -> None:
    """Raised as the run raises it, the request becomes a report under its own identifier:
    the question is what is needed, the options the steps, what it blocks what stands still."""
    report = await given.decision()
    assert report is not None and report.kind is ReportKind.DECISION
    request = await given.decisions.queries.one(TENANT, report.id)
    assert request is not None
    shaped = request.request.request
    assert report.needed == (shaped.question,)
    assert report.standing_still == shaped.blocking
    assert report.due == shaped.due
    assert [o.id for o in report.offered] == ["A", "B"]
    assert report.offered[0].recommended


async def test_a_decision_for_a_role_the_channel_does_not_carry_stays_on_the_surface(
    given: OwnerChannel,
) -> None:
    assert await given.decision("dr_finance", decider="finance.lead") is None
    assert given.deliveries.said == []


async def test_the_repository_text_holds_what_future_work_needs_and_no_conversation(
    given: OwnerChannel,
) -> None:
    """English, minimal; after an answer it names where the answer was given — the channel,
    the address, the thread — and never what anyone wrote there."""
    report = await given.need()
    written = "Erledigt! Und hier noch Kontext, der nur in den Chat gehört."
    await given.answer(report, written, event="Ev1")
    await given.answer(report, "erledigt", event="Ev2")
    await given.answer(report, "ja", event="Ev3")
    filed = await given.owner.queries.one(TENANT, report.id)
    assert filed is not None
    text = repository_text(filed)
    assert "Kontext" not in text and written not in text and "ja" not in text.split()
    assert f"given at {CHANNEL} {ADDRESS} {given.thread_of(filed)}" in text
    for word in (GERMAN["needed"], GERMAN["steps"], GERMAN["due"]):
        assert word not in text, "the repository text is English"
    assert "## What is needed" in text and "**Needed by:**" in text
    assert "## Answer" in text


async def test_the_message_is_in_the_configured_language_and_links_everything(
    given: OwnerChannel,
) -> None:
    report = await given.need()
    said = the_message(given, report)
    for label in ("needed", "steps", "standing_still", "due", "links"):
        assert GERMAN[label] in said, label
        assert ENGLISH[label] not in said, label
    for link in report.links:
        assert link.url in said
    assert GERMAN["answer_with"].format(answers=GERMAN["done"]) in said


async def test_the_language_is_configuration_and_the_core_names_none(
    given: OwnerChannel,
) -> None:
    """The same report in a tenant that configured English is in English. No sentence of a
    phrasebook appears in any component: the core names no language."""
    english = owner_channel()
    await people(english)
    await english.configure(language="en")
    report = await english.need()
    said = the_message(english, report)
    assert ENGLISH["needed"] in said and GERMAN["needed"] not in said
    sentences = [
        v for k, v in GERMAN.items() if isinstance(v, str) and len(v) > 6 and k != "language"
    ]
    components = ROOT / "src" / "taktus" / "components"
    for path in components.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for sentence in sentences:
            assert sentence not in source, f"{path} names a sentence of the phrasebook"
    assert not re.search(
        r"\b(German|Deutsch)\b",
        "\n".join(p.read_text(encoding="utf-8") for p in components.rglob("*.py")),
    )


async def test_a_channel_with_no_phrasebook_for_its_language_is_refused(
    given: OwnerChannel,
) -> None:
    with pytest.raises(ChannelRefused, match="ships none"):
        await given.configure(language="xx")
    with pytest.raises(ChannelRefused, match="reflect"):
        await given.owner.configure.execute(
            ConfigureChannel(
                tenant=TENANT,
                document={
                    "owner": OWNER,
                    "channel": CHANNEL,
                    "address": ADDRESS,
                    "phrasebook": {**GERMAN, "reflect": "Ich verstehe {nothing}."},
                },
                actor="operator",
            )
        )


# --- a report without one of the four is not sent ------------------------------------------------


@pytest.mark.parametrize(
    "missing",
    [
        {"needed": []},
        {"steps": ["  "]},
        {"standing_still": []},
        {"due": None},
    ],
    ids=["needed", "steps", "standing_still", "due"],
)
async def test_a_report_without_one_of_the_four_is_not_sent(
    given: OwnerChannel, missing: dict[str, Any]
) -> None:
    with pytest.raises(NotSent):
        await given.need(**missing)
    assert given.deliveries.said == [] and given.deliveries.tasks == []
    assert await given.owner.queries.one(TENANT, "need_0001") is None
    assert "report.raised" not in await given.kinds()


# --- the answer: read, reflected, confirmed, filed -----------------------------------------------


async def test_an_answer_is_filed_only_after_its_reading_is_confirmed(given: OwnerChannel) -> None:
    report = await given.need()
    thread = given.thread_of(report)
    reflected = await given.answer(report, "Erledigt.", event="Ev1")
    assert reflected.outcome == "reflected" and reflected.replied
    after = await given.owner.queries.one(TENANT, report.id)
    assert after is not None and after.state is ReportState.REFLECTED and after.filed is None
    reply = given.deliveries.in_thread(thread)[-1]
    assert reply.startswith(GERMAN["reflect"].format(answer="done", label=GERMAN["done"]))
    assert "„ja“" in reply
    assert "report.filed" not in await given.kinds()

    filed = await given.answer(report, "Ja", event="Ev2")
    assert filed.outcome == "filed"
    after = await given.owner.queries.one(TENANT, report.id)
    assert after is not None and after.state is ReportState.FILED
    assert after.filed is not None and after.filed.answer == "done" and after.filed.by == OWNER
    assert given.deliveries.in_thread(thread)[-1] == GERMAN["filed"].format(answer="done")
    assert "report.filed" in await given.kinds()


async def test_a_decision_answer_is_filed_in_the_register_only_once_confirmed(
    given: OwnerChannel,
) -> None:
    report = await given.decision()
    assert report is not None
    reflected = await given.answer(report, "B, aber erst nächste Woche", event="Ev1")
    assert reflected.outcome == "reflected"
    request = await given.decisions.queries.one(TENANT, report.id)
    assert request is not None and request.request.status is DecisionStatus.INTERPRETED
    assert await given.decisions.queries.entries(TENANT) == []
    reply = given.deliveries.in_thread(given.thread_of(report))[-1]
    assert GERMAN["kept"] in reply, "the rest of the answer is kept and not acted on"
    assert "nächste Woche" not in reply, "the answer is never quoted back"

    await given.answer(report, "ja", event="Ev2")
    entries: list[RegisterEntry] = await given.decisions.queries.entries(TENANT)
    assert [e.option for e in entries] == ["B"] and entries[0].decided_by == OWNER
    filed = await given.owner.queries.one(TENANT, report.id)
    assert filed is not None and filed.filed is not None
    assert filed.filed.record == entries[0].id, "filed where it belongs: the register"
    applied = await given.decisions.queries.one(TENANT, report.id)
    assert applied is not None and applied.request.status is DecisionStatus.APPLIED


async def test_a_rejected_reading_files_nothing_and_opens_the_report_again(
    given: OwnerChannel,
) -> None:
    report = await given.decision()
    assert report is not None
    await given.answer(report, "A", event="Ev1")
    rejected = await given.answer(report, "nein", event="Ev2")
    assert rejected.outcome == "reread"
    after = await given.owner.queries.one(TENANT, report.id)
    assert after is not None and after.state is ReportState.OPEN and after.filed is None
    request = await given.decisions.queries.one(TENANT, report.id)
    assert request is not None and request.request.status is DecisionStatus.OPEN
    assert await given.decisions.queries.entries(TENANT) == []


@pytest.mark.parametrize("text", ["vielleicht", "A oder B", "nicht erledigt"])
async def test_an_answer_no_offered_answer_can_be_read_from_is_asked_back(
    given: OwnerChannel, text: str
) -> None:
    decision = await given.decision()
    need = await given.need()
    assert decision is not None
    for report in (decision, need):
        asked = await given.answer(report, text, event=f"Ev-{report.id}")
        assert asked.outcome == "asked_back"
        after = await given.owner.queries.one(TENANT, report.id)
        assert after is not None and after.state is ReportState.OPEN and after.filed is None
        reply = given.deliveries.in_thread(given.thread_of(report))[-1]
        assert reply.startswith(GERMAN["asked_back"].split("{")[0])
    assert await given.decisions.queries.entries(TENANT) == []


# --- who may answer ------------------------------------------------------------------------------


@pytest.mark.parametrize("who", [OUTSIDER, None], ids=["another identity", "nobody placed"])
async def test_an_answer_from_anyone_else_is_acknowledged_as_not_filed(
    given: OwnerChannel, who: str | None
) -> None:
    decision = await given.decision()
    need = await given.need()
    assert decision is not None
    for report in (decision, need):
        answered = await given.answer(report, "A" if report is decision else "erledigt", who)
        assert answered.outcome == "not_filed" and answered.replied
        assert given.deliveries.in_thread(given.thread_of(report))[-1] == GERMAN["not_filed"]
        after = await given.owner.queries.one(TENANT, report.id)
        assert after is not None and after.state is ReportState.OPEN and after.reading is None
    request = await given.decisions.queries.one(TENANT, decision.id)
    assert request is not None and request.request.status is DecisionStatus.OPEN


async def test_someone_the_owner_named_answers_and_confirms_in_their_place(
    given: OwnerChannel,
) -> None:
    report = await given.need()
    assert (await given.answer(report, "bereitgestellt", NAMED, event="Ev1")).outcome == (
        "reflected"
    )
    # Only the person whose answer was read confirms it: the owner's "ja" is not a
    # confirmation of someone else's reading, and reads as no answer at all.
    owner_says = await given.answer(report, "ja", OWNER, event="Ev2")
    assert owner_says.outcome == "asked_back"
    assert "report.filed" not in await given.kinds()
    await given.answer(report, "bereitgestellt", NAMED, event="Ev3")
    filed = await given.answer(report, "ja", NAMED, event="Ev4")
    assert filed.outcome == "filed"


# --- the ticket system ---------------------------------------------------------------------------


async def test_the_report_also_goes_to_a_configured_ticket_system_as_a_task(
    given: OwnerChannel,
) -> None:
    await given.configure(
        task={"capability": "repository.issues", "operation": "repository.issues.create"}
    )
    report = await given.need()
    [task] = given.deliveries.tasks
    assert task.operation == "repository.issues.create"
    assert task.title.startswith(report.id) and task.body == repository_text(
        report.model_copy(update={"deliveries": (), "history": report.history[:1]})
    )
    said = the_message(given, report)
    assert "https://tickets.example/issues/1" in said, "the message links the task"


async def test_closing_the_task_without_an_answer_files_nothing(given: OwnerChannel) -> None:
    await given.configure(
        task={"capability": "repository.issues", "operation": "repository.issues.create"}
    )
    report = await given.need()
    closed = await given.owner.close_task.execute(CloseTask(tenant=TENANT, task="issue:1"))
    assert closed is not None and closed.state is ReportState.OPEN and closed.filed is None
    assert closed.history[-1].event == "task_closed"
    assert "report.filed" not in await given.kinds()
    assert "report.task_closed" in await given.kinds()
    still = await given.answer(report, "erledigt", event="Ev1")
    assert still.outcome == "reflected", "the report still takes its answer in the channel"


# --- delivery that fails -------------------------------------------------------------------------


async def test_a_message_that_cannot_be_delivered_leaves_the_event_and_shows_the_failure(
    given: OwnerChannel,
) -> None:
    given.deliveries.fails = "unreachable"
    report = await given.need()
    stored = await given.owner.queries.one(TENANT, report.id)
    assert stored is not None, "the event stays"
    [delivery] = stored.deliveries
    assert delivery.channel is DeliveryChannel.MESSAGE
    assert delivery.state is DeliveryState.FAILED and delivery.reason == "unreachable"
    assert "- message failed" in repository_text(stored) and "unreachable" in repository_text(
        stored
    )
    seen = view(stored, OWNER)
    assert seen["deliveries"][0]["state"] == "failed"
    assert [h["event"] for h in seen["history"]] == ["raised", "message_failed"]

    given.deliveries.fails = None
    again = await given.owner.raising.deliver(DeliverReport(tenant=TENANT, id=report.id))
    assert again.message() is not None
    assert [d.state for d in again.deliveries] == [DeliveryState.FAILED, DeliveryState.DELIVERED]


# --- a failure Taktus noticed about itself -------------------------------------------------------


async def test_a_failure_taktus_noticed_about_itself_reaches_the_owner_the_same_way(
    given: OwnerChannel,
) -> None:
    report = await given.failure()
    assert report.kind is ReportKind.FAILURE
    said = the_message(given, report)
    assert said.startswith(f"*{GERMAN['failure']}: ")
    assert given.deliveries.said[0].channel == CHANNEL
    assert given.deliveries.said[0].address == ADDRESS
    assert (await given.answer(report, "erledigt")).outcome == "reflected"


# --- no secret -----------------------------------------------------------------------------------


async def test_no_message_carries_a_secret_value(given: OwnerChannel) -> None:
    with pytest.raises(NotSent, match="secret"):
        await given.need(steps=[f"Paste {SECRET} into the file."])
    assert given.deliveries.said == []
    assert await given.owner.queries.one(TENANT, "need_0001") is None

    report = await given.need()
    await given.answer(report, f"erledigt, der Wert ist {SECRET}", event="Ev1")
    await given.answer(report, SECRET, event="Ev2")
    for said in given.deliveries.said:
        assert SECRET not in said.text
    assert all(SECRET not in t.body for t in given.deliveries.tasks)


async def test_the_view_names_nobody(given: OwnerChannel) -> None:
    """Whether the reader acted, never who did (ADR-0015)."""
    report = await given.need()
    await given.answer(report, "erledigt", NAMED, event="Ev1")
    await given.answer(report, "ja", NAMED, event="Ev2")
    stored = await given.owner.queries.one(TENANT, report.id)
    assert stored is not None
    as_owner = json.dumps(view(stored, OWNER))
    assert NAMED not in as_owner and OWNER not in as_owner
    assert view(stored, NAMED)["filed"]["by_you"] is True
    assert view(stored, OWNER)["filed"]["by_you"] is False


async def test_raising_the_same_event_twice_is_one_report_said_once(given: OwnerChannel) -> None:
    first = await given.need()
    second = await given.need()
    assert first == second
    assert len(given.deliveries.said) == 1


async def test_a_report_in_a_tenant_without_a_channel_is_not_raised() -> None:
    bare = owner_channel()
    with pytest.raises(NoChannel):
        await bare.owner.raising.execute(
            RaiseReport(
                tenant=TENANT,
                id="need_x",
                kind=ReportKind.NEED,
                title="t",
                needed=["n"],
                steps=["s"],
                standing_still=["w"],
                due=bare.due(),
            )
        )
