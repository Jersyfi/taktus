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
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass

from taktus.components.reporting.domain.model import Finding, Lack, Occurrence, Reported
from taktus.components.reporting.domain.model.finding import short
from taktus.components.reporting.domain.service import findings as rule
from taktus.components.reporting.domain.service import leaving, texts
from taktus.components.reporting.domain.service.findings import State
from taktus.components.reporting.domain.service.leaving import Match
from taktus.components.reporting.domain.service.pseudonyms import KEY_BYTES, Pseudonyms
from taktus.components.reporting.ports import (
    Blocks,
    FindingChannel,
    SecretValues,
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


@dataclass(frozen=True)
class Sent:
    """What one `send` did: findings opened, additions made, and findings withheld because
    their own parts carry a value of the tenant. Zero, zero and zero when there was nothing
    new, or no channel."""

    opened: int = 0
    added: int = 0
    withheld: int = 0


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
    operator set to enable it — the connector's address — and its digest is what the ledger
    records."""

    channel: FindingChannel
    address: str


@dataclass(frozen=True)
class Outgoing:
    """A finding as it would leave the instance: as the instance knows it, as it is sent, in
    the words it is sent in, and what withholds it — nothing, where it may leave."""

    finding: Finding
    sent_as: Finding
    text: str
    withheld: tuple[Match, ...]


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
    ) -> None:
        """`shape` is the form a finding's issue takes, as its operator configured it
        (`texts.form`); None, the product's plain shape."""
        self._blocks = blocks
        self._kept = kept
        self._sending = sending
        self._shape = shape
        self._settled: dict[Tenant, Digest | None] = {}
        """What this process last recorded or read of the setting, by tenant."""

    @property
    def enabled(self) -> bool:
        """Whether this instance sends its findings, or only records and shows them."""
        return self._sending is not None

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
        if tenant in self._settled and self._settled[tenant] == want:
            return
        async with kept.work.transaction(tenant):
            entries = await kept.ledger.of_kinds(tenant, {ENABLED, DISABLED})
            last = entries[-1] if entries else None
            was = last.content_digest if last is not None and last.kind == ENABLED else None
            if want != was:
                await kept.ledger.record(
                    tenant,
                    Fact(
                        kind=ENABLED if want is not None else DISABLED,
                        refs=LedgerRefs(tenant=tenant),
                        adapter=None if self._sending is None else self._sending.channel.name,
                        outcome="enabled" if want is not None else "disabled",
                        content_digest=want,
                    ),
                )
        self._settled[tenant] = want

    async def outgoing(self, tenant: Tenant) -> tuple[Outgoing, ...]:
        """Every finding as it would leave, with what withholds it."""
        found = await self.findings(tenant)
        if not found:
            return ()
        pseudonyms = await self.pseudonyms(tenant)
        values = await self._values(tenant)
        return tuple(
            Outgoing(
                finding=finding,
                sent_as=(sent := pseudonyms.finding(finding)),
                text=texts.shown(sent, self._shape),
                withheld=self._check(self._parts(finding.lack), values),
            )
            for finding in found
        )

    async def send(self, tenant: Tenant) -> Sent:
        """Send what the channel does not hold yet; nothing where sending is not enabled."""
        await self.settle(tenant)
        if self._sending is None:
            return Sent()
        found = await self.findings(tenant)
        if not found:
            return Sent()
        pseudonyms = await self.pseudonyms(tenant)
        channel = self._sending.channel
        held = await channel.held(tenant)
        everywhere: dict[str, list[Reported]] = defaultdict(list)
        open_finding: dict[str, tuple[str, dict[str, Reported]]] = {}
        for one in held:
            marks = texts.reported(one.texts)
            for each in marks:
                everywhere[each.lack].append(each)
            if one.open and marks and marks[0].lack not in open_finding:
                open_finding[marks[0].lack] = (one.reference, texts.latest(marks))
        values: frozenset[str] | None = None
        opened = added = withheld = 0
        for local in found:
            finding = pseudonyms.finding(local)
            lack = finding.lack
            known = texts.latest(everywhere.get(lack.key, ()))
            reference, in_issue = open_finding.get(lack.key, (None, {}))
            sends = [
                (occurrence, state)
                for occurrence, state in rule.to_send(finding, known)
                # One whose finding was closed while it lasted: the product took it up.
                if not (occurrence.id in known and occurrence.id not in in_issue)
            ]
            if not sends:
                continue
            if values is None:
                values = await self._values(tenant)
            if self._check(self._parts(lack), values):
                withheld += 1
                continue
            on_instance = {pseudonyms.occurrence(o).id: o for o in local.occurrences}
            for occurrence, state in sends:
                key = key_of(lack, occurrence, state)
                if reference is None:
                    text = texts.opening(lack, occurrence, state, self._shape)
                    reference = await channel.open(tenant, texts.title(lack), text, key=key)
                    opened += 1
                    outcome = "opened"
                else:
                    text = texts.addition(lack, occurrence, state, in_issue)
                    await channel.add(tenant, reference, text, key=key)
                    added += 1
                    outcome = "added"
                in_issue[occurrence.id] = Reported(
                    lack=lack.key,
                    occurrence=occurrence.id,
                    state=state,
                    seconds=occurrence.seconds,
                    source=occurrence.source,
                )
                mine = on_instance[occurrence.id]
                await self._record(tenant, SENT, mine.run_id, mine.step_id, outcome, text)
        return Sent(opened=opened, added=added, withheld=withheld)

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
        key = f"taktus:report:{short(report.title + chr(10) + report.body)}"
        reference = await self._sending.channel.open(tenant, report.title, report.body, key=key)
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
        kept = self._kept
        sending = self._sending
        digest = await kept.objects.put(text.encode("utf-8"))
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
