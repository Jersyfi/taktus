"""A live representation asked for in the owner's conversation, a chat that cannot draw it
(UC-6.10 *beyond the web app*, ADR-0069, issue #193).

The answer is the level's text equivalent, element by element as the level hands it to the web
app, and the link to the level live in the web app. It carries nothing its readers may not see:
a run or a process the asker may not see, anyone but the owner or someone the owner named, and an
answer that would carry a secret are all told the same sentence, and a message at another
address of the channel is not this use case's.
"""

from __future__ import annotations

from datetime import UTC, datetime
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
)

from taktus.components.reporting.domain.model import (
    Phrasebook,
    ProcessFacts,
    ProcessStepFacts,
    RunAtVersion,
    RunFacts,
    StepFacts,
    VersionRef,
)
from taktus.components.reporting.domain.service.levels import process_level, run_level
from taktus.components.reporting.domain.service.reading import Asked, representation
from taktus.ports.connector import Intake, Taken
from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Autonomy, ConsumptionQuantities, ExactnessClass, Method

ROOT = Path(__file__).resolve().parents[3]
AT = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)
BASE = "https://taktus.example/instance-a"
GERMAN = Phrasebook.model_validate_json(
    (ROOT / "src/taktus/composition/phrasebooks/de.json").read_text("utf-8")
)

RUN = RunFacts(
    id="run_1",
    tenant=TENANT,
    process_version="invoices@2",
    state="running",
    consumed=ConsumptionQuantities(tokens_in=120, tokens_out=30, currency={"eur": 0.25}),
    steps=(
        StepFacts(id="read", method=Method.RULE, exactness=ExactnessClass.EXACT, state="succeeded"),
        StepFacts(
            id="draft",
            method=Method.LLM,
            exactness=ExactnessClass.FREE,
            state="running",
            depends_on=("read",),
            consumption=ConsumptionQuantities(tokens_in=120, tokens_out=30),
        ),
    ),
    created_at=AT,
    updated_at=AT,
)

PROCESS = ProcessFacts(
    id="invoices",
    tenant=TENANT,
    name="Invoices",
    version="2",
    autonomy=Autonomy(
        level=2, reason="a person confirms each booking", toward_next="twenty clean runs"
    ),
    steps=(
        ProcessStepFacts(
            id="read", method=Method.RULE, exactness=ExactnessClass.EXACT, reason="fixed fields"
        ),
        ProcessStepFacts(
            id="draft",
            method=Method.LLM,
            exactness=ExactnessClass.FREE,
            reason="free text",
            depends_on=("read",),
        ),
    ),
    versions=(VersionRef(version="2", active=True),),
    runs=(RunAtVersion(id="run_1", tenant=TENANT, state="running", created_at=AT),),
)


class Records:
    """The run and the process of the tenant `t`, and a run of another tenant."""

    def __init__(self, run: RunFacts = RUN) -> None:
        self._run = run

    async def run(self, tenant: Tenant, run_id: str) -> RunFacts | None:
        if run_id == "run_1":
            return self._run
        if run_id == "run_elsewhere":
            return self._run.model_copy(update={"id": run_id, "tenant": "other"})
        return None

    async def process(
        self, tenant: Tenant, process_id: str, version: str | None
    ) -> ProcessFacts | None:
        if process_id == "invoices" and version in (None, "2"):
            return PROCESS
        return None


def message(text: str, *, address: str = ADDRESS, event: str = "Ev1") -> Intake:
    return Intake.model_validate(
        {
            "event_id": event,
            "event": "message.posted",
            "channel": CHANNEL,
            "sender": {"account": "U0000000001", "kind": "person"},
            "intent": {"raw": text},
            "context": {"conversation": address},
            "reply_to": {"channel": CHANNEL, "address": address, "thread": event},
            "occurred_at": AT.isoformat(),
        }
    )


@pytest.fixture
async def given() -> OwnerChannel:
    channel = owner_channel(levels=Records())
    await channel.configure(view_base=BASE)
    return channel


async def ask(
    given: OwnerChannel, text: str, identity: str | None = OWNER, **more: Any
) -> Taken | None:
    return await given.owner.answers.take(TENANT, message(text, **more), identity)


