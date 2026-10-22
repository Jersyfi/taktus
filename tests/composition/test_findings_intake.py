"""A finding leaves an instance only as a product candidate, signed, to the intake of the
project's own instance (UC-6.12 §2, ADR-0118, DEC-0217).

Two instances, each over memory, each with its owner-facing channel as the composition root
wires it (`fakes/owner_channel.py`). The sending instance classifies its lacks against the
list the release carries (`composition/shipped.json`) and submits its candidates through
`IntakeClient`, over HTTP, to the intake route of the receiving instance
(`adapters/driving/rest/findings.py`). The receiving instance opens and adds to issues through
a channel in memory that holds what it was sent as the repository does, by texts and marks.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
from fakes.owner_channel import OwnerChannel, owner_channel
from fastapi import FastAPI

from taktus.adapters.driven.memory import MemoryBackupLog, MemoryObjectStore, MemoryTenantStore
from taktus.adapters.driven.signing import Ed25519Signatures
from taktus.adapters.driving.rest import findings as route
from taktus.components.reporting.application.service import (
    RECEIVED,
    FindingsIntake,
    IntakeOptions,
    Kept,
    ProductFindings,
    Sending,
    Sent,
    Taking,
    payload_of,
    report_of,
)
from taktus.components.reporting.domain.model import Blocked, Submission
from taktus.components.reporting.domain.service import texts
from taktus.components.reporting.ports import Held
from taktus.composition.alerts import alerts
from taktus.composition.findings import IntakeClient
from taktus.composition.shipped import load as load_shipped

TENANT = "t"
AT = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
URL = "http://project.test/findings/intake"


@dataclass
class Channel:
    """The repository in memory: findings by number, each with its texts, as the intake's own
    connector would write them."""

    issues: dict[str, Held] = field(default_factory=dict)
    titles: dict[str, str] = field(default_factory=dict)
    keys: dict[str, str] = field(default_factory=dict)
    """By idempotency key, the issue it opened or added to: a repeat changes nothing."""

    @property
    def name(self) -> str:
        return "findings.memory"

    async def held(self, tenant: str) -> Sequence[Held]:
        return list(self.issues.values())

    async def open(self, tenant: str, title: str, body: str, *, key: str) -> str:
        if key in self.keys:
            return self.keys[key]
        reference = str(len(self.issues) + 1)
        self.keys[key] = reference
        self.issues[reference] = Held(reference=reference, open=True, texts=(body,))
        self.titles[reference] = title
        return reference

    async def add(self, tenant: str, reference: str, text: str, *, key: str) -> None:
        assert key not in self.keys
        self.keys[key] = reference
        held = self.issues[reference]
        self.issues[reference] = held.model_copy(update={"texts": (*held.texts, text)})

    def every_text(self) -> str:
        return "\n".join(
            [*self.titles.values(), *(t for h in self.issues.values() for t in h.texts)]
        )


@dataclass
class Source:
    found: list[Blocked] = field(default_factory=list)

    async def blocks(self, tenant: str) -> Sequence[Blocked]:
        return list(self.found)


@dataclass
class Content:
    held: list[str] = field(default_factory=list)

    async def values(self, tenant: str) -> Sequence[str]:
        return list(self.held)


class Randomness:
    def token(self, length: int) -> str:
        return secrets.token_hex(length)


def blocked(run: str, cause: str, lacking: str, *, seconds: float | None = None) -> Blocked:
    return Blocked(
        cause=cause, run_id=run, step_id="export", since=AT, seconds=seconds, lacking=lacking
    )


@dataclass
class Intake:
    """The project's own instance: its owner, its repository and its intake on HTTP."""

    given: OwnerChannel
    channel: Channel
    intake: FindingsIntake
    app: FastAPI

    def transport(self) -> httpx.ASGITransport:
        return httpx.ASGITransport(app=self.app)

    async def post(self, document: dict[str, str]) -> httpx.Response:
        async with httpx.AsyncClient(transport=self.transport(), base_url="http://p.test") as h:
            return await h.post("/findings/intake", json=document)

    async def confirm(self, key: str) -> None:
        """The owner answers the sender's report that it is done, and confirms the reading."""
        report = await self.given.owner.queries.one(TENANT, report_of(key))
        assert report is not None, "the owner was asked"
        await self.given.answer(report, "erledigt", event=f"{report.id}-1")
        await self.given.answer(report, "ja", event=f"{report.id}-2")

    async def received(self) -> list[str]:
        async with self.given.persistence.transaction(TENANT):
            entries = await self.given.identity.ledger.of_kinds(TENANT, {RECEIVED})
        return [str(e.outcome) for e in entries]


