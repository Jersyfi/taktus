"""Where a run or a process spends, asked in the owner's conversation (#449, ADR-0148).

The channel is configured from a shipped phrasebook. `spend <run>` answers the run step by step,
`spend <run> <other>` both runs side by side with whether each step produced the same result,
`spend process <process>` the process over thirty days; each with the link to the same view in
the web app. What cannot be priced is said. Anyone the owner did not name, a run of another
tenant and a message at another address are not shown anything; nothing is written.
"""

from __future__ import annotations

from typing import Any

from fakes.owner_channel import ADDRESS, CHANNEL, NAMED, OUTSIDER, OWNER, TENANT, owner_channel

from taktus.adapters.driven.memory import MemoryObjectStore, MemoryRepository
from taktus.components.accounting.application.service import SpendHandler
from taktus.components.reporting.domain.model import OwnerChannel, Phrasebook
from taktus.components.run.domain.model import Run
from taktus.composition.owner_channel import KnownSecrets, ShippedPhrasebooks
from taktus.composition.spend_in_channel import NOT_SHOWN, SHOWN, SpendInChannel, asked
from taktus.ports.ledger import Fact
from taktus.ports.worker import ComputeLimit, Limits
from taktus.shared.v1 import (
    Consumption,
    ExactnessClass,
    LedgerRefs,
    Method,
    Step,
)

THREAD = "1700000000.000200"


class Given:
    def __init__(self) -> None:
        self.channel = owner_channel()
        self.persistence = self.channel.persistence
        self.ledger = self.channel.identity.ledger
        self.runs = MemoryRepository(self.persistence, Run)
        self.handler = SpendInChannel(
            channels=MemoryRepository(self.persistence, OwnerChannel),
            runs=self.runs,
            work=self.persistence,
            spend=SpendHandler(self.ledger, MemoryObjectStore(), self.persistence),
            deliveries=self.channel.deliveries,
            secrets=KnownSecrets(()),
            clock=self.channel.clock,
        )
        self.n = 0

    async def run(self, run_id: str, output: int, digest: str, tenant: str = TENANT) -> None:
        now = self.channel.clock.now()
        run = Run(
            id=run_id,
            plan_id="pln_1",
            process_version="replies@1",
            tenant=tenant,
            identity="idn_t",
            autonomy_level=2,
            budget=Limits(compute=ComputeLimit(seconds=10, resource_class="cpu.small")),
            steps=(
                Step(
                    id="draft",
                    method=Method.RULE,
                    reason="r",
                    rejected=(),
                    exactness=ExactnessClass.EXACT,
                ),
            ),
            work={"draft": {"rule": "constant", "value": 1}},
            created_at=now,
            updated_at=now,
        )
        async with self.persistence.transaction(tenant):
            await self.runs.put(tenant, run)
            await self.ledger.record(
                tenant,
                Fact(
                    kind="step.finished",
                    refs=LedgerRefs(
                        tenant=tenant, run_id=run_id, step_id="draft", process_version="replies@1"
                    ),
                    method=Method.LLM,
                    adapter="model.fake",
                    consumption=Consumption(
                        tokens_by_model={"fake-model@1": {"input": 40, "output": output}}, turns=1
                    ),
                    outcome="succeeded",
                    content_digest="sha256:" + digest * 64,
                ),
            )

    async def say(self, text: str, who: str = OWNER, address: str = ADDRESS) -> Any:
        self.n += 1
        return await self.handler.take(
            TENANT, CHANNEL, address, THREAD, who, (), text, f"evt_{self.n}"
        )

    @property
    def last(self) -> str:
        return str(self.channel.deliveries.said[-1].text)


async def given() -> Given:
    g = Given()
    await g.channel.configure(language="en", view_base="https://taktus.example/a")
    return g


async def test_a_run_s_spend_is_answered_step_by_step_with_its_link() -> None:
    g = await given()
    await g.run("run_1", 7, "a")
    answered = await g.say("spend run_1")
    assert answered is not None and answered.outcome == SHOWN
    assert "Where run run_1 spent, step by step:" in g.last
    assert "• draft: not priced, not priced Takte, 40 tokens in, 7 out, 1 turns" in g.last
    assert "https://taktus.example/a/app/#/spend/runs/run_1" in g.last


async def test_two_runs_are_answered_side_by_side_with_whether_each_result_is_the_same() -> None:
    g = await given()
    await g.run("run_1", 7, "a")
    await g.run("run_2", 9, "b")
    answered = await g.say("Spend run_1 run_2.")
    assert answered is not None and answered.outcome == SHOWN
    assert "Run run_1 and run run_2 side by side" in g.last
    assert "• draft: not priced, 40/7 | not priced, 40/9 | different result" in g.last
    assert "#/spend/runs/run_1/run_2" in g.last


async def test_a_process_s_spend_is_answered_over_thirty_days() -> None:
    g = await given()
    await g.run("run_1", 7, "a")
    await g.run("run_2", 9, "a")
    answered = await g.say("spend process replies")
    assert answered is not None and answered.outcome == SHOWN
    assert "Where process replies spent over 30 days, in 2 runs" in g.last
    assert "#/spend/processes/replies" in g.last
    nothing = await g.say("spend process unknown")
    assert nothing is not None and nothing.outcome == NOT_SHOWN


async def test_only_the_owner_and_whom_they_named_are_shown_runs_they_may_see() -> None:
    g = await given()
    await g.run("run_1", 7, "a")
    await g.run("run_9", 7, "a", tenant="elsewhere")
    named = await g.say("spend run_1", who=NAMED)
    assert named is not None and named.outcome == SHOWN
    outsider = await g.say("spend run_1", who=OUTSIDER)
    assert outsider is not None and outsider.outcome == NOT_SHOWN
    assert "run_1" not in g.last
    other = await g.say("spend run_9")
    assert other is not None and other.outcome == NOT_SHOWN
    assert await g.say("spend run_1", address="D0000000999") is None
    assert await g.say("show run run_1") is None


def test_the_words_are_read_as_the_channel_reads_its_other_words() -> None:
    shipped = ShippedPhrasebooks().shipped("de")
    assert shipped is not None
    book = Phrasebook.model_validate(shipped)
    assert asked("Kosten lauf_1", book) == asked("kosten lauf_1", book)
    read = asked("kosten prozess antworten", book)
    assert read is not None and (read.kind, read.subject) == ("process", "antworten")
    two = asked("kosten lauf_1 lauf_2", book)
    assert two is not None and (two.kind, two.other) == ("against", "lauf_2")
    assert asked("kosten", book) is None
    assert asked("kosten a b c", book) is None
