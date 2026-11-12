"""The chat says *untried* where it shows a level (UC-6.3 §2, ADR-0180 §3, #627).

A channel that cannot draw receives a level's text equivalent, element by element, as the level
hands it to the web app (ADR-0069). A version at level 3 or 4 that no person has yet run by
hand from its takeover instructions says so in that text, on the process level and on the
overview, so the chat says it in the same words as the web app."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from taktus.components.reporting.domain.model import OwnerChannel, Phrasebook
from taktus.components.reporting.domain.model.levels import (
    OverviewFacts,
    ProcessFacts,
    ProcessStepFacts,
    ProcessSummary,
    VersionRef,
)
from taktus.components.reporting.domain.service.levels import (
    UNTRIED,
    overview_level,
    process_level,
)
from taktus.components.reporting.domain.service.rendering import shown
from taktus.shared.v1 import Autonomy, ExactnessClass, Method

AT = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[3]


def channel() -> OwnerChannel:
    book = Phrasebook.model_validate_json(
        (ROOT / "src/taktus/composition/phrasebooks/de.json").read_text("utf-8")
    )
    return OwnerChannel(
        id="default",
        tenant="default",
        owner="idn_owner",
        channel="channel.chat",
        address="D1",
        phrasebook=book,
        configured_at=AT,
        configured_by="operator",
    )


def facts(*, level: int, untried: bool) -> ProcessFacts:
    return ProcessFacts(
        id="billing",
        tenant="default",
        name="Billing",
        version="1",
        autonomy=Autonomy(level=level, reason="a rule decides", toward_next="none"),
        steps=(
            ProcessStepFacts(
                id="sum", method=Method.RULE, exactness=ExactnessClass.EXACT, reason="a sum"
            ),
        ),
        versions=(VersionRef(version="1", active=True),),
        untried=untried,
    )


def test_the_chat_says_a_process_is_untried_in_the_words_of_the_process_level() -> None:
    said = shown(process_level(facts(level=3, untried=True)), channel())
    assert UNTRIED.format(level=3) in said.splitlines()[0]
    tried = shown(process_level(facts(level=3, untried=False)), channel())
    assert "by hand" not in tried.splitlines()[0]


def test_the_chat_s_overview_says_which_process_is_untried() -> None:
    overview = overview_level(
        OverviewFacts(
            tenant="default",
            processes=(
                ProcessSummary(
                    id="billing", name="Billing", active_version="1", autonomy_level=3, untried=True
                ),
                ProcessSummary(
                    id="support",
                    name="Support",
                    active_version="1",
                    autonomy_level=3,
                    untried=False,
                ),
            ),
        )
    )
    lines = shown(overview, channel()).splitlines()
    billing = next(line for line in lines if "(billing@1)" in line)
    support = next(line for line in lines if "(support@1)" in line)
    assert "untried by hand" in billing
    assert "untried by hand" not in support
