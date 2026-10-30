"""A running step taken over and its result handed back in the owner's conversation (UC-4.19
*the chat offers "take over"*, ADR-0128 §7, issue #404).

The channel is configured from the shipped German phrasebook, over the same memory store as a
run engine with its queue and a runner. A take-over is read back and asked only on the same
person's `ja` in the same thread; the question where it stands shows the state the step reached;
a hand-back is read back with how the result was read, and handed back only on `ja`; a `nein`
drops either; a take-over that lapsed or was refused is said as such; anyone the owner did not
name, a message at another address, and a step that cannot be taken over are refused or not
read. What the engine does is held by `tests/components/run/test_takeover.py`.
"""

from __future__ import annotations

import json
from typing import Any

from components.run.test_runner import World, rule, until, work
from components.run.test_takeover import running
from fakes import FakeWorker, InnerStep
from fakes.owner_channel import (
    ADDRESS,
    CHANNEL,
    NAMED,
    OUTSIDER,
    OWNER,
    SECRET,
    TENANT,
    owner_channel,
)

from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.reporting.domain.model import OwnerChannel, PendingAct, Phrasebook
from taktus.components.reporting.domain.service import reading as rules
from taktus.components.run.domain.model import RunState, StepState
from taktus.composition.owner_channel import KnownSecrets, ShippedPhrasebooks
from taktus.composition.takeover_in_channel import ASKED, REFUSED, TAKEN, TakeoverInChannel

THREAD = "1700000000.000100"


def slow_worker() -> FakeWorker:
    return FakeWorker(
        script=(
            InnerStep("one", artifacts=(("out-1", b"first\n"),)),
            InnerStep("two"),
            InnerStep("three"),
        ),
        inner_seconds=0.15,
    )


class Given:
    def __init__(self, world: World, handler: TakeoverInChannel, said: Any) -> None:
        self.world = world
        self.handler = handler
        self.said = said
        self.n = 0

    async def say(self, text: str, who: str = OWNER, address: str = ADDRESS) -> Any:
        self.n += 1
        return await self.handler.take(
            TENANT, CHANNEL, address, THREAD, who, (), text, f"evt_{self.n}"
        )

    @property
    def last(self) -> str:
        return str(self.said[-1].text)


async def given(world: World) -> Given:
    channel = owner_channel(persistence=world.persistence)
    await channel.configure(view_base="https://taktus.example/a")
    handler = TakeoverInChannel(
        channels=MemoryRepository(world.persistence, OwnerChannel),
        pending=MemoryRepository(world.persistence, PendingAct),
        runs=world.runs,
        work=world.persistence,
        takeovers=world.engine,
        deliveries=channel.deliveries,
        secrets=KnownSecrets((SECRET,)),
        clock=channel.clock,
    )
    return Given(world, handler, channel.deliveries.said)


def takeover_in(text: str) -> str:
    """The take-over identifier the answer names."""
    return next(word.strip(":,.") for word in text.split() if word.startswith("tko"))


async def test_a_take_over_is_read_back_asked_on_yes_and_its_state_reaches_the_person() -> None:
    world = World(worker=slow_worker())
    run = await world.submit(work("w"), rule("r", 1, after=("w",)))
    runner = world.runner("r1")
    await running(world, run.id, "w")
    chat = await given(world)

    read = await chat.say(f"übernimm {run.id} w")
    assert read is not None and read.outcome == ASKED
    assert f"Schritt w von Lauf {run.id} übernehmen" in chat.last
    assert "ja" in chat.last.rsplit(".", 2)[-2], "the confirmation is asked for"
    assert world.worker.stops == [], "nothing asked before the confirmation"

    asked = await chat.say("ja")
    assert asked is not None and asked.outcome == TAKEN
    takeover = takeover_in(chat.last)
    assert f"https://taktus.example/a/app/#/runs/{run.id}" in chat.last

    await until(lambda: len(runner.outcomes) == 1)
    await world.stop(runner)
    shown = await chat.say(f"zeige übernahme {takeover}")
    assert shown is not None and shown.outcome == TAKEN
    assert f"Schritt w von Lauf {run.id} gehört dir bis" in chat.last
    assert "Ziel: g" in chat.last and "Abnahmekriterien: a" in chat.last
    assert "out-1" in chat.last, "what the worker produced so far"


