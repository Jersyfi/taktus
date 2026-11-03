"""An outside participant's answer, taken from a channel's intake (ADR-0155).

A supplier, a client or an authority answers a `human` step in the thread the step before it
opened: a mail, a chat. They have no Taktus account. Their message is matched by its channel
and thread against the steps of the tenant that wait for a participant, before the owner-facing
channel reads it and before the sender's identity matters (ADR-0040). The engine reads the
answer and says what to reply; this module finds the step and says it in the thread.

Everything else goes on to the next taker, as any other message.
"""

from __future__ import annotations

from typing import Protocol

from taktus.components.run.application.service import AnswerParticipant, ParticipantAnswered
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.ports.connector import ChannelAnswers, ChannelReplies, Intake, Taken
from taktus.ports.persistence import Queried, UnitOfWork


class Engine(Protocol):
    async def answer_participant(self, command: AnswerParticipant) -> ParticipantAnswered: ...


def waiting_step(run: Run, channel: str, thread: str) -> str | None:
    """The step of the run that waits for a participant's answer in this channel and thread."""
    for step_run in run.step_runs:
        block = step_run.block
        if (
            step_run.state is StepState.WAITING_HUMAN
            and block is not None
            and block.awaited is not None
            and block.awaited.channel == channel
            and block.awaited.thread == thread
        ):
            return step_run.step_id
    return None


class ParticipantAnswers:
    """`ChannelAnswers` for the participants of waiting steps, ahead of `then`."""

    def __init__(
        self,
        runs: Queried[Run],
        work: UnitOfWork,
        engine: Engine,
        replies: ChannelReplies,
        then: ChannelAnswers | None = None,
        *,
        enqueue: bool = True,
    ) -> None:
        self._runs = runs
        self._work = work
        self._engine = engine
        self._replies = replies
        self._then = then
        self._enqueue = enqueue

    async def take(
        self,
        tenant: str,
        intake: Intake,
        identity: str | None,
        roles: tuple[str, ...] = (),
    ) -> Taken | None:
        taken = await self._participant(tenant, intake)
        if taken is not None:
            return taken
        if self._then is None:
            return None
        return await self._then.take(tenant, intake, identity, roles)

    async def _participant(self, tenant: str, intake: Intake) -> Taken | None:
        thread = intake.context.get("thread")
        if not isinstance(thread, str) or not thread:
            return None
        async with self._work.transaction(tenant):
            waiting = await self._runs.having(tenant, "state", RunState.WAITING_HUMAN.value)
        for run in waiting:
            step_id = waiting_step(run, intake.channel, thread)
            if step_id is None:
                continue
            answered = await self._engine.answer_participant(
                AnswerParticipant(
                    run_id=run.id,
                    step_id=step_id,
                    tenant=tenant,
                    channel=intake.channel,
                    account=intake.sender.account,
                    text=intake.intent.raw,
                    enqueue=self._enqueue,
                )
            )
            if not answered.taken:
                return None
            replied = False
            if answered.say is not None:
                replied = await self._replies.reply(
                    tenant,
                    intake.reply_to,
                    answered.say,
                    key=f"participant:{run.id}:{step_id}:{intake.event_id}",
                )
            return Taken(outcome=f"participant_{answered.outcome}", replied=replied)
        return None
