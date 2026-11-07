"""Who sees which figure, what a report carries, and an explanation held to its records (UC-6.4,
UC-6.2, UC-6.5; ADR-0241 to ADR-0243). The rules are pure; the figures are handed in."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from taktus.components.reporting.domain.model.views import (
    ReportDefinition,
    Shown,
    ViewConfiguration,
)
from taktus.components.reporting.domain.service import explaining, reports
from taktus.components.reporting.domain.service import views as selection

AT = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[3]


def figure(id: str, subject: str = "invoice", **more: object) -> Shown:
    return Shown.model_validate(
        {
            "id": id,
            "component": "value",
            "definition": "d",
            "unit": "u",
            "scope": "process",
            "subject": subject,
            "value": 1.0,
            "method": "m",
            **more,
        }
    )


def test_the_default_gives_the_owner_every_figure_and_nobody_else_any() -> None:
    known = ["value.quality", "value.runs_ended"]
    c = selection.default("t", known, AT)
    figures = [figure(k) for k in known]
    assert selection.exported(("owner",), c, figures, {}) == figures
    assert selection.exported(("accounting",), c, figures, {}) == []
    assert [v["id"] for v in selection.shown("idn_x", ("owner",), c, figures, {})] == [
        "day",
        "team",
        "management",
        "executive",
        "investor",
    ]


def test_a_figure_of_relief_is_withheld_where_one_identity_would_be_its_subject() -> None:
    c = selection.default("t", ["value.time_saved_hours"], AT)
    relief = figure("value.time_saved_hours", basis={"roles_by_hand": ["lead"]})
    (alone,) = selection.exported(("owner",), c, [relief], {"lead": 1})
    (two,) = selection.exported(("owner",), c, [relief], {"lead": 2})
    assert alone.value is None and alone.withheld is not None and two.value == 1.0


@pytest.mark.parametrize("group", ["person", "identity", "employee"])
def test_a_view_grouped_by_person_is_refused(group: str) -> None:
    with pytest.raises(ValueError, match="never by person"):
        ViewConfiguration.model_validate(
            {
                "id": "t",
                "tenant": "t",
                "configured_at": AT,
                "entitlements": {},
                "views": [
                    {"id": "v", "title": "V", "figures": ["value.quality"], "group_by": group}
                ],
            }
        )


def test_a_report_needs_a_reader_and_a_schedule_needs_its_hour() -> None:
    base = {
        "id": "r",
        "tenant": "t",
        "trigger": "schedule",
        "every": "day",
        "channel": "channel.chat",
        "address": "C",
        "set_at": AT,
    }
    with pytest.raises(ValueError):
        ReportDefinition.model_validate({**base, "hour": 7})
    with pytest.raises(ValueError):
        ReportDefinition.model_validate({**base, "reader_role": "lead"})
    weekly = ReportDefinition.model_validate(
        {**base, "reader_role": "lead", "hour": 7, "every": "week", "weekday": AT.weekday()}
    )
    slot = reports.due(weekly, AT)
    assert slot == "2026-W45"
    assert reports.due(weekly.model_copy(update={"last_slot": slot}), AT) is None


def test_the_first_level_carries_only_what_bears_on_the_reader() -> None:
    d = ReportDefinition(
        id="r",
        tenant="t",
        reader_role="lead",
        trigger="request",
        channel="channel.chat",
        address="C",
        set_at=AT,
    )
    quiet = reports.compose(d, reports.ReportFacts(reader="lead", since=AT, until=AT))
    assert quiet.quiet and len(quiet.lines) == 1
    off = reports.Item(kind="switch_off", ref="p", text="p is a candidate to switch off.")
    busy = reports.compose(
        d,
        reports.ReportFacts(
            reader="lead",
            since=AT,
            until=AT,
            decisions=("dr_1",),
            blocked=(("run_1", "p", "s"),),
            switch_off=(off,),
        ),
    )
    assert [i.kind for i in busy.items] == ["decision", "blocked"], "switch-off is the owner's"
    owner = reports.compose(
        d.model_copy(update={"reader_role": "owner"}),
        reports.ReportFacts(reader="owner", since=AT, until=AT, switch_off=(off,)),
    )
    assert [i.kind for i in owner.items] == ["switch_off"], "unasked, to the owner"


FACTS = explaining.StepFacts(
    run_id="run_1",
    process_version="invoice@2",
    step_id="total",
    method="rule",
    reason="a fixed sum",
    rejected=(explaining.Alternative(method="llm", why="not exact"),),
    exactness="exact",
    state="succeeded",
    money=0.25,
    currency="EUR",
    takte=3.0,
)


def template(language: str) -> dict[str, str]:
    path = ROOT / "src" / "taktus" / "composition" / "explanations" / f"{language}.json"
    loaded: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def test_a_short_explanation_is_a_part_of_the_full_one_and_both_are_grounded() -> None:
    short = explaining.explain(FACTS, "short", template("en"))
    full = explaining.explain(FACTS, "full", template("en"))
    assert set(short.lines) <= set(full.lines)
    assert "It cost 0.25 EUR, 3 Takt." in short.lines
    assert "Not chosen: llm, because not exact" in full.lines
    assert short.grounded and full.grounded
    german = explaining.explain(FACTS, "short", template("de"))
    assert german.language == "de" and german.lines[0].startswith("Schritt total")


def test_an_explanation_with_a_figure_the_records_do_not_hold_fails() -> None:
    assert explaining.ungrounded(["It cost 0.25 EUR."], FACTS) == []
    assert explaining.ungrounded(["It cost 9.99 EUR, 47 times."], FACTS) == ["9.99", "47"]


def test_both_languages_give_every_sentence() -> None:
    for language in ("en", "de"):
        assert set(explaining.KEYS) <= set(template(language))