@dataclass
class _Surface:
    findings_intake: FindingsIntake | None


async def project(*, rate: int = 30, pending_max: int = 5) -> Intake:
    given = owner_channel()
    await given.configure()
    channel = Channel()
    intake = FindingsIntake(
        channel,
        Ed25519Signatures(),
        Taking(
            given.identity.ledger,
            MemoryObjectStore(),
            given.persistence,
            given.owner.queries,
            given.owner.raising,
            given.clock,
        ),
        IntakeOptions(tenant=TENANT, rate=rate, pending_max=pending_max),
    )
    app = FastAPI()
    app.include_router(route.router(_Surface(intake)))  # type: ignore[arg-type]
    return Intake(given, channel, intake, app)


@dataclass
class Customer:
    """An instance outside the project: its blocks, its owner and its findings."""

    given: OwnerChannel
    source: Source
    findings: ProductFindings

    async def key(self) -> str:
        return Ed25519Signatures().public((await self.findings.pseudonyms(TENANT)).signing)


async def customer(
    to: Intake, *blocks: Blocked, level: str = "automatic", content: Content | None = None
) -> Customer:
    given = owner_channel()
    await given.configure()
    source = Source(list(blocks))
    sending = Sending(
        IntakeClient(URL, transport=to.transport()),
        URL,
        level="review" if level == "review" else "automatic",
        signatures=Ed25519Signatures(),
    )
    findings = ProductFindings(
        source,
        Kept(
            given.identity.ledger,
            MemoryObjectStore(),
            given.persistence,
            Randomness(),
            content or Content(),
        ),
        sending,
        shipped=load_shipped(),
    )
    return Customer(given, source, findings)


async def admitted(to: Intake, sender: Customer) -> None:
    """The sender's first contact, held, and the owner's confirmation."""
    assert (await sender.findings.send(TENANT)).held == 1
    await to.confirm(await sender.key())


# --- what leaves: only a lack the product does not ship -----------------------------------------


async def test_only_a_lack_the_product_does_not_ship_reaches_the_intake() -> None:
    """One lack nothing shipped offers, one a shipped connector left unconfigured, one of a
    connector of the customer's own: the first is a product candidate and reaches the intake;
    the other two reach the customer's own channel and never the intake."""
    to = await project()
    sender = await customer(
        to,
        blocked("run_1", "no_connector", "repository.wiki"),
        blocked("run_2", "no_connector", "knowledge.pages"),
        blocked("run_3", "operation_unsupported", "crm.contacts.merge"),
    )
    kinds = {f.lack.lacking: c.kind for f, c in await sender.findings.classified(TENANT)}
    assert kinds == {
        "repository.wiki": "product",
        "knowledge.pages": "configuration",
        "crm.contacts.merge": "own",
    }

    await admitted(to, sender)
    assert await sender.findings.send(TENANT) == Sent(opened=1)
    (issue,) = to.channel.issues.values()
    assert "repository.wiki" in issue.texts[0]
    text = to.channel.every_text()
    assert "knowledge.pages" not in text and "crm.contacts" not in text
    assert await to.received() == ["opened"], "nothing local reached the intake"

    said = alerts(
        sender.given.identity.ledger,
        sender.given.persistence,
        MemoryBackupLog(sender.given.persistence),
        MemoryTenantStore(sender.given.persistence),
        sender.given.owner,
        sender.given.clock,
        backup_expected_hours=None,
        findings=sender.findings,
    )
    reported = await said.report(TENANT)
    assert reported.raised == 2 and reported.delivered == 2
    messages = [s.text for s in sender.given.deliveries.said]
    configuration = next(m for m in messages if "knowledge.pages" in m)
    assert "`bookstack`" in configuration and "TAKTUS_CONNECTORS" in configuration
    own = next(m for m in messages if "crm.contacts.merge" in m)
    assert "own development" in own and "taktusctl findings report" in own
    assert not any("repository.wiki" in m for m in messages), "a candidate is no alert"


