"""A run answers in the channel its command came from, by itself (ADR-0239, UC-1.1)."""

from __future__ import annotations

from datetime import timedelta

from components.run.test_pause_and_cancel import AT, BUDGET, TENANT, WORK, Harness
from fakes.identity import FakeReplies, FixedTenants

from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.run.application.service import StartRun
from taktus.components.run.domain.model import RunState
from taktus.composition.run_answers import WINDOW, RunAnswers
from taktus.shared.v1 import Command, Intent, Plan, ReplyTo

CHAT = ReplyTo(channel="channel.chat", address="C1", thread="1.1")


async def wired(h: Harness, reply_to: ReplyTo = CHAT) -> tuple[RunAnswers, FakeReplies]:
    plans = MemoryRepository(h.persistence, Plan)
    commands = MemoryRepository(h.persistence, Command)
    async with h.persistence.transaction(TENANT):
        await plans.put(TENANT, h.plan())
        await commands.put(
            TENANT,
            Command(
                id="cmd_1",
                channel=reply_to.channel,
                identity="idn_t",
                org_path=(TENANT,),
                intent=Intent(raw="run p@1"),
                reply_to=reply_to,
                received_at=AT,
            ),
        )
    replies = FakeReplies()
    answers = RunAnswers(
        FixedTenants((TENANT,)), h.ledger, h.runs, plans, commands, h.persistence, replies, h.clock
    )
    return answers, replies


async def kinds(h: Harness) -> list[str]:
    async with h.persistence.transaction(TENANT):
        return [f"{e.kind}:{e.outcome}" for e in await h.ledger.entries(TENANT)]


async def test_a_finished_run_answers_once_in_the_thread_its_command_came_from() -> None:
    h = Harness()
    run = await h.start()
    answers, replies = await wired(h)
    assert await answers.tick() == [(run.id, "said")]
    (tenant, to, text, key) = replies.said[0]
    assert (tenant, to.channel, to.address, to.thread) == (TENANT, "channel.chat", "C1", "1.1")
    assert text == f"Done: run {run.id} of p@1 finished."
    assert key.startswith(f"taktus:answer:{run.id}:")
    assert "run.answered:said" in await kinds(h)
    assert await answers.tick() == [], "an end is answered once"
    assert len(replies.said) == 1


async def test_a_run_that_waits_for_a_person_asks_back_and_is_asked_once_per_wait() -> None:
    h = Harness()
    step = h.plan().steps[0].model_copy(update={"depends_on": None})
    plan = h.plan().model_copy(update={"autonomy_level": 2, "steps": (step,)})
    run = await h.engine.start(
        StartRun(
            plan=plan,
            work={"a": WORK["a"]},
            budget=BUDGET,
            process_version="p@1",
            actor="idn_t",
            tenant=TENANT,
        )
    )
    assert run.state is RunState.WAITING_HUMAN
    answers, replies = await wired(h)
    assert await answers.tick() == [(run.id, "said")]
    assert "waits for you: a needs your answer" in replies.said[0][2]


async def test_a_command_from_no_channel_that_replies_is_recorded_and_not_said() -> None:
    h = Harness()
    run = await h.start()
    answers, replies = await wired(h, ReplyTo(channel="channel.cli", address="stdout"))
    assert await answers.tick() == [(run.id, "not_said")]
    assert replies.said == []
    assert "run.answered:not_said" in await kinds(h)


async def test_an_end_older_than_the_window_is_answered_by_nobody() -> None:
    h = Harness()
    await h.start()
    answers, replies = await wired(h)
    h.clock.current += WINDOW + timedelta(seconds=1)
    assert await answers.tick() == []
    assert replies.said == []
