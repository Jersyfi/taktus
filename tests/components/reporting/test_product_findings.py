"""The product finding's rule, its grouping and what it sends (UC-6.12 §2; ADR-0046).

Pure: blocks in, findings out, and a channel in memory that holds what it was sent the way the
repository does — by the texts and their marks. The run against the fake repository service is
`tests/adapters/connectors/test_product_findings.py`.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import BaseModel

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryObjectStore, MemoryPersistence
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.reporting.application.service import (
    DISABLED,
    ENABLED,
    REPORTED,
    SENT,
    Kept,
    NotEnabled,
    ProductFindings,
    Sending,
    Sent,
    Withheld,
)
from taktus.components.reporting.domain.model import Blocked, Finding, Lack, Occurrence, Reported
from taktus.components.reporting.domain.service import leaving, texts
from taktus.components.reporting.domain.service.findings import findings, lack_of
from taktus.components.reporting.domain.service.pseudonyms import Pseudonyms
from taktus.components.reporting.ports import Held
from taktus.components.run.domain.model import block as run_block
from taktus.shared.v1 import LedgerEntry

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


@dataclass
class Content:
    """What the tenant holds, as the run's repository would answer."""

    held: list[str] = field(default_factory=list)

    async def values(self, tenant: str) -> Sequence[str]:
        return list(self.held)


class Randomness:
    """A different key for every instance, as the system's randomness draws one."""

    def token(self, length: int) -> str:
        return secrets.token_hex(length)


def kept(content: Content | None = None) -> Kept:
    persistence = MemoryPersistence()
    ledger = ChainedLedger(MemoryLedgerStore(persistence), _Clock())
    return Kept(ledger, MemoryObjectStore(), persistence, Randomness(), content or Content())


def product(
    source: Source,
    channel: Channel | None = None,
    *,
    shape: str | None = None,
    content: Content | None = None,
) -> ProductFindings:
    sending = None if channel is None else Sending(channel, "http://findings.invalid/mcp")
    return ProductFindings(source, kept(content), sending, shape=shape)


class _Clock:
    def now(self) -> datetime:
        return AT


async def test_a_finding_closed_by_the_product_is_not_reopened_and_a_new_lack_opens_anew() -> None:
    channel, source = Channel(), Source([blocked("run_1")])
    findings_ = product(source, channel)
    assert await findings_.send(TENANT) == Sent(opened=1)
    channel.close("1")
    # The occurrence ends after its finding was closed: the product took it up, nothing is sent.
    source.found = [blocked("run_1", seconds=60)]
    assert await findings_.send(TENANT) == Sent()
    # The same lack met again after the close: a finding of its own, not the closed one.
    source.found.append(blocked("run_2", after=timedelta(hours=1)))
    assert await findings_.send(TENANT) == Sent(opened=1)
    assert [h.open for h in channel.issues.values()] == [False, True]
    named = await findings_.pseudonyms(TENANT)
    body = channel.issues["2"].texts[0]
    assert named.run("run_2") in body and named.run("run_1") not in body


async def test_an_occurrence_that_ended_before_it_was_sent_is_sent_once_with_its_waiting() -> None:
    channel = Channel()
    findings_ = product(Source([blocked("run_1", seconds=90)]), channel)
    assert await findings_.send(TENANT) == Sent(opened=1)
    assert await findings_.send(TENANT) == Sent()
    (body,) = channel.issues["1"].texts
    assert "waited 90 s" in body
    assert "In all: 1 occurrence from 1 sender, 90 s waited over the 1 that ended." in body
    assert texts.reported([body])[0].state == "ended"


async def test_without_a_channel_nothing_is_sent_and_the_finding_is_shown() -> None:
    findings_ = product(Source([blocked("run_1"), blocked("run_2", seconds=30)]))
    assert not findings_.enabled
    assert await findings_.send(TENANT) == Sent()
    (one,) = await findings_.outgoing(TENANT)
    assert one.text.splitlines()[0] == "Product finding: no worker offers code.review"
    named = await findings_.pseudonyms(TENANT)
    assert f"Occurrence 2: sender `{named.source}`, run `{named.run('run_2')}`" in one.text
    assert "run_2" not in one.text, "shown as it would be sent by hand"
    assert [o.run_id for o in one.finding.occurrences] == ["run_1", "run_2"]


# --- the shape -------------------------------------------------------------------------------


