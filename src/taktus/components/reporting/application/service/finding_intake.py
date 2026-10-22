"""Use case: the intake of findings that other instances submit (ADR-0118, UC-6.12).

An instance that has a channel to the repository — the project's own — takes the product
candidates of other instances here and opens or adds to their issues with its own channel. A
sending instance needs no account and no app of its own on the repository service (DEC-0214).
Five things hold, in this order:

1. **The signature.** A submission carries the sender's public key, the payload as it was
   signed, and the signature. One whose signature does not verify is `forged`, and nothing is
   recorded: an unsigned request writes nothing.
2. **What it may carry.** A finding's submission is closed values only (`Submission`). A report
   by hand is the person's text, which their own instance checked. The intake checks every part
   again for the shapes of personal data, and refuses one that carries any as `invalid`.
3. **A new sender is held.** The first submission under a public key registers the key and its
   sender in this tenant's ledger (`intake.sender`) and raises a report of kind `need` in the
   owner's channel. Until the owner answers it that it is done, every submission of the sender
   is answered `held`, and the sender tries again at its interval. A key that names a sender
   another key registered is `refused`. At most `pending_max` senders wait at once; a further
   new one is `limited`, so that made-up keys cannot fill the owner's channel.
4. **Each sender is rate-limited.** A confirmed sender's submissions are counted over the last
   hour from the ledger's `intake.received` entries. One over the rate is `limited`.
5. **The issue.** A finding's occurrence is delivered as the instance's own are: it opens the
   lack's issue, adds to the open one, or is `known` already. The same lack from another sender
   adds an occurrence. A report opens an issue of its own, once for the same text.

Every submission taken is recorded as `intake.received`, its sender as the actor and what was
done as its outcome. The texts the issue holds are the intake's own sentences around closed
values, in the shape its operator configured.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta

from pydantic import ValidationError

from taktus.components.reporting.application.query import ReportQueries
from taktus.components.reporting.application.service.errors import ReportingError
from taktus.components.reporting.application.service.product_findings import deliver
from taktus.components.reporting.application.service.raise_report import (
    DONE,
    RaiseReport,
    RaiseReportHandler,
)
from taktus.components.reporting.domain.model import Finding, ReportKind, Submission
from taktus.components.reporting.domain.model.finding import short
from taktus.components.reporting.domain.service import leaving
from taktus.components.reporting.ports import FindingChannel, IntakeAnswer, Signatures, Signed
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

RECEIVED = "intake.received"
"""A submission the intake took: the sender as the actor, what was done as the outcome."""
SENDER = "intake.sender"
"""A sender's first contact: its public key and its identifier, as the object it points to."""
SENDER_REPORT = "finding-sender-"
"""The prefix of the report that asks the owner to confirm a sender."""
RATE_WINDOW = timedelta(hours=1)
CONFIRM_DAYS = 7


@dataclass(frozen=True)
class Received:
    """What the intake did with one submission, and the issue it went to where it opened one."""

    answer: IntakeAnswer
    reference: str | None = None


@dataclass(frozen=True)
class IntakeOptions:
    """The intake's configuration. `tenant` is the one whose owner confirms senders and whose
    ledger records what was taken. `rate` is how many submissions a sender may make in an
    hour. `pending_max` is how many new senders may wait for the owner at once. `shape` is the
    form of a finding's issue, as the intake's operator configured it."""

    tenant: Tenant
    rate: int = 30
    pending_max: int = 5
    shape: str | None = None


@dataclass(frozen=True)
class Taking:
    """Where the intake keeps what it knows, and what it raises a confirmation through."""

    ledger: Ledger
    objects: ObjectStore
    work: UnitOfWork
    reports: ReportQueries
    raising: RaiseReportHandler
    clock: Clock


def report_of(key: str) -> str:
    """The identifier of the report that asks to confirm the sender of this public key."""
    return SENDER_REPORT + short(key)