async def test_a_run_is_answered_with_its_text_equivalent_and_a_link_to_it_live(
    given: OwnerChannel,
) -> None:
    taken = await ask(given, "Zeige Lauf run_1")
    assert taken is not None and taken.outcome == "shown" and taken.replied
    [said] = given.deliveries.said
    level = run_level(RUN)
    assert said.text.splitlines()[: 1 + len(level.steps)] == [
        level.run.text,
        *(f"• {step.text}" for step in level.steps),
    ]
    assert said.text.endswith(f"{GERMAN.live}: {BASE}/app/#/runs/run_1")
    assert "tokens_in 120" in said.text and "currency.eur 0.25" in said.text
    assert (said.channel, said.address, said.thread) == (CHANNEL, ADDRESS, "Ev1")


async def test_a_process_is_answered_with_its_graph_in_words_and_a_link_to_it_live(
    given: OwnerChannel,
) -> None:
    taken = await ask(given, "zeige prozess invoices@2")
    assert taken is not None and taken.outcome == "shown"
    [said] = given.deliveries.said
    level = process_level(PROCESS)
    for text in (level.process.text, *(s.text for s in level.steps), *(r.text for r in level.runs)):
        assert text in said.text
    assert said.text.endswith(f"{BASE}/app/#/processes/invoices/2")


async def test_someone_the_owner_named_is_shown_it_too(given: OwnerChannel) -> None:
    taken = await ask(given, "zeige lauf run_1", NAMED)
    assert taken is not None and taken.outcome == "shown"


async def test_what_the_asker_may_not_see_is_answered_as_what_does_not_exist(
    given: OwnerChannel,
) -> None:
    answers = [
        await ask(given, "zeige lauf run_elsewhere", event="Ev1"),
        await ask(given, "zeige lauf run_9", event="Ev2"),
        await ask(given, "zeige prozess invoices@7", event="Ev3"),
        await ask(given, "zeige lauf run_1", OUTSIDER, event="Ev4"),
    ]
    assert [a.outcome if a else None for a in answers] == ["not_shown"] * 4
    assert [s.text for s in given.deliveries.said] == [GERMAN.not_shown] * 4


async def test_an_answer_that_would_carry_a_secret_is_not_sent() -> None:
    leaking = RUN.model_copy(update={"process_version": f"{SECRET}@1"})
    given = owner_channel(levels=Records(leaking))
    await given.configure(view_base=BASE)
    taken = await ask(given, "zeige lauf run_1")
    assert taken is not None and taken.outcome == "not_shown"
    assert all(SECRET not in s.text for s in given.deliveries.said)


async def test_a_message_at_another_address_or_from_nobody_placed_is_not_taken(
    given: OwnerChannel,
) -> None:
    assert await ask(given, "zeige lauf run_1", address="C0000000099") is None
    assert await ask(given, "zeige lauf run_1", None) is None
    assert await ask(given, "Bitte P-01 starten") is None
    assert given.deliveries.said == []


async def test_without_the_control_plane_s_address_the_text_comes_without_a_link() -> None:
    given = owner_channel(levels=Records())
    await given.configure()
    await ask(given, "zeige lauf run_1")
    [said] = given.deliveries.said
    assert "/app/#/" not in said.text and GERMAN.live not in said.text


async def test_a_phrasebook_without_the_words_reads_no_request(given: OwnerChannel) -> None:
    older = GERMAN.model_copy(
        update={"show_run_words": None, "show_process_words": None, "live": None, "not_shown": None}
    )
    assert representation("zeige lauf run_1", older) is None


def test_a_request_is_the_words_and_one_identifier() -> None:
    assert representation("Zeige Lauf run_1.", GERMAN) == Asked(level="run", id="run_1")
    assert representation("zeige prozess p@3", GERMAN) == Asked(
        level="process", id="p", version="3"
    )
    assert representation("zeige prozess p", GERMAN) == Asked(level="process", id="p")
    for text in ("zeige lauf", "zeige lauf run_1 run_2", "lauf run_1", "zeige prozess @3"):
        assert representation(text, GERMAN) is None, text


def test_a_phrasebook_names_all_four_or_none() -> None:
    document = GERMAN.document()
    del document["live"]
    with pytest.raises(ValueError, match="all four"):
        Phrasebook.model_validate(document)


def test_the_link_is_a_route_the_web_app_has() -> None:
    """`level_url` builds the routes `web/src/lib/links.ts` builds; the routes exist."""
    routes = ROOT / "web/src/routes"
    assert (routes / "runs/[id]/+page.svelte").is_file()
    assert (routes / "processes/[id]/[[version]]/+page.svelte").is_file()
    links = (ROOT / "web/src/lib/links.ts").read_text("utf-8")
    assert "`#/runs/${" in links and "`#/processes/${" in links