async def test_without_a_form_a_finding_has_the_products_plain_shape() -> None:
    """No repository's backlog is the product's default (ADR-0092): the plain shape names no
    section of an issue form, and the occurrences follow below a rule with the mark."""
    channel = Channel()
    findings_ = product(Source([blocked("run_1")]), channel)
    assert await findings_.send(TENANT) == Sent(opened=1)
    (body,) = channel.issues["1"].texts
    assert "###" not in body and "Blocked by" not in body
    named = await findings_.pseudonyms(TENANT)
    assert "`code.review`" in body
    assert f"run `{named.run('run_1')}`, step `{named.step('review')}`" in body
    assert "\n---\n" in body and texts.reported([body])[0].lack


async def test_a_configured_form_is_filled_and_keeps_the_mark() -> None:
    shape = texts.form("## Lack\n\n$tried\n\n## Where\n\n$area: $lacking in $run/$step ($cause)")
    channel = Channel()
    findings_ = product(Source([blocked("run_1")]), channel, shape=shape)
    assert await findings_.send(TENANT) == Sent(opened=1)
    (body,) = channel.issues["1"].texts
    assert body.startswith("## Lack\n\nA step needed a worker that offers `code.review`.")
    named = await findings_.pseudonyms(TENANT)
    assert f"workers: code.review in {named.run('run_1')}/{named.step('review')}" in body
    assert texts.reported([body])[0].occurrence
    (one,) = await findings_.outgoing(TENANT)
    assert one.text.splitlines()[2] == "## Lack"


@pytest.mark.parametrize(
    ("text", "named"),
    [("$tried and $customer", "customer"), ("a lone $ sign", "`$$`"), ("  ", "empty")],
)
def test_a_form_that_names_anything_but_the_fields_is_refused(text: str, named: str) -> None:
    """A form fills identifiers, causes and names only (ADR-0006): nothing else can enter."""
    with pytest.raises(ValueError, match=re.escape(named)):
        texts.form(text)


# --- outside the project: enabled by its operator, nothing of the tenant, one finding ----------


async def entries_of(kept_: Kept, *kinds: str) -> list[LedgerEntry]:
    async with kept_.work.transaction(TENANT):
        return list(await kept_.ledger.of_kinds(TENANT, set(kinds)))


async def test_sending_is_off_by_default_and_each_change_of_the_setting_is_recorded() -> None:
    """ADR-0112 §1: one setting of the operator, recorded in the tenant's ledger before anything
    is sent; an instance that never enabled it records nothing and sends nothing."""
    on_instance, channel, source = kept(), Channel(), Source([blocked("run_1")])
    off = ProductFindings(source, on_instance)
    assert await off.send(TENANT) == Sent() and channel.issues == {}
    assert await entries_of(on_instance, ENABLED, DISABLED) == []

    address = "http://findings.invalid/mcp"
    on = ProductFindings(source, on_instance, Sending(channel, address))
    assert await on.send(TENANT) == Sent(opened=1)
    (enabled,) = await entries_of(on_instance, ENABLED, DISABLED)
    assert enabled.kind == ENABLED and enabled.adapter == channel.name
    assert enabled.content_digest is not None
    assert await on_instance.objects.get(enabled.content_digest) == address.encode()
    first_sent = (await entries_of(on_instance, SENT))[0]
    assert enabled.seq < first_sent.seq, "the setting is recorded before anything is sent"

    restarted = ProductFindings(source, on_instance, Sending(channel, address))
    await restarted.send(TENANT)
    assert len(await entries_of(on_instance, ENABLED, DISABLED)) == 1, "nothing changed"

    await ProductFindings(source, on_instance).send(TENANT)
    kinds = [e.kind for e in await entries_of(on_instance, ENABLED, DISABLED)]
    assert kinds == [ENABLED, DISABLED]


async def test_one_lack_is_one_finding_across_instances() -> None:
    """Two instances, each with its own sender, meet the same lack: one finding, two
    occurrences, each naming its sender, none naming an instance's own run."""
    channel = Channel()
    first = product(Source([blocked("run_1", seconds=60)]), channel)
    second = product(Source([blocked("run_1", after=timedelta(minutes=5), seconds=30)]), channel)
    assert await first.send(TENANT) == Sent(opened=1)
    assert await second.send(TENANT) == Sent(added=1)
    (issue,) = channel.issues.values()
    one, other = (await first.pseudonyms(TENANT)), (await second.pseudonyms(TENANT))
    assert one.source != other.source and one.run("run_1") != other.run("run_1")
    assert one.source in issue.texts[0] and other.source in issue.texts[1]
    total = "In all: 2 occurrences from 2 senders, 90 s waited over the 2 that ended."
    assert total in issue.texts[1]
    assert {r.source for r in texts.reported(issue.texts)} == {one.source, other.source}
    assert not any("run_1" in text for text in issue.texts)
    assert await first.send(TENANT) == Sent() and await second.send(TENANT) == Sent()


