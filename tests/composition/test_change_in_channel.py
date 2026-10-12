"""A process changed in dialogue in the owner's conversation (UC-4.15 *the same from the web app
and from the chat*, ADR-0091 §6, issue #299).

The channel is configured from the shipped German phrasebook. A change in words starts S-07 for
the owner; a rehearsal needs no confirmation; a commissioning and a rollback are read back and
take effect only on the same person's `ja` in the same thread, and a `nein` drops them; anyone
the owner did not name is refused; a message at another address is not this handler's. What the
acts do is held by `tests/composition/test_proposals.py`; here they are recorded.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from fakes.owner_channel import ADDRESS, CHANNEL, NAMED, OUTSIDER, OWNER, TENANT, owner_channel
from fakes.owner_channel import OwnerChannel as World

from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.reporting.domain.model import OwnerChannel, PendingAct
from taktus.composition.change_in_channel import ASKED, CHANGED, REFUSED, ChangeInChannel
from taktus.composition.owner_channel import KnownSecrets

THREAD = "1700000000.000100"


class Acts:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def ask(self, *args: Any) -> Any:
        self.calls.append(("ask", args))
        return SimpleNamespace(id="run_7")

    async def rehearse(self, *args: Any) -> Any:
        self.calls.append(("rehearse", args))
        return None, SimpleNamespace(id="run_8")

    async def commission(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(("commission", args))
        return SimpleNamespace(version="9")

    async def rollback(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(("rollback", args))
        return SimpleNamespace(version="4")


class Proposals:
    async def find(self, tenant: str, proposal_id: str) -> Any:
        return SimpleNamespace(id=proposal_id, process_id="daily", version="9")


async def given() -> tuple[World, Acts, ChangeInChannel]:
    world = owner_channel()
    await world.configure(view_base="https://taktus.example/a")
    acts = Acts()
    handler = ChangeInChannel(
        channels=MemoryRepository(world.persistence, OwnerChannel),
        pending=MemoryRepository(world.persistence, PendingAct),
        work=world.persistence,
        acts=cast(Any, acts),
        proposals=cast(Any, Proposals()),
        deliveries=world.deliveries,
        secrets=KnownSecrets(()),
        clock=world.clock,
    )
    return world, acts, handler


async def say(handler: ChangeInChannel, text: str, who: str = OWNER, n: int = 1) -> Any:
    return await handler.take(TENANT, CHANNEL, ADDRESS, THREAD, who, text, f"evt_{n}_{text}")


async def test_a_change_in_words_starts_s07_for_the_owner_and_links_the_page() -> None:
    world, acts, handler = await given()
    taken = await say(handler, "ändere prozess daily: prüfe den Titel vor dem Öffnen")
    assert taken is not None and taken.outcome == CHANGED
    assert acts.calls == [("ask", (TENANT, "daily", "prüfe den Titel vor dem Öffnen", OWNER))]
    (said,) = world.deliveries.said
    assert "run_7" in said.text and "https://taktus.example/a/app/#/changes/daily" in said.text


async def test_a_commissioning_is_read_back_and_takes_effect_only_on_yes() -> None:
    world, acts, handler = await given()
    asked = await say(handler, "beauftrage prp_1")
    assert asked is not None and asked.outcome == ASKED
    assert acts.calls == [], "nothing takes effect before the confirmation"
    assert "Version 9 von daily" in world.deliveries.said[-1].text
    done = await say(handler, "ja", n=2)
    assert done is not None and done.outcome == CHANGED
    assert acts.calls == [("commission", (TENANT, "daily", "prp_1", OWNER))]
    assert "Version 9 von daily ist aktiv" in world.deliveries.said[-1].text
    assert await say(handler, "ja", n=3) is None, "a confirmation counts once"


async def test_a_rollback_dropped_with_no_changes_nothing() -> None:
    world, acts, handler = await given()
    await say(handler, "zurück zu daily@1")
    assert "Version 1 von daily" in world.deliveries.said[-1].text
    dropped = await say(handler, "nein", n=2)
    assert dropped is not None and dropped.outcome == REFUSED
    assert acts.calls == []


async def test_only_the_person_who_asked_confirms_and_a_rehearsal_needs_no_confirmation() -> None:
    world, acts, handler = await given()
    await say(handler, "zurück zu daily@1")
    assert await say(handler, "ja", who=NAMED, n=2) is None
    assert acts.calls == []
    rehearsed = await say(handler, "probe prp_1", who=NAMED, n=3)
    assert rehearsed is not None and rehearsed.outcome == CHANGED
    assert acts.calls == [("rehearse", (TENANT, "daily", "prp_1", NAMED))]


async def test_anyone_the_owner_did_not_name_is_refused_and_another_address_is_not_read() -> None:
    world, acts, handler = await given()
    refused = await say(handler, "ändere prozess daily: alles anders", who=OUTSIDER)
    assert refused is not None and refused.outcome == REFUSED
    assert acts.calls == []
    elsewhere = await handler.take(
        TENANT, CHANNEL, "C999", THREAD, OWNER, "ändere prozess daily: x", "evt_x"
    )
    assert elsewhere is None
    assert await say(handler, "zeige prozess daily") is None, "not a change"
