"""The product finding (UC-6.12, ADR-0046, ADR-0112): what an instance met that the product
lacks, shown to its operator and sent where the operator enabled it, and a report a person
writes by hand.

`findings` is the view on the instance: the rule over the tenant's blocks, every lack with its
occurrences, by the instance's own identifiers. It is computed from the blocked-time accounts
each time it is read, so there is nothing to keep in step with them.

`outgoing` is each finding as it would leave: its run and its step by pseudonym, its sender
named, and what, if anything, withholds it (ADR-0112 §2 to §4). It is what the operator is shown
and can send by hand (`taktusctl findings`).

`send` sends what the channel does not hold yet. A lack the channel holds an open finding for is
added to it — one more occurrence, the waiting summed — and a lack it holds none open for opens
one. The channel is shared by every instance that sends to it, so one lack is one finding across
instances. An occurrence the channel holds is never sent again, so a restart, or a second
instance, sends nothing twice. A finding whose own parts carry a value of the tenant is not sent
at all. Every text sent is recorded in the tenant's ledger as `finding.sent`, with the run and the
step it is about and the text's digest, as every other outward effect is.

Whether the instance sends is its operator's one setting. The tenant's ledger records each
change of it, before anything is sent: `finding.enabled` with the digest of what the operator
set, and `finding.disabled` (ADR-0112 §1).

`by_hand` prepares a report a person wrote: their text, checked by the same rule a finding is,
with the sender below. `send_by_hand` sends it, once the person has seen what will be sent and
confirmed it (ADR-0008); the driving adapter shows and asks.

**What leaves, and how (ADR-0118).** A rule over the list of what the release ships classifies
every lack (`domain/service/findings.py`, `classify`). Only a *product candidate* may leave. A
local lack reaches the tenant's own owner-facing channel through its alerts, and never the
channel or the intake here. The operator's level says how a candidate leaves. `off` sends
nothing. `review` sends one only when a person said yes to its text (`send_one`), and a lack a
person called "local for us" is remembered (`call_local`) and never offered again. `automatic`
lets the scheduler send every candidate the rule raised. A report by hand is always shown and
confirmed first, at every level that sends.

A candidate goes either through a channel to the repository, as before, or to the intake of
another instance (`FindingIntake`). To an intake it goes one occurrence at a time, signed with
the sender's key. The ledger's `finding.submitted` entries are what was submitted: the intake
holds the repository's state, this instance only what it handed over.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from taktus.components.reporting.domain.model import (
    Classified,
    Finding,
    FindingsLevel,
    Lack,
    Occurrence,
    Reported,
    Shipped,
    Submission,
)
from taktus.components.reporting.domain.model.finding import short
from taktus.components.reporting.domain.service import findings as rule
from taktus.components.reporting.domain.service import leaving, texts
from taktus.components.reporting.domain.service.findings import State
from taktus.components.reporting.domain.service.leaving import Match
from taktus.components.reporting.domain.service.pseudonyms import KEY_BYTES, Pseudonyms
from taktus.components.reporting.ports import (
    Blocks,
    FindingChannel,
    FindingIntake,
    SecretValues,
    Signatures,
    Signed,
    TenantContent,
)
from taktus.ports.clock import Randomness
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Tenant, UnitOfWork
from taktus.shared.v1 import Digest, LedgerRefs

SENT = "finding.sent"
"""The ledger entry of a text sent to the channel: `opened` or `added` as its outcome."""
SOURCE = "finding.source"
"""The ledger entry of the tenant's sender: the digest of the key its pseudonyms are drawn
under. The first one whose key is readable holds."""
ENABLED = "finding.enabled"
"""The operator enabled sending: the digest of the connector's address they set."""
DISABLED = "finding.disabled"
"""The operator no longer enables sending."""
REPORTED = "finding.reported"
"""A report by hand, sent: the digest of its text."""
SUBMITTED = "finding.submitted"
"""An occurrence submitted to an intake: the digest of the payload, the intake's answer as its
outcome (ADR-0118)."""
LOCAL = "finding.local"
"""A person called a candidate "local for us" in review: the digest of the lack's key."""
ACCEPTED = frozenset({"opened", "added", "known"})
CANDIDATE = Classified(kind="product")
"""The intake's answers after which an occurrence is never submitted again."""


