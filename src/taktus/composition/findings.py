"""The product finding, wired (UC-6.12, ADR-0046): the run's accounts as the blocks a finding
reads, and a repository as the channel it is sent through.

`RunBlocks` reads the run's blocked-time accounts — every block that ended, and every block still
open on its step run — and hands them to the reporting component in its own shape. The two
components never import each other; this is where they meet.

`RunContent` reads what the tenant's runs were given and what their work states: the values no
text that leaves for the product may carry (ADR-0112 §4).

`RepositoryChannel` sends through a connector that serves `repository.issues` and
`repository.comments` on the repository its operator configured it for. A finding is an issue,
opened with the labels its operator configured (`TAKTUS_FINDINGS_LABELS`, none by default), and
every later report a comment on it. Which repository, which labels and which shape are the
operator's configuration, never one project's (ADR-0092). Taktus writes as itself (ADR-0033):
the call carries Taktus's own identity and references the credential the connector declares for
actions. The connector is the one `TAKTUS_FINDINGS_CONNECTOR` names; an instance whose operator
did not name one sends nothing and shows its findings to the operator instead
(`taktusctl findings`).

`IntakeClient` is the other way out (ADR-0118): an instance without a connector of its own to
the repository submits each candidate, signed, to the intake of another instance, at the
address `TAKTUS_FINDINGS_INTAKE` names. `sending_of` chooses between the two from the
operator's settings, and builds nothing at the level `off`. `intake_of` builds the intake an
instance opens to other instances' findings, where its operator named the tenant whose owner
confirms their senders.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

import httpx
import structlog

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.signing import Ed25519Signatures
from taktus.components.reporting.application.query import ReportQueries
from taktus.components.reporting.application.service import (
    FindingsIntake,
    IntakeOptions,
    ProductFindings,
    RaiseReportHandler,
    Sending,
    Sent,
    Taking,
)
from taktus.components.reporting.domain.model import Blocked, FindingsLevel
from taktus.components.reporting.domain.service.texts import MARK
from taktus.components.reporting.ports import (
    ChannelIncomplete,
    Held,
    IntakeAnswer,
    IntakeUnreachable,
    Signed,
)
from taktus.components.run.application.query import BlockedTime
from taktus.components.run.domain.model import Run
from taktus.composition.settings import FindingsShape
from taktus.composition.tenancy import this_round
from taktus.ports.clock import Clock
from taktus.ports.configuration import ConfigurationError
from taktus.ports.connector import ActionConnector, CallContext
from taktus.ports.identity import ServedTenants
from taktus.ports.ledger import Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.ports.worker import CredentialReference
from taktus.shared.v1 import Command

TAKTUS = "taktus"
"""The identity Taktus acts as on its own behalf (ADR-0033)."""
READ_KEY = "taktus:finding:read"
"""A read changes nothing; the contract asks every call for a key, so a read carries this one."""
ADAPTER = "findings.repository"
INTAKE_ADAPTER = "findings.intake"
ANSWERS: frozenset[str] = frozenset(
    {"opened", "added", "known", "held", "refused", "limited", "forged", "invalid"}
)
"""Every answer an intake gives; anything else is no answer."""
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


NAMES_OF_THE_PRODUCT = frozenset({"operation", "capability", "capabilities", "requires"})
"""The keys of a work whose values name what a step needs of the product, not the tenant's
content: a finding is about exactly these."""


def leaves(value: Any, *, under: str | None = None) -> list[str]:
    """Every text and number in a document, as text; a reference (`$input.…`) and the value of
    a key in `NAMES_OF_THE_PRODUCT` left out."""
    if under in NAMES_OF_THE_PRODUCT:
        return []
    if isinstance(value, Mapping):
        return [leaf for key, each in value.items() for leaf in leaves(each, under=str(key))]
    if isinstance(value, list | tuple):
        return [leaf for each in value for leaf in leaves(each, under=under)]
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, int | float):
        return [str(value)]
    text = str(value)
    return [] if text.startswith("$") else [text]


class RunContent:
    """What the tenant's commands said and its runs were given, and what their work states,
    read from the repositories each time it is asked: when a finding has something to send,
    and when a person prepares a report."""

    def __init__(
        self,
        runs: Repository[Run],
        work: UnitOfWork,
        commands: Repository[Command] | None = None,
    ) -> None:
        self._runs = runs
        self._work = work
        self._commands = commands

    async def values(self, tenant: Tenant) -> Sequence[str]:
        async with self._work.transaction(tenant):
            runs = await self._runs.list(tenant)
            commands = [] if self._commands is None else await self._commands.list(tenant)
        found: list[str] = []
        for command in commands:
            found += leaves(command.model_dump(mode="json", include={"intent", "context"}))
        for run in runs:
            found += leaves(run.inputs)
            found += leaves(run.work)
        return found


class RepositoryChannel:
    """The repository findings go to, reached through one connector, which names it."""

    def __init__(
        self, connector: ActionConnector, *, name: str = ADAPTER, labels: Sequence[str] = ()
    ) -> None:
        self._connector = connector
        self._name = name
        self._labels = tuple(labels)
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
            {"title": title, "body": body, "labels": list(self._labels)},
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


class IntakeClient:
    """The sender's half of the intake: one request per submission, to the address its
    operator set. An intake that does not answer, or answers something else than an intake
    answers, is unreachable, and the submission is tried again at the next interval."""

    def __init__(
        self,
        address: str,
        *,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._address = address
        self._timeout = timeout_seconds
        self._transport = transport

    @property
    def name(self) -> str:
        return INTAKE_ADAPTER

    async def submit(self, signed: Signed) -> IntakeAnswer:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(self._address, json=signed.model_dump())
            answer = response.json().get("answer")
        except (httpx.HTTPError, ValueError, AttributeError) as error:
            raise IntakeUnreachable(type(error).__name__) from error
        if answer not in ANSWERS:
            raise IntakeUnreachable(f"status {response.status_code} without an intake's answer")
        found: IntakeAnswer = answer
        return found


def sending_of(shape: FindingsShape, connector: str | None) -> Sending | None:
    """Where this instance's candidates go, from its operator's settings: through its own
    connector to the repository, or to another instance's intake. None at the level `off`."""
    if shape.level not in ("review", "automatic"):
        return None
    level: FindingsLevel = "review" if shape.level == "review" else "automatic"
    if connector is not None:
        channel = RepositoryChannel(McpActionConnector(connector), labels=shape.labels)
        return Sending(channel, connector, level=level)
    if shape.intake is not None:
        return Sending(
            IntakeClient(shape.intake), shape.intake, level=level, signatures=Ed25519Signatures()
        )
    raise ConfigurationError(
        "TAKTUS_FINDINGS_LEVEL",
        f"{shape.level!r} sends to the product, and neither TAKTUS_FINDINGS_CONNECTOR nor "
        "TAKTUS_FINDINGS_INTAKE says where: set one, or the level off",
    )


