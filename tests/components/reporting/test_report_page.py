"""Every link a channel carries opens a page of the web app, and the report is answered there as
in the channel (UC-6.11, DEC-0218, ADR-0120).

The link a message carries to its report is the report's page in the web app, under the
reader's sign-in, for every kind of report the channel sends; an alert is a report of kind
`failure` (ADR-0106). An answer given on the page is read by the same rules and said back in the
same sentence, nothing takes effect before the same person confirms it, and nothing is said in
the channel.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fakes.owner_channel import NAMED, OUTSIDER, OWNER, TENANT, OwnerChannel, owner_channel, people

from taktus.components.reporting.application.service import Answer, AnswerOnPage, RaiseReport
from taktus.components.reporting.domain.model import Report, ReportKind, ReportState
from taktus.shared.v1 import DecisionStatus

ROOT = Path(__file__).resolve().parents[3]
GERMAN = json.loads(
    (ROOT / "src/taktus/composition/phrasebooks/de.json").read_text(encoding="utf-8")
)
CONTROL_PLANE = "https://taktus.example/instance-a"


@pytest.fixture
async def given() -> OwnerChannel:
    channel = owner_channel()
    await people(channel)
    await channel.configure(view_base=f"{CONTROL_PLANE}/")
    return channel


async def signals(given: OwnerChannel) -> Report:
    return await given.owner.raising.execute(
        RaiseReport(
            tenant=TENANT,
            id="signals-2026-10-22",
            kind=ReportKind.SIGNALS,
            title="Two signals left their corridor",
            needed=["A look at the two signals."],
            steps=["Read each signal's corridor."],
            standing_still=["Nothing yet."],
            due=given.due(1),
        )
    )


async def every_kind(given: OwnerChannel) -> list[Report]:
    decision = await given.decision()
    assert decision is not None
    return [
        decision,
        await given.need(),
        await given.date(),
        await given.failure("backup-missing-2026-10-22"),
        await signals(given),
    ]


def said_for(given: OwnerChannel, report: Report) -> str:
    [said] = [s.text for s in given.deliveries.said if f"({report.id})" in s.text]
    return said


async def test_every_kind_of_report_links_its_page_in_the_web_app(given: OwnerChannel) -> None:
    reports = await every_kind(given)
    assert {r.kind for r in reports} == set(ReportKind), "every kind the channel sends"
    for report in reports:
        said = said_for(given, report)
        page = f"{CONTROL_PLANE}/app/#/reports/{report.id}"
        assert f"{GERMAN['view']}: {page}" in said, report.kind
        assert "/owner/reports" not in said, "never a route of the HTTP surface"


async def test_an_identifier_is_written_into_the_page_s_address_escaped(
    given: OwnerChannel,
) -> None:
    report = await given.need("need 0002/a")
    assert f"{CONTROL_PLANE}/app/#/reports/need%200002%2Fa" in said_for(given, report)


async def test_without_the_control_plane_s_address_the_message_links_no_page() -> None:
    bare = owner_channel()
    await people(bare)
    await bare.configure()
    report = await bare.need()
    assert "/app/#/reports/" not in said_for(bare, report)


# --- answered on the page ------------------------------------------------------------------------


async def on_page(
    given: OwnerChannel,
    report: Report,
    who: str = OWNER,
    *,
    option: str | None = None,
    text: str | None = None,
    confirmed: bool | None = None,
) -> Answer:
    answered = await given.owner.answering.on_page(
        AnswerOnPage(
            tenant=TENANT,
            report_id=report.id,
            identity=who,
            option=option,
            text=text,
            confirmed=confirmed,
        )
    )
    assert answered is not None
    return answered


async def test_an_answer_on_the_page_is_read_back_and_filed_only_once_confirmed(
    given: OwnerChannel,
) -> None:
    report = await given.need()
    before = len(given.deliveries.said)
    read = await on_page(given, report, option="done")
    assert read.outcome == "reflected"
    assert read.said.startswith(GERMAN["reflect"].format(answer="done", label=GERMAN["done"]))
    waiting = await given.owner.queries.one(TENANT, report.id)
    assert waiting is not None and waiting.state is ReportState.REFLECTED
    filed = await on_page(given, report, confirmed=True)
    assert filed.outcome == "filed"
    after = await given.owner.queries.one(TENANT, report.id)
    assert after is not None and after.state is ReportState.FILED
    assert after.filed is not None and after.filed.where == "web" and after.filed.by == OWNER
    assert len(given.deliveries.said) == before, "nothing is said in the channel"


async def test_the_reader_s_own_words_are_read_by_the_channel_s_rule(given: OwnerChannel) -> None:
    report = await given.need()
    asked = await on_page(given, report, text="vielleicht")
    assert asked.outcome == "asked_back"
    read = await on_page(given, report, text="Erledigt.")
    assert read.outcome == "reflected"


async def test_a_decision_on_the_page_is_filed_in_the_register_only_once_confirmed(
    given: OwnerChannel,
) -> None:
    report = await given.decision()
    assert report is not None
    read = await on_page(given, report, option="B")
    assert read.outcome == "reflected"
    request = await given.decisions.queries.one(TENANT, report.id)
    assert request is not None and request.request.status is DecisionStatus.INTERPRETED
    assert await given.decisions.queries.entries(TENANT) == []
    await on_page(given, report, confirmed=True)
    [entry] = await given.decisions.queries.entries(TENANT)
    assert entry.option == "B" and entry.decided_by == OWNER
    filed = await given.owner.queries.one(TENANT, report.id)
    assert filed is not None and filed.filed is not None and filed.filed.record == entry.id


async def test_a_rejected_reading_opens_the_report_again(given: OwnerChannel) -> None:
    report = await given.need()
    await on_page(given, report, option="done")
    rejected = await on_page(given, report, confirmed=False)
    assert rejected.outcome == "reread"
    after = await given.owner.queries.one(TENANT, report.id)
    assert after is not None and after.state is ReportState.OPEN and after.filed is None


async def test_only_the_person_whose_answer_was_read_confirms_it(given: OwnerChannel) -> None:
    report = await given.need()
    await on_page(given, report, NAMED, option="done")
    other = await on_page(given, report, OWNER, confirmed=True)
    assert other.outcome == "nothing_to_confirm"
    nothing = await on_page(given, await given.date(), confirmed=True)
    assert nothing.outcome == "nothing_to_confirm"
    after = await given.owner.queries.one(TENANT, report.id)
    assert after is not None and after.state is ReportState.REFLECTED


async def test_an_answer_from_anyone_else_is_not_filed(given: OwnerChannel) -> None:
    report = await given.need()
    answered = await on_page(given, report, OUTSIDER, option="done")
    assert answered.outcome == "not_filed"
    after = await given.owner.queries.one(TENANT, report.id)
    assert after is not None and after.state is ReportState.OPEN


async def test_an_answer_to_no_report_is_none(given: OwnerChannel) -> None:
    assert (
        await given.owner.answering.on_page(
            AnswerOnPage(tenant=TENANT, report_id="nothing", identity=OWNER, option="done")
        )
        is None
    )