async def test_a_hand_back_is_read_back_with_its_reading_and_handed_back_only_on_yes() -> None:
    world = World(worker=slow_worker())
    run = await world.submit(work("w"), rule("r", 1, after=("w",)))
    runner = world.runner("r1")
    await running(world, run.id, "w")
    chat = await given(world)
    await chat.say(f"übernimm {run.id} w")
    await chat.say("ja")
    takeover = takeover_in(chat.last)
    await until(lambda: len(runner.outcomes) == 1)
    await world.stop(runner)

    read = await chat.say(f'gib zurück {takeover}: {{"answer": 42}}')
    assert read is not None and read.outcome == ASKED
    assert "als JSON" in chat.last and f"Schritt w von Lauf {run.id}" in chat.last
    held = (await world.stored(run.id)).step_run("w")
    assert held.state is StepState.WAITING_HUMAN, "nothing handed back before the yes"

    dropped = await chat.say("nein")
    assert dropped is not None and dropped.outcome == REFUSED
    assert (await world.stored(run.id)).step_run("w").state is StepState.WAITING_HUMAN

    await chat.say(f"gib zurück {takeover}: behoben, siehe Branch fix-1")
    assert "als Text" in chat.last
    done = await chat.say("ja")
    assert done is not None and done.outcome == TAKEN
    assert "Zurückgegeben" in chat.last
    handed = (await world.stored(run.id)).step_run("w")
    assert handed.state is StepState.SUCCEEDED and handed.confirmed_by == OWNER
    result = handed.artifact(f"{takeover}.result")
    assert result is not None
    content = await world.objects.get(result.digest)
    assert json.loads(content or b"null") == "behoben, siehe Branch fix-1"

    runner = world.runner("r2")
    await until(lambda: len(runner.outcomes) == 1)
    await world.stop(runner)
    assert (await world.stored(run.id)).state is RunState.FINISHED
    await chat.say(f"zeige übernahme {takeover}")
    assert "wurde zurückgegeben" in chat.last
    again = await chat.say(f"gib zurück {takeover}: noch einmal")
    assert again is not None and again.outcome == REFUSED, "a second hand-back changes nothing"


async def test_a_lapsed_take_over_is_said_as_such_and_a_hand_back_then_changes_nothing() -> None:
    world = World(worker=slow_worker(), takeover_seconds=0.3)
    run = await world.submit(work("w"))
    runner = world.runner("r1")
    await running(world, run.id, "w")
    chat = await given(world)
    await chat.say(f"übernimm {run.id} w")
    await chat.say("ja")
    takeover = takeover_in(chat.last)
    await until(lambda: len(runner.outcomes) == 1)
    await world.stop(runner)
    await chat.say(f"gib zurück {takeover}: zu spät")

    runner = world.runner("r2")  # claims the job after the lease and takes the step back
    await until(lambda: len(runner.outcomes) >= 1)
    await world.stop(runner)
    refused = await chat.say("ja")
    assert refused is not None and refused.outcome == REFUSED
    assert "ist abgelaufen" in chat.last and "Nichts wurde zurückgegeben" in chat.last
    assert (await world.stored(run.id)).step_run("w").artifact(f"{takeover}.result") is None
    await chat.say(f"zeige übernahme {takeover}")
    assert "ist abgelaufen" in chat.last


async def test_a_take_over_of_a_step_that_ended_first_is_said_to_be_refused() -> None:
    # One step and no inner boundary: the worker finishes before it can stop.
    world = World(worker=FakeWorker(script=(InnerStep("only"),), inner_seconds=0.3))
    run = await world.submit(work("w"))
    runner = world.runner("r1")
    await running(world, run.id, "w")
    chat = await given(world)
    await chat.say(f"übernimm {run.id} w")
    await chat.say("ja")
    takeover = takeover_in(chat.last)
    await until(lambda: len(runner.outcomes) == 1)
    await world.stop(runner)
    await chat.say(f"zeige übernahme {takeover}")
    assert f"{takeover} wurde abgelehnt" in chat.last


async def test_only_the_owner_or_someone_named_and_only_a_running_worker_step() -> None:
    world = World(worker=slow_worker())
    run = await world.submit(work("w"), rule("r", 1, after=("w",)))
    runner = world.runner("r1")
    await running(world, run.id, "w")
    chat = await given(world)

    outsider = await chat.say(f"übernimm {run.id} w", who=OUTSIDER)
    assert outsider is not None and outsider.outcome == REFUSED
    not_running = await chat.say(f"übernimm {run.id} r")
    assert not_running is not None and not_running.outcome == REFUSED
    unknown = await chat.say("übernimm run_nothing w")
    assert unknown is not None and unknown.outcome == REFUSED
    assert "Seite des Laufs" in chat.last
    elsewhere = await chat.say(f"übernimm {run.id} w", address="C999")
    assert elsewhere is None
    assert await chat.say("zeige lauf x") is None, "not a take-over"

    await chat.say(f"übernimm {run.id} w")
    assert await chat.say("ja", who=NAMED) is None, "only the person who asked confirms"
    await world.stop(runner)
    assert all(stop.reason != "a person takes the step over" for _, stop in world.worker.stops)