async def test_a_finding_whose_lack_names_a_value_of_the_tenant_is_withheld() -> None:
    content = Content(["Erika Mustermann", "Heidestraße 17, 51147 Köln"])
    channel = Channel()
    findings_ = product(
        Source([blocked("run_1", lacking="crm.erika-mustermann")]), channel, content=content
    )
    assert await findings_.send(TENANT) == Sent(withheld=1)
    assert channel.issues == {}, "nothing of it is sent"
    (one,) = await findings_.outgoing(TENANT)
    assert [m.kind for m in one.withheld] == ["tenant_value"]
    assert one.withheld[0].excerpt == "erika mustermann", "shown on the instance, with why"


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("the export of Erika Mustermann failed", "tenant_value"),
        ("ERIKA-MUSTERMANN", "tenant_value"),
        ("write to erika@example.org", "email"),
        ("call +49 221 1234567", "phone"),
        ("IBAN DE89 3704 0044 0532 0130 00", "iban"),
        ("card 4111 1111 1111 1111", "card"),
        ("the invoice of 4.711,00 EUR", "amount"),
        ("it cost € 1200", "amount"),
        ("she lives at Heidestraße 17", "street"),
        ("in 51147 Köln", "postcode"),
    ],
)
def test_the_rule_finds_a_value_of_the_tenant_and_the_shapes_of_personal_data(
    text: str, kind: str
) -> None:
    held = leaving.values(["Erika Mustermann"])
    assert kind in {m.kind for m in leaving.check([text], held)}


@pytest.mark.parametrize(
    "text",
    [
        "The step review fails when no worker offers code.review.",
        "Since release 0.4.0 the scheduler logs twice per tick.",
        "A run with 12 steps waited 600 s.",
    ],
)
def test_the_rule_lets_a_text_without_the_tenants_data_leave(text: str) -> None:
    held = leaving.values(["Erika Mustermann", "4.711,00 EUR", "main", "ok"])
    assert leaving.check([text, "code.review"], held) == ()


async def test_a_report_by_hand_is_checked_by_the_same_rule_and_sent_once_it_may_leave() -> None:
    """ADR-0112 §5: what a person writes is checked by the rule a finding is; it shows what
    will be sent, and is sent only as shown."""
    channel = Channel()
    on_instance = kept(Content(["Erika Mustermann"]))
    findings_ = ProductFindings(
        Source(), on_instance, Sending(channel, "http://findings.invalid/mcp")
    )
    named = await findings_.pseudonyms(TENANT)

    leaky = await findings_.by_hand(
        TENANT, "Export fails", "The export for Erika Mustermann, 4.711,00 EUR, fails."
    )
    assert {m.kind for m in leaky.withheld} == {"tenant_value", "amount"}
    with pytest.raises(Withheld):
        await findings_.send_by_hand(TENANT, leaky)
    assert channel.issues == {}

    clean = await findings_.by_hand(
        TENANT, "Export fails", "The export step fails after a retry.", run_id="run_1"
    )
    assert clean.withheld == ()
    assert clean.body.startswith("The export step fails after a retry.")
    assert named.source in clean.body and named.run("run_1") in clean.body
    assert "run_1" not in clean.body
    reference = await findings_.send_by_hand(TENANT, clean)
    assert channel.issues[reference].texts == (clean.body,)
    assert texts.reported(channel.issues[reference].texts) == (), "a report is no finding"
    (sent,) = await entries_of(on_instance, REPORTED)
    assert sent.refs.run_id == "run_1" and sent.refs.actor is None

    off = product(Source())
    with pytest.raises(NotEnabled):
        await off.send_by_hand(TENANT, await off.by_hand(TENANT, "t", "a text"))
    assert (await off.by_hand(TENANT, " ", "a text")).withheld[0].kind == "empty"


def test_a_pseudonym_is_the_same_under_one_key_and_cannot_be_computed_without_it() -> None:
    one, same, other = Pseudonyms(b"k" * 32), Pseudonyms(b"k" * 32), Pseudonyms(b"x" * 32)
    assert one.run("run_1") == same.run("run_1") != other.run("run_1")
    assert one.step("review") == same.step("review") != other.step("review")
    assert re.fullmatch(r"src_[0-9a-f]{20}", one.source) and one.source != other.source
    with pytest.raises(ValueError):
        Pseudonyms(b"short")