@dataclass(frozen=True)
class Sent:
    """What one `send` did: findings opened, additions made, and findings withheld because
    their own parts carry a value of the tenant. Zero, zero and zero when there was nothing
    new, or no channel."""

    opened: int = 0
    added: int = 0
    withheld: int = 0
    held: int = 0
    """Submissions an intake did not take: it holds this sender until its owner confirms it,
    refuses it, or limits it. Tried again at the next interval."""


@dataclass(frozen=True)
class Kept:
    """Where the findings are kept on the instance: the tenant's ledger and objects, the
    randomness a sender's key is drawn from, and what must not leave."""

    ledger: Ledger
    objects: ObjectStore
    work: UnitOfWork
    randomness: Randomness
    content: TenantContent
    secrets: SecretValues | None = None


@dataclass(frozen=True)
class Sending:
    """Where findings go, on an instance whose operator enabled it. `address` is what the
    operator set to enable it — the connector's or the intake's address — and its digest is what
    the ledger records. `channel` is a channel to the repository or an intake of another
    instance. `level` is the operator's: `review` or `automatic`; `off` builds no `Sending`."""

    channel: FindingChannel | FindingIntake
    address: str
    level: FindingsLevel = "automatic"
    signatures: Signatures | None = None
    """What signs a submission to an intake; needed with an intake only."""


@dataclass(frozen=True)
class Outgoing:
    """A finding as it would leave the instance: as the instance knows it, as it is sent, in
    the words it is sent in, and what withholds it — nothing, where it may leave."""

    finding: Finding
    sent_as: Finding
    text: str
    withheld: tuple[Match, ...]
    classified: Classified = CANDIDATE
    local_for_us: bool = False
    """A person called it local in review: it is never offered again."""

    @property
    def leaves(self) -> bool:
        """Whether it may leave: a product candidate, not called local, not withheld."""
        return not self.classified.local and not self.local_for_us and not self.withheld


@dataclass(frozen=True)
class ByHand:
    """A report a person wrote, as it would leave: the title and the body sent, and what
    withholds it. `run_id` is the run they reported it from, by the instance's own identifier;
    it is not sent."""

    title: str
    body: str
    withheld: tuple[Match, ...]
    run_id: str | None = None


class Withheld(Exception):
    """A report that carries what may not leave is not sent."""


class NotEnabled(Exception):
    """This instance's operator did not enable sending: a report is sent by hand."""


class NotACandidate(Exception):
    """The lack is local, called local, withheld or unknown: it never leaves."""


class NotTaken(Exception):
    """The intake did not take a report by hand: the message says what it answered."""


def digest_of(content: bytes) -> str:
    """The object store's digest of these bytes: `sha256:` over exactly them (`ObjectStore`)."""
    return "sha256:" + hashlib.sha256(content).hexdigest()


def payload_of(submission: Submission) -> bytes:
    """The bytes a submission is signed as: the same submission, the same bytes."""
    document = submission.model_dump(mode="json", exclude_none=True)
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class Delivered:
    """One text a channel was given: the occurrence as it left, and what became of it."""

    occurrence: Occurrence
    outcome: str
    text: str


async def deliver(
    channel: FindingChannel,
    tenant: Tenant,
    found: Sequence[Finding],
    shape: str | None,
) -> list[Delivered]:
    """Give the channel what it does not hold yet of findings already fit to leave. A lack it
    holds an open finding for is added to it, and one it holds none open for opens one. An
    occurrence whose finding was closed while it lasted is not sent. The instance that sends its
    own findings calls this, and so does an intake for a sender's."""
    held = await channel.held(tenant)
    everywhere: dict[str, list[Reported]] = defaultdict(list)
    open_finding: dict[str, tuple[str, dict[str, Reported]]] = {}
    for one in held:
        marks = texts.reported(one.texts)
        for each in marks:
            everywhere[each.lack].append(each)
        if one.open and marks and marks[0].lack not in open_finding:
            open_finding[marks[0].lack] = (one.reference, texts.latest(marks))
    done: list[Delivered] = []
    for finding in found:
        lack = finding.lack
        known = texts.latest(everywhere.get(lack.key, ()))
        reference, in_issue = open_finding.get(lack.key, (None, {}))
        sends = [
            (occurrence, state)
            for occurrence, state in rule.to_send(finding, known)
            # One whose finding was closed while it lasted: the product took it up.
            if not (occurrence.id in known and occurrence.id not in in_issue)
        ]
        for occurrence, state in sends:
            key = key_of(lack, occurrence, state)
            if reference is None:
                text = texts.opening(lack, occurrence, state, shape)
                reference = await channel.open(tenant, texts.title(lack), text, key=key)
                outcome = "opened"
            else:
                text = texts.addition(lack, occurrence, state, in_issue)
                await channel.add(tenant, reference, text, key=key)
                outcome = "added"
            in_issue[occurrence.id] = Reported(
                lack=lack.key,
                occurrence=occurrence.id,
                state=state,
                seconds=occurrence.seconds,
                source=occurrence.source,
            )
            done.append(Delivered(occurrence=occurrence, outcome=outcome, text=text))
    return done


