"""What needs a person's action, wired (ADR-0106, issue #323): the facts the reporting component
reads, the scheduler's tick that reports them to the owner, and the startup lines that say who
will hear of them.

`RecordedSignals` reads a tenant's capacity crossings, which the governance component writes,
and its lost claims, which the run writes, by their kinds and nothing else of the ledger
(ADR-0105 §10), and the backup's outcomes, which the backup program writes into the database. It
hands them to the reporting component in its own shape. With the governance component's
`Corrections`, it also reads every incident about a level that fell by rule and every raise
Taktus proposed on the corrections (ADR-0110). The
components never import each other; this is where they meet. `alerts` builds the
use case over the owner-facing channel's own handlers, so that an alert reaches the owner
through the same channel, checks and renderings as every other report (ADR-0045).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime, timedelta

import structlog
from pydantic import ValidationError

from taktus.components.governance.application.service import Corrections
from taktus.components.governance.domain.model import Incident, Proposed
from taktus.components.governance.domain.service import capacity as capacity_rule
from taktus.components.reporting.application.service import Alerts, ProductFindings, Reported
from taktus.components.reporting.domain.model import (
    BackupRun,
    BackupState,
    CapacityCrossing,
    ClaimLost,
    LevelLowered,
    RaiseProposed,
    Signalled,
)
from taktus.components.run.application.service import CLAIM_LOST
from taktus.composition.owner_channel import OwnerChannelWiring
from taktus.composition.tenancy import this_round
from taktus.ports.backups import BackupLog, BackupOutcome
from taktus.ports.clock import Clock
from taktus.ports.identity import ServedTenants
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Tenant, TenantStore, UnitOfWork
from taktus.shared.v1 import LedgerEntry

INTERVAL_SECONDS = 60
"""How often the scheduler looks: the owner hears of a recorded fact within a minute, and each
look reads the entries of the kinds it reports, not the tenant's ledger."""

CAPACITY = "capacity."
"""Every kind the capacity report records a crossing under starts with this (platform.md §3)."""

READ_KINDS = (*capacity_rule.KINDS, CLAIM_LOST)
"""The kinds a look reads."""

log = structlog.get_logger("taktusd")


def _run(outcome: BackupOutcome) -> BackupRun:
    return BackupRun(name=outcome.name, at=outcome.at, reason=outcome.reason)


def _number(facts: dict[str, str | float | None], name: str) -> float | None:
    value = facts.get(name)
    return value if isinstance(value, float) else None


def _lowered(incident: Incident) -> LevelLowered:
    facts = dict(incident.facts)
    unit = facts.get("unit")
    anchors = facts.get("anchors")
    decided = _number(facts, "decided")
    step = facts.get("step")
    return LevelLowered.model_validate(
        {
            "incident": incident.id,
            "at": incident.raised_at,
            "process_version": incident.process_version,
            "action": None if unit in (None, "process") else unit,
            "rule": incident.rule,
            "before": int(str(facts.get("level_before"))),
            "after": int(str(facts.get("level_after"))),
            "anchors": tuple(a for a in str(anchors or "").split(", ") if a),
            "run_id": incident.run_id,
            "step_id": step if isinstance(step, str) else None,
            "decided": None if decided is None else int(decided),
            "rate": _number(facts, "rate"),
            "limit": _number(facts, "limit"),
            "window_days": _number(facts, "window_days"),
        }
    )


def _proposed(one: Proposed) -> RaiseProposed:
    figures = one.figures
    return RaiseProposed.model_validate(
        {
            "seq": one.seq,
            "at": figures.at,
            "process_version": one.process_version,
            "action": figures.unit.action,
            "week_decided": figures.week.decided,
            "week_rate": figures.week.rate,
            "month_decided": figures.month.decided,
            "month_rate": figures.month.rate,
            "counted_since": figures.counted_since,
        }
    )


def recorded(entries: Iterable[LedgerEntry]) -> tuple[list[CapacityCrossing], list[ClaimLost]]:
    """The capacity crossings and the lost claims among entries of any kind, in their order."""
    crossings: list[CapacityCrossing] = []
    losses: list[ClaimLost] = []
    for one in entries:
        if one.rehearsal:
            continue
        try:
            if one.kind.startswith(CAPACITY) and one.outcome in ("act", "ok"):
                crossings.append(
                    CapacityCrossing.model_validate(
                        {"seq": one.seq, "at": one.ts, "kind": one.kind, "outcome": one.outcome}
                    )
                )
            elif one.kind == CLAIM_LOST and one.refs.run_id is not None:
                losses.append(
                    ClaimLost.model_validate(
                        {"seq": one.seq, "at": one.ts, "run_id": one.refs.run_id}
                    )
                )
        except ValidationError:
            continue
    return crossings, losses


