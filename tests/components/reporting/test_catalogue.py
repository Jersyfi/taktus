"""The catalogue of what a person may ask Taktus for (UC-1.13, ADR-0159 §1): a projection of
the active versions, in plain words, with the one start command and how to start each entry on
each channel. Nothing is stored, and nothing in it is a ticket."""

from __future__ import annotations

from taktus.components.reporting.domain.service.catalogue import (
    CatalogueFacts,
    CatalogueInput,
    catalogue,
)

DAILY = CatalogueFacts(
    process="daily",
    name="Daily report",
    description="The figures of yesterday.",
    version="daily@3",
    level=3,
    roles=("clerk", "clerk", "lead"),
)
OFFER = CatalogueFacts(
    process="offer",
    name="An offer",
    version="offer@1",
    level=2,
    inputs=(
        CatalogueInput(name="client", description="who asks", required=True),
        CatalogueInput(name="note", description="anything else", required=False),
    ),
)


def test_each_entry_carries_the_one_command_and_how_to_start_it_on_each_channel() -> None:
    listed = catalogue([DAILY, OFFER], agent_may_start=True, chat_word="start")
    assert [e.process for e in listed.entries] == ["offer", "daily"], "by name"
    offer, daily = listed.entries
    assert daily.command.intent == "run daily@3" and daily.command.recognised == "process.run"
    assert daily.start.web == "/catalogue/daily/start"
    assert daily.start.agent == {
        "tool": "start_process",
        "arguments": {"process": "daily"},
        "right": "agent.start",
        "held": True,
    }
    assert daily.start.chat == "start daily"
    assert offer.start.chat is None, "a reply cannot give the input it needs"
    assert daily.roles == ("clerk", "lead")
    assert daily.text == (
        "Daily report (daily): The figures of yesterday. Runs at level 3. Needs nothing from "
        "you to start. A person acts in the role clerk, lead."
    )
    assert "Needs client." in offer.text


def test_without_a_chat_that_reads_a_start_and_without_any_process() -> None:
    listed = catalogue([DAILY], agent_may_start=False, chat_word=None)
    (daily,) = listed.entries
    assert daily.start.chat is None and daily.start.agent["held"] is False
    empty = catalogue([], agent_may_start=False, chat_word=None)
    assert empty.entries == () and empty.summary == "There is no process you may start yet."
    assert "gallery" in empty.nothing_fits


def test_no_entry_holds_a_queue_a_ticket_or_a_promised_time() -> None:
    fields = set(
        catalogue([DAILY], agent_may_start=True, chat_word="start").document()["entries"][0]
    )
    assert not fields & {"ticket", "queue", "sla", "due", "priority", "assignee", "request"}
