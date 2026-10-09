"""The product finding, wired (UC-6.12, ADR-0046): the run's accounts as the blocks a finding
reads, and the Taktus repository as the channel it is sent through.

`RunBlocks` reads the run's blocked-time accounts — every block that ended, and every block still
open on its step run — and hands them to the reporting component in its own shape. The two
components never import each other; this is where they meet.

`RepositoryChannel` sends through a connector that serves `repository.issues` and
`repository.comments` on the Taktus repository. A finding is an issue labelled `task`, and every
later report a comment on it. Taktus writes as itself (ADR-0033): the call carries Taktus's own
identity and references the credential the connector declares for actions. The connector is the
one `TAKTUS_FINDINGS_CONNECTOR` names; an instance whose operator did not name one sends nothing
and shows its findings to the operator instead (`taktusctl findings`).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

import structlog

from taktus.components.reporting.application.service import ProductFindings, Sent
from taktus.components.reporting.domain.model import Blocked
from taktus.components.reporting.domain.service.texts import MARK
from taktus.components.reporting.ports import ChannelIncomplete, Held
from taktus.components.run.application.query import BlockedTime
from taktus.ports.clock import Clock
from taktus.ports.connector import ActionConnector, CallContext
from taktus.ports.persistence import Tenant
from taktus.ports.worker import CredentialReference

TAKTUS = "taktus"
"""The identity Taktus acts as on its own behalf (ADR-0033)."""
READ_KEY = "taktus:finding:read"
"""A read changes nothing; the contract asks every call for a key, so a read carries this one."""
LABELS = ("task",)
"""A finding is a task of the backlog (DEC-0051): the form's label, and no other."""
ADAPTER = "findings.repository"
INTERVAL_SECONDS = 600
"""How often the scheduler sends findings: a block that waits is waiting minutes at least, and
every sending reads the repository's issues once, against the service's rate limit."""

log = structlog.get_logger("taktusd")


class RunBlocks:
    """The blocks of the run's accounts, ended and open, as the reporting component reads them."""

    def __init__(self, accounts: BlockedTime) -> None:
        self._accounts = accounts

    async def blocks(self, tenant: Tenant) -> Sequence[Blocked]:
        ended = [
            Blocked(
                cause=b.cause,
                run_id=b.run_id,
                step_id=b.step_id,
                since=b.since,
                seconds=b.seconds,
                lacking=b.lacking,
            )
            for b in await self._accounts.blocks(tenant)
        ]
        still = [
            Blocked(
                cause=w.cause,
                run_id=w.run_id,
                step_id=w.step_id,
                since=w.since,
                lacking=w.lacking,
            )
            for w in await self._accounts.waiting(tenant)
        ]
        return [*ended, *still]


class RepositoryChannel:
    """The Taktus repository, reached through one connector."""

    def __init__(self, connector: ActionConnector, *, name: str = ADAPTER) -> None:
        self._connector = connector
        self._name = name
        self._credentials: tuple[CredentialReference, ...] | None = None

    @property
    def name(self) -> str:
        return self._name

    async def held(self, tenant: Tenant) -> Sequence[Held]:
        listed = await self._call(tenant, "repository.issues.list", {"state": "all"}, READ_KEY)
        if not listed.get("complete", False):
            raise ChannelIncomplete("the repository's issues could not all be read")
        found: list[Held] = []
        for issue in listed.get("issues", []):
            body = str(issue.get("body", ""))
            if MARK not in body:
                continue
            number = int(issue["number"])
            comments = await self._call(
                tenant, "repository.comments.list", {"number": number}, READ_KEY
            )
            found.append(
                Held(
                    reference=str(number),
                    open=issue.get("state") == "open",
                    texts=(body, *(str(c.get("body", "")) for c in comments.get("comments", []))),
                )
            )
        return sorted(found, key=lambda h: int(h.reference))

    async def open(self, tenant: Tenant, title: str, body: str, *, key: str) -> str:
        created = await self._call(
            tenant,
            "repository.issues.create",
            {"title": title, "body": body, "labels": list(LABELS)},
            key,
        )
        return str(created["number"])

    async def add(self, tenant: Tenant, reference: str, text: str, *, key: str) -> None:
        await self._call(
            tenant, "repository.comments.create", {"number": int(reference), "body": text}, key
        )

    async def _call(
        self, tenant: Tenant, operation: str, input: Mapping[str, Any], key: str
    ) -> dict[str, Any]:
        if self._credentials is None:
            declaration = await self._connector.capabilities()
            self._credentials = tuple(
                CredentialReference(name=need.name, injected_as="env")
                for need in declaration.credentials
                if need.purpose == "actions"
            )
        context = CallContext(
            tenant=tenant,
            identity=TAKTUS,
            run_id="finding",
            step_id="report",
            attempt=1,
            idempotency_key=key,
            credentials=self._credentials,
        )
        result = await self._connector.call(operation, context, input)
        return result.output


def findings_tick(
    findings: ProductFindings,
    tenants: Sequence[Tenant],
    clock: Clock,
    *,
    interval_seconds: int = INTERVAL_SECONDS,
) -> Callable[[], Awaitable[None]]:
    """What the scheduler calls on every tick: where sending is enabled, every tenant's findings
    are sent when the interval has passed since the last sending — the first tick sends at once.
    A sending that fails is logged and tried again at the next interval: reporting never stops
    the scheduler, and what was not sent is sent then."""
    last: list[datetime] = []

    async def tick() -> None:
        if not findings.enabled:
            return
        now = clock.now()
        if last and now - last[0] < timedelta(seconds=interval_seconds):
            return
        last[:] = [now]
        for tenant in tenants:
            try:
                sent: Sent = await findings.send(tenant)
            except Exception as error:  # a sending must never take the scheduler down
                log.error("product findings not sent", tenant=tenant, error=type(error).__name__)
                continue
            if sent.opened or sent.added:
                log.info(
                    "product findings sent", tenant=tenant, opened=sent.opened, added=sent.added
                )

    return tick
