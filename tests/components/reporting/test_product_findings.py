"""The product finding's rule, its grouping and what it sends (UC-6.12 §2; ADR-0046).

Pure: blocks in, findings out, and a channel in memory that holds what it was sent the way the
repository does — by the texts and their marks. The run against the fake repository service is
`tests/adapters/connectors/test_product_findings.py`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import BaseModel

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryObjectStore, MemoryPersistence
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.reporting.application.service import ProductFindings, Sending, Sent
from taktus.components.reporting.domain.model import Blocked, Finding, Lack, Occurrence, Reported
from taktus.components.reporting.domain.service import texts
from taktus.components.reporting.domain.service.findings import findings, lack_of
from taktus.components.reporting.ports import Held
from taktus.components.run.domain.model import block as run_block

AT = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)
TENANT = "t"
OTHER_CAUSES = sorted(
    {
        run_block.AT_CAPACITY,
        run_block.REJECTED_BY_CAPACITY,
        run_block.REJECTED_BY_ADMISSION,
        run_block.HALTED_AT_LIMIT,
        run_block.AT_PROVIDER_LIMIT,
        run_block.AWAITING_CONFIRMATION,
        run_block.AWAITING_PERFORMANCE,
        run_block.AWAITING_DECISION,
        run_block.WAITING_ON_STATE,
        run_block.WAITING_ON_CLOCK,
        run_block.HELD_BACK,
    }
)


def blocked(
    run: str,
    *,
    cause: str = "no_worker",
    lacking: str | None = "code.review",
    after: timedelta = timedelta(0),
    seconds: float | None = None,
) -> Blocked:
    return Blocked(
        cause=cause,
        run_id=run,
        step_id="review",
        since=AT + after,
        seconds=seconds,
        lacking=lacking,
    )


# --- the rule ---------------------------------------------------------------------------------


@pytest.mark.parametrize("cause", sorted(run_block.LACKS))
def test_a_block_for_a_lack_of_the_product_is_a_finding(cause: str) -> None:
    lack = lack_of(blocked("run_1", cause=cause))
    assert lack is not None and lack.cause == cause and lack.lacking == "code.review"


@pytest.mark.parametrize("cause", OTHER_CAUSES)
def test_no_other_block_is_a_finding(cause: str) -> None:
    """Anything else a person raises by hand, from the run."""
    assert lack_of(blocked("run_1", cause=cause)) is None
    assert findings([blocked("run_1", cause=cause)]) == ()


@pytest.mark.parametrize("lacking", [None, "Customer ACME payroll", "a b", "x;y"])
def test_a_lack_not_named_by_an_identifier_is_never_a_finding(lacking: str | None) -> None:
    """Nothing that is not an identifier reaches a finding, so nothing of a project's text can."""
    assert lack_of(blocked("run_1", lacking=lacking)) is None


def test_the_same_lack_met_twice_is_one_finding_with_two_occurrences() -> None:
    (finding,) = findings(
        [
            blocked("run_2", after=timedelta(minutes=10), seconds=300),
            blocked("run_1", seconds=900),
            blocked("run_1"),  # the same block, read while still open: one occurrence
        ]
    )
    assert [o.run_id for o in finding.occurrences] == ["run_1", "run_2"]
    assert finding.waited == 1200
    two = findings([blocked("run_1"), blocked("run_3", cause="no_connector", lacking="x.y")])
    assert len(two) == 2, "another lack is another finding"


def test_no_value_of_a_finding_can_hold_a_person() -> None:
    """Principle 14: no field for a person, and no field can be added."""
    for model in (Blocked, Lack, Occurrence, Finding, Reported, Held):
        assert issubclass(model, BaseModel)
        assert model.model_config.get("extra") == "forbid", model.__name__
        names = set(model.model_fields)
        assert not names & {"actor", "person", "identity", "by", "who", "author"}, model.__name__


# --- what is sent ------------------------------------------------------------------------------


@dataclass
class Channel:
    """A channel in memory: findings by number, each with its texts, open or closed."""

    issues: dict[str, Held] = field(default_factory=dict)
    keys: set[str] = field(default_factory=set)

    @property
    def name(self) -> str:
        return "findings.memory"

    async def held(self, tenant: str) -> Sequence[Held]:
        return list(self.issues.values())

    async def open(self, tenant: str, title: str, body: str, *, key: str) -> str:
        assert key not in self.keys
        self.keys.add(key)
        reference = str(len(self.issues) + 1)
        self.issues[reference] = Held(reference=reference, open=True, texts=(body,))
        return reference

    async def add(self, tenant: str, reference: str, text: str, *, key: str) -> None:
        assert key not in self.keys
        self.keys.add(key)
        held = self.issues[reference]
        self.issues[reference] = held.model_copy(update={"texts": (*held.texts, text)})

    def close(self, reference: str) -> None:
        self.issues[reference] = self.issues[reference].model_copy(update={"open": False})


@dataclass
class Source:
    found: list[Blocked] = field(default_factory=list)

    async def blocks(self, tenant: str) -> Sequence[Blocked]:
        return list(self.found)


def sending(channel: Channel) -> Sending:
    persistence = MemoryPersistence()
    ledger = ChainedLedger(MemoryLedgerStore(persistence), _Clock())
    return Sending(channel, ledger, MemoryObjectStore(), persistence)


class _Clock:
    def now(self) -> datetime:
        return AT


async def test_a_finding_closed_by_the_product_is_not_reopened_and_a_new_lack_opens_anew() -> None:
    channel, source = Channel(), Source([blocked("run_1")])
    product = ProductFindings(source, sending(channel))
    assert await product.send(TENANT) == Sent(opened=1)
    channel.close("1")
    # The occurrence ends after its finding was closed: the product took it up, nothing is sent.
    source.found = [blocked("run_1", seconds=60)]
    assert await product.send(TENANT) == Sent()
    # The same lack met again after the close: a finding of its own, not the closed one.
    source.found.append(blocked("run_2", after=timedelta(hours=1)))
    assert await product.send(TENANT) == Sent(opened=1)
    assert [h.open for h in channel.issues.values()] == [False, True]
    assert "run_2" in channel.issues["2"].texts[0] and "run_1" not in channel.issues["2"].texts[0]


async def test_an_occurrence_that_ended_before_it_was_sent_is_sent_once_with_its_waiting() -> None:
    channel = Channel()
    product = ProductFindings(Source([blocked("run_1", seconds=90)]), sending(channel))
    assert await product.send(TENANT) == Sent(opened=1)
    assert await product.send(TENANT) == Sent()
    (body,) = channel.issues["1"].texts
    assert (
        "waited 90 s" in body and "In all: 1 occurrence, 90 s waited over the 1 that ended." in body
    )
    assert texts.reported([body])[0].state == "ended"


async def test_without_a_channel_nothing_is_sent_and_the_finding_is_shown() -> None:
    product = ProductFindings(Source([blocked("run_1"), blocked("run_2", seconds=30)]))
    assert not product.enabled
    assert await product.send(TENANT) == Sent()
    (finding,) = await product.findings(TENANT)
    shown = texts.shown(finding)
    assert shown.splitlines()[0] == "Product finding: no worker offers code.review"
    assert "Occurrence 2: run `run_2`" in shown
