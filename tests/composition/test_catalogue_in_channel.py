"""What a person may ask Taktus for, asked and started in the owner's conversation (UC-1.13,
ADR-0159 §3).

The channel is configured from the shipped German phrasebook. The catalogue is listed with what
to write to start each entry, or the inputs it needs where a reply cannot give them; a start is
read back and runs only on the same person's `ja` in the same thread, on the conversation's
channel, acting as that person; a `nein` drops it; anyone the owner did not name is refused; a
process the person may not see, or one that needs an input, is answered with the same sentence.
What the start does is held by `tests/adapters/rest/test_catalogue.py`; here it is recorded.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from fakes.owner_channel import ADDRESS, CHANNEL, NAMED, OUTSIDER, OWNER, TENANT, owner_channel
from fakes.owner_channel import OwnerChannel as World

from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.reporting.domain.model import OwnerChannel, PendingAct
from taktus.components.reporting.domain.service.catalogue import (
    Catalogue,
    CatalogueFacts,
    CatalogueInput,
    catalogue,
)
from taktus.composition.catalogue_in_channel import (
    ASKED,
    LISTED,
    REFUSED,
    STARTED,
    CatalogueInChannel,
)
from taktus.composition.owner_channel import KnownSecrets
from taktus.ports.identity import Resolution

THREAD = "1700000000.000100"

PROCESSES = [
    CatalogueFacts(process="daily", name="Täglicher Bericht", version="daily@3", level=3),
    CatalogueFacts(
        process="offer",
        name="Angebot",
        version="offer@1",
        level=2,
        inputs=(CatalogueInput(name="client", description="wer", required=True),),
    ),
]


class Surface:
    """The surface's catalogue as the pure view draws it; every start recorded."""

    def __init__(self) -> None:
        self.started: list[tuple[str, str, dict[str, Any], str, str]] = []

    async def catalogue(self, who: Resolution, *, agent_may_start: bool) -> Catalogue:
        return catalogue(PROCESSES, agent_may_start=agent_may_start, chat_word="starte")

    async def start(
        self, who: Resolution, process: str, inputs: Any, *, channel: str, address: str
    ) -> Any:
        self.started.append((who.identity, process, dict(inputs), channel, address))
        return SimpleNamespace(id="run_9")


class Identities:
    async def identity(self, tenant: str, identity: str) -> Resolution | None:
        if identity not in (OWNER, NAMED, OUTSIDER):
            return None
        return Resolution(tenant=tenant, identity=identity, org_path=(tenant,))


async def given() -> tuple[World, Surface, CatalogueInChannel]:
    world = owner_channel()
    await world.configure(view_base="https://taktus.example/a")
    surface = Surface()
    handler = CatalogueInChannel(
        channels=MemoryRepository(world.persistence, OwnerChannel),
        pending=MemoryRepository(world.persistence, PendingAct),
        work=world.persistence,
        surface=cast(Any, surface),
        identities=cast(Any, Identities()),
        deliveries=world.deliveries,
        secrets=KnownSecrets(()),
        clock=world.clock,
    )
    return world, surface, handler


async def say(handler: CatalogueInChannel, text: str, who: str = OWNER, n: int = 1) -> Any:
    return await handler.take(TENANT, CHANNEL, ADDRESS, THREAD, who, (), text, f"evt_{n}_{text}")


async def test_the_catalogue_is_listed_with_what_to_write_and_what_a_reply_cannot_give() -> None:
    world, surface, handler = await given()
    listed = await say(handler, "Was kann ich anfragen?")
    assert listed is not None and listed.outcome == LISTED
    (said,) = world.deliveries.said
    assert "Täglicher Bericht: schreibe „starte daily“" in said.text
    assert "Angebot: braucht client" in said.text
    assert "https://taktus.example/a/app/#/catalogue" in said.text
    assert surface.started == [], "a list acts on nothing"


async def test_a_start_is_read_back_and_runs_only_on_yes_as_the_person_on_the_channel() -> None:
    world, surface, handler = await given()
    asked = await say(handler, "starte daily")
    assert asked is not None and asked.outcome == ASKED
    assert surface.started == [], "nothing starts before the confirmation"
    assert "daily (Täglicher Bericht)" in world.deliveries.said[-1].text
    assert await say(handler, "ja", who=NAMED, n=2) is None, "only the person who asked"
    done = await say(handler, "ja", n=3)
    assert done is not None and done.outcome == STARTED
    assert surface.started == [(OWNER, "daily", {}, CHANNEL, ADDRESS)]
    assert "run_9" in world.deliveries.said[-1].text
    assert "/app/#/runs/run_9" in world.deliveries.said[-1].text
    assert await say(handler, "ja", n=4) is None, "a confirmation counts once"


async def test_a_start_dropped_with_no_starts_nothing() -> None:
    _, surface, handler = await given()
    await say(handler, "starte daily")
    dropped = await say(handler, "nein", n=2)
    assert dropped is not None and dropped.outcome == REFUSED
    assert surface.started == []


async def test_an_unseen_process_one_that_needs_an_input_and_an_outsider_are_refused_alike() -> (
    None
):
    world, surface, handler = await given()
    for n, (text, who) in enumerate(
        [("starte nothing", OWNER), ("starte offer", OWNER), ("starte daily", OUTSIDER)]
    ):
        refused = await say(handler, text, who=who, n=n)
        assert refused is not None and refused.outcome == REFUSED
    assert len({s.text for s in world.deliveries.said}) == 1, "one sentence for all three"
    assert surface.started == []
    elsewhere = await handler.take(
        TENANT, CHANNEL, "C999", THREAD, OWNER, (), "starte daily", "evt_x"
    )
    assert elsewhere is None, "another address is not this handler's"
    assert await say(handler, "zeige prozess daily", n=9) is None, "not a start"