async def test_a_result_that_carries_a_secret_value_is_not_read_back() -> None:
    world = World(worker=slow_worker())
    run = await world.submit(work("w"))
    runner = world.runner("r1")
    await running(world, run.id, "w")
    chat = await given(world)
    await chat.say(f"übernimm {run.id} w")
    await chat.say("ja")
    takeover = takeover_in(chat.last)
    await until(lambda: len(runner.outcomes) == 1)
    await world.stop(runner)
    refused = await chat.say(f"gib zurück {takeover}: {SECRET}")
    assert refused is not None and refused.outcome == REFUSED
    assert SECRET not in chat.last


def test_the_words_are_read_by_a_rule() -> None:
    book = Phrasebook.model_validate(ShippedPhrasebooks().shipped("en"))
    asked = rules.takeover_act("take over run_1 build", book)
    assert asked is not None and (asked.kind, asked.run, asked.step) == (
        "take_over",
        "run_1",
        "build",
    )
    back = rules.takeover_act('hand back tko_1: {"a": "b: c"}', book)
    assert back is not None and (back.takeover, back.result) == ("tko_1", '{"a": "b: c"}')
    shown = rules.takeover_act("Show takeover tko_1.", book)
    assert shown is not None and (shown.kind, shown.takeover) == ("show", "tko_1")
    assert rules.takeover_act("take over run_1", book) is None
    assert rules.takeover_act("hand back tko_1", book) is None
    assert rules.takeover_act("please take over run_1 build now", book) is None


async def test_a_message_to_a_running_step_is_read_back_and_sent_only_on_yes() -> None:
    """ADR-0156 §7: `nachricht <run> <step>: <text>` is read back with its text and asked only on
    the same person's `ja`; a step whose worker takes no message is refused with the reason."""
    worker = slow_worker()
    worker.steering = True
    world = World(worker=worker)
    run = await world.submit(work("w"))
    runner = world.runner("r1")
    await running(world, run.id, "w")
    chat = await given(world)

    read = await chat.say(f"nachricht {run.id} w: nimm den zweiten Spiegel")
    assert read is not None and read.outcome == ASKED
    assert '"nimm den zweiten Spiegel"' in chat.last and f"Lauf {run.id}" in chat.last
    assert "step.message_asked" not in await world.kinds(run.id), "nothing before the yes"
    other = await chat.say("ja", who=OUTSIDER)
    assert other is None or other.outcome != TAKEN, "only the person who asked confirms"

    sent = await chat.say("ja")
    assert sent is not None and sent.outcome == TAKEN
    assert "Geschickt als msg_" in chat.last
    await until(lambda: len(runner.outcomes) == 1)
    await world.stop(runner)
    assert [m.text for _, m in world.worker.messages] == ["nimm den zweiten Spiegel"]
    async with world.persistence.transaction(TENANT):
        entries = list(await world.ledger.entries(TENANT, run.id))
    (asked,) = [e for e in entries if e.kind == "step.message_asked"]
    assert asked.refs.actor == OWNER


async def test_a_message_the_worker_cannot_take_is_refused_with_its_reason() -> None:
    world = World(worker=slow_worker())
    run = await world.submit(work("w"))
    runner = world.runner("r1")
    await running(world, run.id, "w")
    chat = await given(world)
    await chat.say(f"nachricht {run.id} w: halt")
    refused = await chat.say("ja")
    await until(lambda: len(runner.outcomes) == 1)
    await world.stop(runner)
    assert refused is not None and refused.outcome == REFUSED
    assert "Nicht geschickt" in chat.last and "declares no steering" in chat.last
    assert world.worker.messages == []


def test_a_message_to_a_step_is_read_by_its_rule() -> None:
    book = Phrasebook.model_validate(ShippedPhrasebooks().shipped("de"))
    act = rules.takeover_act("Nachricht run_1 w: nimm: den zweiten", book)
    assert act is not None and (act.kind, act.run, act.step, act.result) == (
        "steer",
        "run_1",
        "w",
        "nimm: den zweiten",
    )
    assert rules.takeover_act("nachricht run_1: ohne Schritt", book) is None
    assert rules.takeover_act("nachricht run_1 w:", book) is None