class RecordedSignals:
    """A tenant's recorded facts, as the reporting component reads them. An entry whose fields
    do not hold to the reporting component's patterns is left out: nothing that is not an
    identifier, a time or a token is ever reported."""

    def __init__(
        self,
        ledger: Ledger,
        work: UnitOfWork,
        backups: BackupLog,
        tenants: TenantStore,
        *,
        backup_expected_hours: int | None,
        corrections: Corrections | None = None,
    ) -> None:
        self._ledger = ledger
        self._work = work
        self._backups = backups
        self._tenants = tenants
        self._expected = backup_expected_hours
        self._corrections = corrections

    async def signalled(self, tenant: Tenant) -> Signalled:
        async with self._work.transaction(tenant):
            entries = await self._ledger.of_kinds(tenant, READ_KINDS)
            history = await self._backups.history(tenant)
            entry = await self._tenants.get(tenant)
        crossings, losses = recorded(entries)
        lowered: list[LevelLowered] = []
        raises: list[RaiseProposed] = []
        if self._corrections is not None:
            for incident in await self._corrections.lowerings(tenant):
                try:
                    lowered.append(_lowered(incident))
                except (ValidationError, ValueError):
                    continue
            for proposal in await self._corrections.proposed(tenant):
                try:
                    raises.append(_proposed(proposal))
                except ValidationError:
                    continue
        return Signalled(
            capacity=tuple(crossings),
            claims_lost=tuple(losses),
            lowered=tuple(lowered),
            raises=tuple(raises),
            backup=BackupState(
                watched_since=None if entry is None else entry.created_at,
                expected_hours=self._expected,
                last_ok=None if history.last_ok is None else _run(history.last_ok),
                failed=tuple(_run(o) for o in history.failed),
                failed_count=history.failed_count,
            ),
        )


def alerts(
    ledger: Ledger,
    work: UnitOfWork,
    backups: BackupLog,
    tenants: TenantStore,
    owner: OwnerChannelWiring,
    clock: Clock,
    *,
    backup_expected_hours: int | None,
    corrections: Corrections | None = None,
    findings: ProductFindings | None = None,
) -> Alerts:
    """Given `findings`, a local lack is one more alert (ADR-0118)."""
    return Alerts(
        RecordedSignals(
            ledger,
            work,
            backups,
            tenants,
            backup_expected_hours=backup_expected_hours,
            corrections=corrections,
        ),
        owner.queries,
        owner.channel,
        owner.raising,
        clock,
        findings,
    )


def alerts_tick(
    found: Alerts,
    tenants: ServedTenants,
    clock: Clock,
    *,
    interval_seconds: int = INTERVAL_SECONDS,
) -> Callable[[], Awaitable[None]]:
    """What the scheduler calls on every tick: every tenant's alerts are reported when the
    interval has passed since the last look — the first tick looks at once. A look that fails is
    logged and made again at the next interval: reporting never stops the scheduler."""
    last: list[datetime] = []

    async def tick() -> None:
        now = clock.now()
        if last and now - last[0] < timedelta(seconds=interval_seconds):
            return
        last[:] = [now]
        for tenant in await this_round(tenants, "scheduler"):
            try:
                done: Reported = await found.report(tenant)
            except Exception as error:  # a report must never take the scheduler down
                log.error("alerts not reported", tenant=tenant, error=type(error).__name__)
                continue
            if done.raised or done.delivered or done.refused:
                log.warning(
                    "what needs a person's action reported to the owner",
                    tenant=tenant,
                    raised=done.raised,
                    delivered=done.delivered,
                    refused=done.refused,
                )

    return tick


async def say_who_hears(
    owner: OwnerChannelWiring,
    tenants: ServedTenants,
    *,
    backup_expected_hours: int | None,
) -> None:
    """The startup lines (ADR-0106 §6): every served tenant without an owner-facing channel,
    whose alerts stay in the log and the ledger, and whether a missing backup is watched."""
    for tenant in await this_round(tenants, "startup"):
        try:
            channel = await owner.channel.of(tenant)
        except Exception as error:  # a startup line never stops the start
            log.error("owner channel not read", tenant=tenant, error=type(error).__name__)
            continue
        if channel is None:
            log.warning(
                "no owner-facing channel: what needs a person's action stays in the log and "
                "the ledger, and `taktusctl alerts` shows it",
                tenant=tenant,
            )
    if backup_expected_hours is None:
        log.info(
            "a missing backup is not watched: TAKTUS_BACKUP_EXPECTED_HOURS is not set; a "
            "failed one recorded by the backup is still reported"
        )
    else:
        log.info("a missing backup is watched", expected_hours=backup_expected_hours)