class FindingsIntake:
    def __init__(
        self,
        channel: FindingChannel,
        signatures: Signatures,
        taking: Taking,
        options: IntakeOptions,
    ) -> None:
        self._channel = channel
        self._signatures = signatures
        self._taking = taking
        self._options = options

    @property
    def tenant(self) -> Tenant:
        return self._options.tenant

    async def receive(self, signed: Signed) -> Received:
        payload = signed.payload.encode("utf-8")
        if not self._signatures.verify(signed.key, payload, signed.signature):
            return Received("forged")
        try:
            submission = Submission.model_validate_json(payload)
        except ValidationError:
            return Received("invalid")
        if leaving.check(self._parts(submission), frozenset()):
            return Received("invalid")
        senders = await self.senders()
        source = senders.get(signed.key)
        if source is None:
            return await self._first_contact(signed.key, submission.source, senders)
        if source != submission.source:
            return Received("refused")
        if not await self._confirmed(signed.key, source):
            return Received("held")
        if await self._over_rate(source):
            return Received("limited")
        return await self._take(submission, payload)

    async def senders(self) -> dict[str, str]:
        """Every registered sender: its public key and its identifier, the first registration
        of a key holding."""
        taking, tenant = self._taking, self.tenant
        async with taking.work.transaction(tenant):
            entries = await taking.ledger.of_kinds(tenant, {SENDER})
        found: dict[str, str] = {}
        for entry in entries:
            if entry.content_digest is None:
                continue
            stored = await taking.objects.get(entry.content_digest)
            if stored is None:
                continue
            document = json.loads(stored)
            found.setdefault(str(document["key"]), str(document["source"]))
        return found

    async def confirmed(self, key: str) -> bool:
        """Whether the owner answered the sender's report that it is done."""
        report = await self._taking.reports.one(self.tenant, report_of(key))
        return report is not None and report.filed is not None and report.filed.answer == DONE

    async def _first_contact(self, key: str, source: str, senders: dict[str, str]) -> Received:
        if source in senders.values():
            return Received("refused")
        waiting = [k for k in senders if not await self.confirmed(k)]
        if len(waiting) >= self._options.pending_max:
            return Received("limited")
        taking, tenant = self._taking, self.tenant
        document = json.dumps({"key": key, "source": source}, sort_keys=True)
        digest = await taking.objects.put(document.encode("utf-8"))
        async with taking.work.transaction(tenant):
            await taking.ledger.record(
                tenant,
                Fact(
                    kind=SENDER,
                    refs=LedgerRefs(tenant=tenant, actor=source),
                    outcome="registered",
                    content_digest=digest,
                ),
            )
        await self._ask(key, source)
        return Received("held")

    async def _confirmed(self, key: str, source: str) -> bool:
        report = await self._taking.reports.one(self.tenant, report_of(key))
        if report is None:
            # Not raised at first contact — the tenant had no channel then: raised now.
            await self._ask(key, source)
            return False
        return report.filed is not None and report.filed.answer == DONE

    async def _ask(self, key: str, source: str) -> None:
        """Raise the report that asks the owner to confirm the sender. A tenant without an
        owner-facing channel raises nothing, and the sender stays held."""
        taking = self._taking
        today = taking.clock.now().date()
        fingerprint = short(key)
        try:
            await taking.raising.execute(
                RaiseReport(
                    tenant=self.tenant,
                    id=report_of(key),
                    kind=ReportKind.NEED,
                    title=f"A new sender of findings asks to be admitted: {source}",
                    needed=(
                        f"Your confirmation that the sender `{source}` may raise product "
                        "findings and reports in the repository through this instance. Its "
                        f"signing key's fingerprint is `{fingerprint}`.",
                    ),
                    steps=(
                        "Ask the operator of the instance you expect findings from which "
                        "sender it is: `taktusctl findings` prints the sender below every "
                        "finding.",
                        "Answer this message that it is done to admit the sender. Its "
                        "submissions are taken from its next attempt on.",
                        "Leave it unanswered to keep the sender held. It is never admitted "
                        "without your answer.",
                    ),
                    standing_still=(
                        f"Every finding and report the sender `{source}` submits: the intake "
                        "answers it `held`, and the sender tries again at its interval.",
                    ),
                    due=today + timedelta(days=CONFIRM_DAYS),
                )
            )
        except ReportingError:
            return

    async def _over_rate(self, source: str) -> bool:
        taking, tenant = self._taking, self.tenant
        since = taking.clock.now() - RATE_WINDOW
        async with taking.work.transaction(tenant):
            recent = await taking.ledger.of_kinds(tenant, {RECEIVED}, since=since)
        return sum(1 for e in recent if e.refs.actor == source) >= self._options.rate

    async def _take(self, submission: Submission, payload: bytes) -> Received:
        tenant = self.tenant
        if submission.title is not None and submission.body is not None:
            key = f"taktus:report:{short(submission.title + chr(10) + submission.body)}"
            reference = await self._channel.open(tenant, submission.title, submission.body, key=key)
            await self._record(submission.source, "opened", submission.body.encode("utf-8"))
            return Received("opened", reference)
        if submission.lack is None or submission.occurrence is None:
            return Received("invalid")
        finding = Finding(lack=submission.lack, occurrences=(submission.occurrence,))
        done = await deliver(self._channel, tenant, [finding], self._options.shape)
        if not done:
            await self._record(submission.source, "known", payload)
            return Received("known")
        (one,) = done
        await self._record(submission.source, one.outcome, one.text.encode("utf-8"))
        return Received("opened" if one.outcome == "opened" else "added")

    async def _record(self, source: str, outcome: str, content: bytes) -> None:
        taking, tenant = self._taking, self.tenant
        digest = await taking.objects.put(content)
        async with taking.work.transaction(tenant):
            await taking.ledger.record(
                tenant,
                Fact(
                    kind=RECEIVED,
                    refs=LedgerRefs(tenant=tenant, actor=source),
                    adapter=self._channel.name,
                    outcome=outcome,
                    content_digest=digest,
                ),
            )

    @staticmethod
    def _parts(submission: Submission) -> tuple[str, ...]:
        if submission.lack is not None:
            return (submission.lack.lacking,)
        return (submission.title or "", submission.body or "")