def key_of(lack: Lack, occurrence: Occurrence, state: State) -> str:
    """The idempotency key of one text: the lack, the occurrence and its state. Derived, never
    stored, so a repeat after a restart carries the same key."""
    return f"taktus:finding:{lack.key}:{occurrence.id}:{state}"


class ProductFindings:
    def __init__(
        self,
        blocks: Blocks,
        kept: Kept,
        sending: Sending | None = None,
        *,
        shape: str | None = None,
        shipped: Shipped | None = None,
    ) -> None:
        """`shape` is the form a finding's issue takes, as its operator configured it
        (`texts.form`); None, the product's plain shape. `shipped` is the release's list of
        what it ships, which every lack is classified against (ADR-0118). None counts every
        lack as a product candidate, as an instance did before the list existed."""
        self._blocks = blocks
        self._kept = kept
        self._sending = sending
        self._shape = shape
        self._shipped = shipped
        self._settled: dict[Tenant, tuple[Digest | None, FindingsLevel]] = {}
        """What this process last recorded or read of the setting, by tenant."""

    @property
    def enabled(self) -> bool:
        """Whether this instance sends its findings, or only records and shows them."""
        return self._sending is not None

    @property
    def level(self) -> FindingsLevel:
        """The operator's level: `off` where nothing is sent."""
        return "off" if self._sending is None else self._sending.level

    def classify(self, lack: Lack) -> Classified:
        """What the lack is, against the release's list."""
        if self._shipped is None:
            return Classified(kind="product")
        return rule.classify(lack, self._shipped)

    async def classified(self, tenant: Tenant) -> tuple[tuple[Finding, Classified], ...]:
        """Every finding of the tenant with what it is, by the instance's own identifiers."""
        return tuple((f, self.classify(f.lack)) for f in await self.findings(tenant))

    async def called_local(self, tenant: Tenant) -> frozenset[str]:
        """The keys of the lacks a person called "local for us" in review."""
        kept = self._kept
        async with kept.work.transaction(tenant):
            entries = await kept.ledger.of_kinds(tenant, {LOCAL})
        keys: set[str] = set()
        for entry in entries:
            if entry.content_digest is not None:
                stored = await kept.objects.get(entry.content_digest)
                if stored is not None:
                    keys.add(stored.decode("utf-8"))
        return frozenset(keys)

    async def call_local(self, tenant: Tenant, lack_key: str) -> None:
        """A person said in review that the lack is local for them. It is remembered in the
        tenant's ledger and never offered again."""
        if lack_key in await self.called_local(tenant):
            return
        kept = self._kept
        digest = await kept.objects.put(lack_key.encode("utf-8"))
        async with kept.work.transaction(tenant):
            await kept.ledger.record(
                tenant,
                Fact(
                    kind=LOCAL,
                    refs=LedgerRefs(tenant=tenant),
                    outcome="local",
                    content_digest=digest,
                ),
            )

    async def findings(self, tenant: Tenant) -> tuple[Finding, ...]:
        """Every lack the tenant's blocks were for, each with its occurrences."""
        return rule.findings(await self._blocks.blocks(tenant))

    async def pseudonyms(self, tenant: Tenant) -> Pseudonyms:
        """The tenant's sender: drawn and recorded the first time it is needed."""
        kept = self._kept
        async with kept.work.transaction(tenant):
            drawn = await kept.ledger.of_kinds(tenant, {SOURCE})
        for entry in drawn:
            if entry.content_digest is None:
                continue
            stored = await kept.objects.get(entry.content_digest)
            if stored is not None:
                return Pseudonyms(bytes.fromhex(json.loads(stored)["key"]))
        key = kept.randomness.token(KEY_BYTES)
        digest = await kept.objects.put(json.dumps({"key": key}).encode("utf-8"))
        async with kept.work.transaction(tenant):
            await kept.ledger.record(
                tenant,
                Fact(
                    kind=SOURCE,
                    refs=LedgerRefs(tenant=tenant),
                    outcome="drawn",
                    content_digest=digest,
                ),
            )
        return await self.pseudonyms(tenant)

    async def settle(self, tenant: Tenant) -> None:
        """Record a change of the operator's setting in the tenant's ledger: `finding.enabled`
        when sending is enabled and the last entry does not say so for the same address,
        `finding.disabled` when it is not and the last entry says it was. Nothing where nothing
        changed, and nothing on an instance that never enabled it."""
        kept = self._kept
        want: Digest | None = None
        if self._sending is not None:
            want = await kept.objects.put(self._sending.address.encode("utf-8"))
        level = self.level
        if tenant in self._settled and self._settled[tenant] == (want, level):
            return
        async with kept.work.transaction(tenant):
            entries = await kept.ledger.of_kinds(tenant, {ENABLED, DISABLED})
            last = entries[-1] if entries else None
            was: tuple[Digest | None, str | None] = (
                (last.content_digest, last.outcome)
                if last is not None and last.kind == ENABLED
                else (None, "off")
            )
            if (want, level) != was:
                await kept.ledger.record(
                    tenant,
                    Fact(
                        kind=ENABLED if want is not None else DISABLED,
                        refs=LedgerRefs(tenant=tenant),
                        adapter=None if self._sending is None else self._sending.channel.name,
                        # The level the operator set: `review` or `automatic`.
                        outcome=level if want is not None else "disabled",
                        content_digest=want,
                    ),
                )
        self._settled[tenant] = (want, level)

    async def outgoing(self, tenant: Tenant) -> tuple[Outgoing, ...]:
        """Every finding as it would leave, with what withholds it."""
        found = await self.findings(tenant)
        if not found:
            return ()
        pseudonyms = await self.pseudonyms(tenant)
        values = await self._values(tenant)
        local = await self.called_local(tenant)
        return tuple(
            Outgoing(
                finding=finding,
                sent_as=(sent := pseudonyms.finding(finding)),
                text=texts.shown(sent, self._shape),
                withheld=self._check(self._parts(finding.lack), values),
                classified=self.classify(finding.lack),
                local_for_us=finding.lack.key in local,
            )
            for finding in found
        )

    async def pending(self, tenant: Tenant) -> tuple[Outgoing, ...]:
        """Every candidate that may leave and holds something the other side has not been
        given: what a person reviews. Nothing where sending is not enabled."""
        if self._sending is None:
            return ()
        chosen = [one for one in await self.outgoing(tenant) if one.leaves]
        if not chosen:
            return ()
        waiting = await self._unsent(tenant, [one.finding for one in chosen])
        return tuple(one for one in chosen if waiting.get(one.finding.lack.key))

    async def send_one(self, tenant: Tenant, lack_key: str) -> Sent:
        """Send one candidate a person said yes to in review: what the other side has not
        been given of it. A local lack, one called local and one withheld never leave."""
        if self._sending is None:
            raise NotEnabled("this instance does not send to the product")
        await self.settle(tenant)
        chosen = [o for o in await self.outgoing(tenant) if o.finding.lack.key == lack_key]
        if not chosen or not chosen[0].leaves:
            raise NotACandidate(f"the lack {lack_key} does not leave this instance")
        return await self._send(tenant, [chosen[0].finding])

    async def send(self, tenant: Tenant) -> Sent:
        """Send what the other side does not hold yet of every candidate the rule raised.
        Nothing where sending is not enabled, or where a person reviews each one."""
        await self.settle(tenant)
        if self._sending is None or self._sending.level != "automatic":
            return Sent()
        found = await self.findings(tenant)
        if not found:
            return Sent()
        local = await self.called_local(tenant)
        chosen = [f for f in found if not self.classify(f.lack).local and f.lack.key not in local]
        return await self._send(tenant, chosen)

    def _enabled(self) -> Sending:
        if self._sending is None:
            raise NotEnabled("this instance does not send to the product")
        return self._sending

    async def _send(self, tenant: Tenant, chosen: Sequence[Finding]) -> Sent:
        sending = self._enabled()
        if not chosen:
            return Sent()
        pseudonyms = await self.pseudonyms(tenant)
        values = await self._values(tenant)
        fit: list[Finding] = []
        withheld = 0
        for local in chosen:
            if self._check(self._parts(local.lack), values):
                withheld += 1
            else:
                fit.append(local)
        channel = sending.channel
        if isinstance(channel, FindingIntake):
            sent = await self._submit(tenant, channel, pseudonyms, fit)
            return Sent(opened=sent.opened, added=sent.added, withheld=withheld, held=sent.held)
        on_instance = {pseudonyms.occurrence(o).id: o for local in fit for o in local.occurrences}
        opened = added = 0
        sent_as = [pseudonyms.finding(local) for local in fit]
        for done in await deliver(channel, tenant, sent_as, self._shape):
            opened += done.outcome == "opened"
            added += done.outcome == "added"
            mine = on_instance[done.occurrence.id]
            await self._record(tenant, SENT, mine.run_id, mine.step_id, done.outcome, done.text)
        return Sent(opened=opened, added=added, withheld=withheld)

    async def _submitted(self, tenant: Tenant) -> frozenset[str]:
        """The digests of every payload an intake took."""
        kept = self._kept
        async with kept.work.transaction(tenant):
            entries = await kept.ledger.of_kinds(tenant, {SUBMITTED})
        return frozenset(
            e.content_digest
            for e in entries
            if e.content_digest is not None and e.outcome in ACCEPTED
        )

    @staticmethod
    def _submissions(pseudonyms: Pseudonyms, local: Finding) -> list[tuple[Occurrence, Submission]]:
        """Each occurrence of the finding on the instance, with the submission it leaves as."""
        return [
            (
                mine,
                Submission(
                    source=pseudonyms.source,
                    lack=local.lack,
                    occurrence=pseudonyms.occurrence(mine),
                ),
            )
            for mine in local.occurrences
        ]

    async def _unsent(self, tenant: Tenant, local: Sequence[Finding]) -> dict[str, int]:
        """By lack, how many texts the other side has not been given."""
        channel = self._enabled().channel
        pseudonyms = await self.pseudonyms(tenant)
        if isinstance(channel, FindingIntake):
            given = await self._submitted(tenant)
            return {
                f.lack.key: sum(
                    digest_of(payload_of(s)) not in given
                    for _, s in self._submissions(pseudonyms, f)
                )
                for f in local
            }
        everywhere: dict[str, list[Reported]] = defaultdict(list)
        for one in await channel.held(tenant):
            for each in texts.reported(one.texts):
                everywhere[each.lack].append(each)
        return {
            f.lack.key: len(
                rule.to_send(pseudonyms.finding(f), texts.latest(everywhere.get(f.lack.key, ())))
            )
            for f in local
        }

    async def _submit(
        self,
        tenant: Tenant,
        intake: FindingIntake,
        pseudonyms: Pseudonyms,
        fit: Sequence[Finding],
    ) -> Sent:
        """Hand every occurrence the intake has not taken to it, signed. An answer that does
        not take it ends the round: the next ones would be answered the same."""
        signatures = self._signatures()
        seed = pseudonyms.signing
        key = signatures.public(seed)
        given = await self._submitted(tenant)
        opened = added = 0
        for local in fit:
            for mine, submission in self._submissions(pseudonyms, local):
                payload = payload_of(submission)
                if digest_of(payload) in given:
                    continue
                answer = await intake.submit(
                    Signed(
                        key=key,
                        payload=payload.decode("utf-8"),
                        signature=signatures.sign(seed, payload),
                    )
                )
                if answer not in ACCEPTED:
                    return Sent(opened=opened, added=added, held=1)
                opened += answer == "opened"
                added += answer == "added"
                await self._record_bytes(
                    tenant, SUBMITTED, mine.run_id, mine.step_id, answer, payload
                )
        return Sent(opened=opened, added=added)

    def _signatures(self) -> Signatures:
        signatures = self._enabled().signatures
        if signatures is None:
            raise NotEnabled("an intake needs a signature scheme to submit to")
        return signatures

    async def by_hand(
        self, tenant: Tenant, title: str, text: str, *, run_id: str | None = None
    ) -> ByHand:
        """A report a person wrote, as it would leave, checked by the rule a finding is."""
        pseudonyms = await self.pseudonyms(tenant)
        body = texts.by_hand(
            text, pseudonyms.source, None if run_id is None else pseudonyms.run(run_id)
        )
        withheld = self._check((title, text), await self._values(tenant))
        if not title.strip() or not text.strip():
            withheld = (*withheld, Match(kind="empty", excerpt="a report has a title and a text"))
        return ByHand(title=title.strip(), body=body, withheld=withheld, run_id=run_id)

    async def send_by_hand(self, tenant: Tenant, report: ByHand) -> str:
        """Send a report the person has seen and confirmed; its reference in the channel. The
        same report again opens nothing new."""
        if report.withheld:
            raise Withheld(f"the report carries {len(report.withheld)} thing(s) that may not leave")
        if self._sending is None:
            raise NotEnabled("this instance does not send to the product; send it by hand")
        await self.settle(tenant)
        channel = self._sending.channel
        if isinstance(channel, FindingIntake):
            signatures = self._signatures()
            pseudonyms = await self.pseudonyms(tenant)
            payload = payload_of(
                Submission(source=pseudonyms.source, title=report.title, body=report.body)
            )
            answer = await channel.submit(
                Signed(
                    key=signatures.public(pseudonyms.signing),
                    payload=payload.decode("utf-8"),
                    signature=signatures.sign(pseudonyms.signing, payload),
                )
            )
            if answer not in ACCEPTED:
                raise NotTaken(f"the intake answered `{answer}`; nothing was opened")
            await self._record(tenant, REPORTED, report.run_id, None, answer, report.body)
            return answer
        key = f"taktus:report:{short(report.title + chr(10) + report.body)}"
        reference = await channel.open(tenant, report.title, report.body, key=key)
        await self._record(tenant, REPORTED, report.run_id, None, "opened", report.body)
        return reference

    def _parts(self, lack: Lack) -> tuple[str, ...]:
        """The parts of a finding that came from the instance: what was lacking, and the
        operator's form. Everything else is the product's own sentences, closed values and
        pseudonyms."""
        return (lack.lacking, *(() if self._shape is None else (self._shape,)))

    def _check(self, parts: tuple[str, ...], values: frozenset[str]) -> tuple[Match, ...]:
        found = list(leaving.check(parts, values))
        secrets = self._kept.secrets
        if secrets is not None and any(secrets.carried_by(part) for part in parts):
            found.append(Match(kind="secret", excerpt="a secret value this instance holds"))
        return tuple(found)

    async def _values(self, tenant: Tenant) -> frozenset[str]:
        return leaving.values(await self._kept.content.values(tenant))

    async def _record(
        self,
        tenant: Tenant,
        kind: str,
        run_id: str | None,
        step_id: str | None,
        outcome: str,
        text: str,
    ) -> None:
        await self._record_bytes(tenant, kind, run_id, step_id, outcome, text.encode("utf-8"))

    async def _record_bytes(
        self,
        tenant: Tenant,
        kind: str,
        run_id: str | None,
        step_id: str | None,
        outcome: str,
        content: bytes,
    ) -> None:
        kept = self._kept
        sending = self._sending
        digest = await kept.objects.put(content)
        refs = (
            LedgerRefs(run_id=run_id, step_id=step_id)
            if run_id is not None
            else LedgerRefs(tenant=tenant)
        )
        async with kept.work.transaction(tenant):
            await kept.ledger.record(
                tenant,
                Fact(
                    kind=kind,
                    refs=refs,
                    adapter=None if sending is None else sending.channel.name,
                    outcome=outcome,
                    content_digest=digest,
                ),
            )
