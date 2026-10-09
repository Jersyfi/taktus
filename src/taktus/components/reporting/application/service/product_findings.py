"""The product finding (UC-6.12, ADR-0046): what an instance met that the product lacks, shown to
its operator and sent where the operator enabled it.

`findings` is the view: the rule over the tenant's blocks, every lack with its occurrences. It is
what the instance records and shows its operator, sent or not; the operator can send it by hand
(`taktusctl findings`). It is computed from the blocked-time accounts each time it is read, so
there is nothing to keep in step with them.

`send` sends what the channel does not hold yet. A lack the channel holds an open finding for is
added to it — one more occurrence, the waiting summed — and a lack it holds none open for opens
one. An occurrence the channel holds is never sent again, so a restart, or a second instance,
sends nothing twice. Every text sent is recorded in the tenant's ledger as `finding.sent`, with
the run and the step it is about and the text's digest, as every other outward effect is.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from taktus.components.reporting.domain.model import Finding, Lack, Occurrence, Reported
from taktus.components.reporting.domain.service import findings as rule
from taktus.components.reporting.domain.service import texts
from taktus.components.reporting.domain.service.findings import State
from taktus.components.reporting.ports import Blocks, FindingChannel
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

SENT = "finding.sent"
"""The ledger entry of a text sent to the channel: `opened` or `added` as its outcome."""


@dataclass(frozen=True)
class Sent:
    """What one `send` did: findings opened and additions made. Zero and zero when there was
    nothing new, or no channel."""

    opened: int = 0
    added: int = 0


@dataclass(frozen=True)
class Sending:
    """Where findings go, on an instance whose operator enabled it, and where each text sent is
    recorded."""

    channel: FindingChannel
    ledger: Ledger
    objects: ObjectStore
    work: UnitOfWork


def key_of(lack: Lack, occurrence: Occurrence, state: State) -> str:
    """The idempotency key of one text: the lack, the occurrence and its state. Derived, never
    stored, so a repeat after a restart carries the same key."""
    return f"taktus:finding:{lack.key}:{occurrence.id}:{state}"


class ProductFindings:
    def __init__(self, blocks: Blocks, sending: Sending | None = None) -> None:
        self._blocks = blocks
        self._sending = sending

    @property
    def enabled(self) -> bool:
        """Whether this instance sends its findings, or only records and shows them."""
        return self._sending is not None

    async def findings(self, tenant: Tenant) -> tuple[Finding, ...]:
        """Every lack the tenant's blocks were for, each with its occurrences."""
        return rule.findings(await self._blocks.blocks(tenant))

    async def send(self, tenant: Tenant) -> Sent:
        """Send what the channel does not hold yet; nothing where sending is not enabled."""
        if self._sending is None:
            return Sent()
        found = await self.findings(tenant)
        if not found:
            return Sent()
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
        opened = added = 0
        for finding in found:
            lack = finding.lack
            known = texts.latest(everywhere.get(lack.key, ()))
            reference, in_issue = open_finding.get(lack.key, (None, {}))
            for occurrence, state in rule.to_send(finding, known):
                if occurrence.id in known and occurrence.id not in in_issue:
                    # Its finding was closed while it lasted: the product took it up.
                    continue
                key = key_of(lack, occurrence, state)
                if reference is None:
                    text = texts.opening(lack, occurrence, state)
                    reference = await channel.open(tenant, texts.title(lack), text, key=key)
                    opened += 1
                    outcome = "opened"
                else:
                    text = texts.addition(lack, occurrence, state, in_issue)
                    await channel.add(tenant, reference, text, key=key)
                    added += 1
                    outcome = "added"
                in_issue[occurrence.id] = Reported(
                    lack=lack.key, occurrence=occurrence.id, state=state, seconds=occurrence.seconds
                )
                await self._record(tenant, occurrence, outcome, text)
        return Sent(opened=opened, added=added)

    async def _record(
        self, tenant: Tenant, occurrence: Occurrence, outcome: str, text: str
    ) -> None:
        sending = self._sending
        if sending is None:
            return
        digest = await sending.objects.put(text.encode("utf-8"))
        async with sending.work.transaction(tenant):
            await sending.ledger.record(
                tenant,
                Fact(
                    kind=SENT,
                    refs=LedgerRefs(run_id=occurrence.run_id, step_id=occurrence.step_id),
                    adapter=sending.channel.name,
                    outcome=outcome,
                    content_digest=digest,
                ),
            )