def intake_of(
    shape: FindingsShape,
    connector: str | None,
    *,
    ledger: Ledger,
    objects: ObjectStore,
    work: UnitOfWork,
    reports: ReportQueries,
    raising: RaiseReportHandler,
    clock: Clock,
    form: str | None,
) -> FindingsIntake | None:
    """The intake this instance opens to other instances' findings; None where its operator
    named no tenant to confirm their senders."""
    if shape.intake_tenant is None:
        return None
    if connector is None:
        raise ConfigurationError(
            "TAKTUS_FINDINGS_INTAKE_TENANT",
            "an intake opens issues through this instance's own connector: set "
            "TAKTUS_FINDINGS_CONNECTOR too, or unset this",
        )
    return FindingsIntake(
        RepositoryChannel(McpActionConnector(connector), labels=shape.labels),
        Ed25519Signatures(),
        Taking(ledger, objects, work, reports, raising, clock),
        IntakeOptions(tenant=shape.intake_tenant, rate=shape.intake_rate, shape=form),
    )


def findings_tick(
    findings: ProductFindings,
    tenants: ServedTenants,
    clock: Clock,
    *,
    interval_seconds: int = INTERVAL_SECONDS,
) -> Callable[[], Awaitable[None]]:
    """What the scheduler calls on every tick: when the interval has passed since the last
    sending — the first tick at once — every tenant's findings are sent where sending is
    enabled, and a change of the setting is recorded in each tenant's ledger either way.
    A sending that fails is logged and tried again at the next interval: reporting never stops
    the scheduler, and what was not sent is sent then."""
    last: list[datetime] = []

    async def tick() -> None:
        now = clock.now()
        if last and now - last[0] < timedelta(seconds=interval_seconds):
            return
        last[:] = [now]
        for tenant in await this_round(tenants, "scheduler"):
            try:
                sent: Sent = await findings.send(tenant)
            except Exception as error:  # a sending must never take the scheduler down
                log.error("product findings not sent", tenant=tenant, error=type(error).__name__)
                continue
            if sent.opened or sent.added:
                log.info(
                    "product findings sent", tenant=tenant, opened=sent.opened, added=sent.added
                )
            if sent.held:
                log.info("product findings wait at the intake: it holds this sender", tenant=tenant)
            if sent.withheld:
                # The count alone: what withholds a finding is shown on the instance, never logged.
                log.warning(
                    "product findings withheld: they carry a value of the tenant",
                    tenant=tenant,
                    withheld=sent.withheld,
                )

    return tick