# --- the levels --------------------------------------------------------------------------------


async def test_off_sends_nothing() -> None:
    to = await project()
    given = owner_channel()
    off = ProductFindings(
        Source([blocked("run_1", "no_connector", "repository.wiki")]),
        Kept(
            given.identity.ledger, MemoryObjectStore(), given.persistence, Randomness(), Content()
        ),
        None,
        shipped=load_shipped(),
    )
    assert off.level == "off" and await off.send(TENANT) == Sent()
    assert await off.pending(TENANT) == ()
    assert to.channel.issues == {} and await to.received() == []


async def test_review_sends_only_on_a_persons_yes_and_remembers_local_for_us() -> None:
    to = await project()
    sender = await customer(
        to,
        blocked("run_1", "no_connector", "repository.wiki"),
        blocked("run_2", "no_worker", "code.review"),
        level="review",
    )
    assert await sender.findings.send(TENANT) == Sent(), "the scheduler sends nothing"
    assert await to.received() == [] and to.given.deliveries.said == []

    pending = await sender.findings.pending(TENANT)
    assert [p.finding.lack.lacking for p in pending] == ["repository.wiki", "code.review"]
    wiki, review = pending
    assert wiki.text.startswith("Product finding:"), "shown with the text that would leave"

    held = await sender.findings.send_one(TENANT, wiki.finding.lack.key)
    assert held.held == 1, "the person's yes reaches the intake, which holds a new sender"
    await to.confirm(await sender.key())
    assert await sender.findings.send_one(TENANT, wiki.finding.lack.key) == Sent(opened=1)

    await sender.findings.call_local(TENANT, review.finding.lack.key)
    assert [p.finding.lack.lacking for p in await sender.findings.pending(TENANT)] == []
    (again,) = [
        o for o in await sender.findings.outgoing(TENANT) if o.finding.lack.lacking == "code.review"
    ]
    assert again.local_for_us and not again.leaves, "remembered for that lack"
    assert len(to.channel.issues) == 1


async def test_automatic_sends_rule_classified_lacks_and_never_a_report_by_hand() -> None:
    to = await project()
    sender = await customer(to, blocked("run_1", "no_connector", "repository.wiki"))
    await admitted(to, sender)
    report = await sender.findings.by_hand(TENANT, "Export fails", "The export fails twice.")
    assert report.withheld == ()

    assert await sender.findings.send(TENANT) == Sent(opened=1)
    assert await sender.findings.send(TENANT) == Sent(), "nothing twice"
    assert ["Export fails" not in t for t in to.channel.titles.values()] == [True]

    # Only the person's confirmation sends it, as the command asks for it at every level.
    assert await sender.findings.send_by_hand(TENANT, report) == "opened"
    assert "Export fails" in to.channel.titles.values()
    assert await to.received() == ["opened", "opened"]


# --- the intake ---------------------------------------------------------------------------------


def signed(seed: bytes, submission: Submission) -> dict[str, str]:
    signatures = Ed25519Signatures()
    payload = payload_of(submission)
    return {
        "key": signatures.public(seed),
        "payload": payload.decode(),
        "signature": signatures.sign(seed, payload),
    }


def submission_of(source: str, lacking: str = "repository.wiki", minute: int = 0) -> Submission:
    return Submission.model_validate(
        {
            "source": source,
            "lack": {"cause": "no_connector", "lacking": lacking},
            "occurrence": {
                "run_id": "r-" + "0" * 15 + str(minute % 10),
                "step_id": "s-" + "0" * 12,
                "since": (AT + timedelta(minutes=minute)).isoformat(),
                "source": source,
            },
        }
    )


async def test_the_intake_refuses_a_forged_finding_and_holds_a_new_sender_until_confirmed() -> None:
    to = await project()
    seed, other = b"a" * 32, b"b" * 32
    source = "src_" + "1" * 20
    document = signed(seed, submission_of(source))

    forged = {**document, "signature": signed(other, submission_of(source))["signature"]}
    answered = await to.post(forged)
    assert answered.status_code == 401 and answered.json()["answer"] == "forged"
    unsigned = await to.post({"key": document["key"], "payload": document["payload"]})
    assert unsigned.status_code == 422, "no signature, no submission"
    changed = {**document, "payload": document["payload"].replace("wiki", "wika")}
    assert (await to.post(changed)).json()["answer"] == "forged"
    assert to.given.deliveries.said == [] and await to.received() == []

    held = await to.post(document)
    assert held.status_code == 202 and held.json()["answer"] == "held"
    (asked,) = to.given.deliveries.said
    assert source in asked.text, "the owner is asked, in the owner's channel"
    assert (await to.post(document)).json()["answer"] == "held"
    assert len(to.given.deliveries.said) == 1, "asked once"
    assert to.channel.issues == {}

    await to.confirm(Ed25519Signatures().public(seed))
    opened = await to.post(document)
    assert opened.status_code == 201 and opened.json()["answer"] == "opened"
    again = await to.post(document)
    assert again.status_code == 200 and again.json()["answer"] == "known"
    assert len(to.channel.issues) == 1

    impostor = signed(other, submission_of(source))
    assert (await to.post(impostor)).json()["answer"] == "refused"


async def test_a_sender_over_its_rate_is_refused() -> None:
    to = await project(rate=2)
    seed, source = b"c" * 32, "src_" + "2" * 20
    assert (await to.post(signed(seed, submission_of(source, minute=0)))).json()["answer"] == (
        "held"
    )
    await to.confirm(Ed25519Signatures().public(seed))
    answers = [
        (await to.post(signed(seed, submission_of(source, minute=m)))).json()["answer"]
        for m in (1, 2, 3)
    ]
    assert answers == ["opened", "added", "limited"]
    limited = await to.post(signed(seed, submission_of(source, minute=4)))
    assert limited.status_code == 429


async def test_new_senders_waiting_for_the_owner_are_limited() -> None:
    """Made-up keys cannot fill the owner's channel."""
    to = await project(pending_max=2)
    answers = [
        (await to.post(signed(bytes([n]) * 32, submission_of(f"src_{n:020d}")))).json()["answer"]
        for n in (1, 2, 3)
    ]
    assert answers == ["held", "held", "limited"]
    assert len(to.given.deliveries.said) == 2


async def test_the_same_lack_from_another_sender_adds_an_occurrence() -> None:
    to = await project()
    first = await customer(to, blocked("run_1", "no_connector", "repository.wiki", seconds=60))
    second = await customer(to, blocked("run_9", "no_connector", "repository.wiki", seconds=30))
    await admitted(to, first)
    await admitted(to, second)
    assert await first.findings.send(TENANT) == Sent(opened=1)
    assert await second.findings.send(TENANT) == Sent(added=1)
    (issue,) = to.channel.issues.values()
    sources = {r.source for r in texts.reported(issue.texts)}
    one = (await first.findings.pseudonyms(TENANT)).source
    other = (await second.findings.pseudonyms(TENANT)).source
    assert sources == {one, other}
    assert "In all: 2 occurrences from 2 senders" in issue.texts[1]


async def test_nothing_of_the_tenant_leaves_through_the_intake() -> None:
    """#446's rule holds on the way to the intake: a name, an amount and an address planted in
    the tenant reach no submission and no issue."""
    planted = ["Erika Mustermann", "4.711,00 EUR", "Heidestraße 17, 51147 Köln"]
    to = await project()
    sender = await customer(
        to,
        blocked("run_erika", "no_connector", "repository.wiki"),
        blocked("run_2", "no_connector", "repository.erika-mustermann"),
        content=Content(planted),
    )
    await admitted(to, sender)
    assert await sender.findings.send(TENANT) == Sent(opened=1, withheld=1)
    leaky = await sender.findings.by_hand(
        TENANT, "Export fails", "The export for Erika Mustermann, 4.711,00 EUR, fails."
    )
    assert leaky.withheld, "a report is checked by the same rule"
    text = to.channel.every_text().lower()
    for value in [*planted, "erika", "run_erika", "mustermann", "51147"]:
        assert value.lower() not in text, value
    async with to.given.persistence.transaction(TENANT):
        entries = await to.given.identity.ledger.of_kinds(TENANT, {RECEIVED})
    assert all("erika" not in json.dumps(e.model_dump(mode="json")).lower() for e in entries)
