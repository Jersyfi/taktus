"""A tenant's limits per unit of its structure, kept, watched and reported on (ADR-0282).

The run reads the limits that apply to a run through its port `UnitLimitsPort`, which the
composition root answers from here, and hands back what it saw: the period's cost and the cost
per day at every admission, and every step a limit refused. From these this service raises,
each by a rule or a statistic and never a model (ADR-0023): an alert at a share of the amount or
of the forecast, the line reached, an anomaly, and a limit that does harm. It never changes a
limit; a change is a person's, recorded as `unit_limit.configured` naming who made it.

A limit that holds each person of a unit on their own names no one. What one person spent
against it raises nothing to a role and is shown only to that person; its harm report counts
every person's holds together (principle 14, DEC-0069).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

from taktus.components.governance.domain.model.incident import (
    Incident,
    IncidentKind,
    incident_id,
)
from taktus.components.governance.domain.model.unit_limits import (
    HISTORY_DAYS,
    Amounts,
    Children,
    Forecast,
    Held,
    LimitWatch,
    Period,
    Policy,
    UnitLimit,
    anomalous,
    forecast,
    harm,
    period_of,
)
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

CONFIGURED = "unit_limit.configured"
WATCHED = "unit_limit.watched"
HELD = "unit_limit.held"
RELEASED = "unit_limit.released"
RAISED = "incident.raised"


class UnitLimitRefused(ValueError):
    """A limit that would not hold: a unit named like a person, or children booked over a
    parent that keeps them within."""


@dataclass(frozen=True)
class SetUnitLimit:
    tenant: Tenant
    name: str
    role: str
    unit: tuple[str, ...] = ()
    individually: bool = False
    process: str | None = None
    period: Period = "month"
    money: Mapping[str, float] | None = None
    compute_seconds: float | None = None
    tokens: int | None = None
    policy: Policy = "halt"
    alert_at: tuple[float, ...] = (0.8,)
    children: Children = "within"
    check_every_seconds: int = 900


@dataclass(frozen=True)
class Standing:
    """One limit as a viewer sees it: its cost this period, its forecast, its alerts."""

    limit: UnitLimit
    period: str
    spent: Mapping[str, float]
    forecasts: tuple[Forecast, ...]
    alerts: tuple[str, ...] = field(default=())


def _children(parent: UnitLimit, every: Sequence[UnitLimit]) -> list[UnitLimit]:
    """The limits set directly below `parent`: none lies between."""
    below = [c for c in every if parent.is_parent_of(c)]
    return [
        c for c in below if not any(parent.is_parent_of(m) and m.is_parent_of(c) for m in below)
    ]


def _overbooked(parent: UnitLimit, children: Sequence[UnitLimit]) -> list[str]:
    """The lines on which `children` together book more than `parent` allows."""
    allowed = parent.amounts.lines()
    sums: dict[str, float] = {}
    for child in children:
        for line, amount in child.amounts.lines().items():
            sums[line] = sums.get(line, 0.0) + amount
    return sorted(
        line for line, total in sums.items() if line in allowed and total > allowed[line] + 1e-9
    )


class UnitLimits:
    def __init__(
        self,
        limits: Repository[UnitLimit],
        watches: Repository[LimitWatch],
        incidents: Repository[Incident],
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
        names_a_person: Callable[[Tenant, str], Awaitable[bool]],
    ) -> None:
        self._limits = limits
        self._watches = watches
        self._incidents = incidents
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._names_a_person = names_a_person

    # --- kept by a person ------------------------------------------------------------------

    async def all(self, tenant: Tenant) -> list[UnitLimit]:
        async with self._work.transaction(tenant):
            stored = await self._limits.list(tenant)
        return sorted(
            (lim for lim in stored if not lim.cleared), key=lambda lim: (lim.unit, lim.id)
        )

    async def get(self, tenant: Tenant, name: str) -> UnitLimit | None:
        async with self._work.transaction(tenant):
            found = await self._limits.get(tenant, name)
        return None if found is None or found.cleared else found

    async def set(self, command: SetUnitLimit, *, by: str) -> UnitLimit:
        """Store the limit, replacing one of its name. Refused, and nothing changed, where a
        unit is named like a person, or children are booked over a parent that keeps them
        within."""
        for part in command.unit:
            if await self._names_a_person(command.tenant, part):
                raise UnitLimitRefused(
                    f"{part!r} is an identity of the tenant; a unit is never a person — hold "
                    "each person of a unit on their own instead (principle 14, DEC-0069)"
                )
        try:
            limit = UnitLimit(
                id=command.name,
                tenant=command.tenant,
                unit=tuple(command.unit),
                individually=command.individually,
                process=command.process,
                period=command.period,
                amounts=Amounts(
                    money=None if command.money is None else dict(command.money),
                    compute_seconds=command.compute_seconds,
                    tokens=command.tokens,
                ),
                policy=command.policy,
                alert_at=tuple(command.alert_at),
                role=command.role,
                children=command.children,
                check_every_seconds=command.check_every_seconds,
                configured_at=self._clock.now(),
            )
        except ValueError as error:
            raise UnitLimitRefused(str(error)) from error
        async with self._work.transaction(command.tenant):
            others = [
                lim
                for lim in await self._limits.list(command.tenant)
                if lim.id != limit.id and not lim.cleared
            ]
            every = [*others, limit]
            for parent in every:
                if parent.children != "within":
                    continue
                over = _overbooked(parent, _children(parent, every))
                if over:
                    raise UnitLimitRefused(
                        f"the limits below {parent.id!r} ({parent.where()}) would together book "
                        f"more than it allows in {', '.join(over)}, and it keeps its children "
                        "within; lower them, or let it be booked over (ADR-0282 §1)"
                    )
            await self._limits.put(command.tenant, limit)
            await self._ledger.record(
                command.tenant,
                Fact(
                    kind=CONFIGURED,
                    refs=LedgerRefs(tenant=command.tenant, actor=by),
                    outcome=limit.id,
                ),
            )
        return limit

    async def clear(self, tenant: Tenant, name: str, *, by: str) -> bool:
        async with self._work.transaction(tenant):
            found = await self._limits.get(tenant, name)
            if found is None or found.cleared:
                return False
            await self._limits.put(tenant, found.model_copy(update={"cleared": True}))
            await self._ledger.record(
                tenant,
                Fact(kind=CONFIGURED, refs=LedgerRefs(tenant=tenant, actor=by), outcome="cleared"),
            )
        return True

    async def watch(self, tenant: Tenant) -> LimitWatch | None:
        async with self._work.transaction(tenant):
            return await self._watches.get(tenant, tenant)

    async def set_watch(
        self,
        tenant: Tenant,
        *,
        held_runs: int | None,
        held_seconds: float | None,
        window_days: int = 7,
        by: str,
    ) -> LimitWatch:
        watch = LimitWatch(
            id=tenant,
            tenant=tenant,
            held_runs=held_runs,
            held_seconds=held_seconds,
            window_days=window_days,
            configured_at=self._clock.now(),
        )
        async with self._work.transaction(tenant):
            await self._watches.put(tenant, watch)
            await self._ledger.record(
                tenant,
                Fact(kind=WATCHED, refs=LedgerRefs(tenant=tenant, actor=by), outcome="configured"),
            )
        return watch

    # --- the run's port ----------------------------------------------------------------------

    async def applying(self, tenant: Tenant, path: Sequence[str], process: str) -> list[UnitLimit]:
        """Every limit that holds a run of this path and process, the company first."""
        return [lim for lim in await self.all(tenant) if lim.applies(path, process)]

    def standing(
        self,
        limit: UnitLimit,
        spent: Mapping[str, float],
        daily: Mapping[date, Mapping[str, float]],
    ) -> Standing:
        """The limit's period, cost, forecast per line and the alert shares reached."""
        now = self._clock.now()
        key, start, end = period_of(limit.period, now)
        forecasts = []
        alerts = []
        for line, amount in limit.amounts.lines().items():
            per_day = {d: v.get(line, 0.0) for d, v in daily.items() if d >= start.date()}
            band = forecast(line, amount, spent.get(line, 0.0), per_day, start, end, now)
            forecasts.append(band)
            for share in limit.alert_at:
                if spent.get(line, 0.0) >= share * amount:
                    alerts.append(f"{line}:{share:g}:spent")
                elif band.high >= share * amount:
                    alerts.append(f"{line}:{share:g}:forecast")
        return Standing(limit, key, dict(spent), tuple(forecasts), tuple(alerts))

    async def observed(
        self,
        tenant: Tenant,
        name: str,
        spent: Mapping[str, float],
        daily: Mapping[date, Mapping[str, float]],
        process_version: str,
    ) -> None:
        """Raise the alerts and the anomaly the period's cost shows, each once."""
        limit = await self.get(tenant, name)
        if limit is None or limit.individually:
            return
        standing = self.standing(limit, spent, daily)
        now = self._clock.now()
        today = now.date()
        for alert in standing.alerts:
            line, share, basis = alert.split(":")
            band = next(f for f in standing.forecasts if f.line == line)
            await self._raise(
                tenant,
                IncidentKind.LIMIT_ALERT,
                f"limit:{limit.id}",
                f"{standing.period}:{alert}",
                process_version,
                rule=f"limit.alert.{basis}",
                facts={
                    "limit": limit.id,
                    "unit": limit.where(),
                    "role": limit.role,
                    "period": standing.period,
                    "line": line,
                    "share": float(share),
                    "amount": limit.amounts.lines()[line],
                    "spent": round(spent.get(line, 0.0), 6),
                    "forecast_low": band.low,
                    "forecast_high": band.high,
                    "forecast_basis": band.basis,
                },
            )
        for line in limit.amounts.lines():
            history = [
                daily.get(today - timedelta(days=i), {}).get(line, 0.0)
                for i in range(1, HISTORY_DAYS + 1)
            ]
            found = anomalous(today, daily.get(today, {}).get(line, 0.0), history)
            if found is None:
                continue
            await self._raise(
                tenant,
                IncidentKind.COST_ANOMALY,
                f"limit:{limit.id}",
                f"{today}:{line}",
                process_version,
                rule="cost.anomaly.robust_median",
                facts={
                    "limit": limit.id,
                    "unit": limit.where(),
                    "role": limit.role,
                    "line": line,
                    "day": str(found.day),
                    "cost": found.cost,
                    "median": found.median,
                    "deviation": found.deviation,
                    "threshold": found.threshold,
                    "history_days": float(found.history_days),
                },
            )

    async def refused(
        self,
        tenant: Tenant,
        name: str,
        process_version: str,
        spent: Mapping[str, float],
        demand: Mapping[str, float],
    ) -> None:
        """A step did not fit the limit: tell its role once per period, and judge from the
        ledger whether the limit does harm."""
        limit = await self.get(tenant, name)
        if limit is None:
            return
        key, _, _ = period_of(limit.period, self._clock.now())
        lines = limit.amounts.lines()
        if not limit.individually:
            await self._raise(
                tenant,
                IncidentKind.LIMIT_REACHED,
                f"limit:{limit.id}",
                key,
                process_version,
                rule="limit.admission",
                facts={
                    "limit": limit.id,
                    "unit": limit.where(),
                    "role": limit.role,
                    "period": key,
                    **{f"amount_{lim}": v for lim, v in lines.items()},
                    **{f"spent_{lim}": round(spent.get(lim, 0.0), 6) for lim in lines},
                    **{f"demand_{lim}": round(v, 6) for lim, v in demand.items() if lim in lines},
                },
            )
        await self._review(tenant, limit, key, process_version, spent, demand)

    async def _review(
        self,
        tenant: Tenant,
        limit: UnitLimit,
        key: str,
        process_version: str,
        spent: Mapping[str, float],
        demand: Mapping[str, float],
    ) -> None:
        watch = await self.watch(tenant)
        if watch is None:
            return
        # A limit held per person is judged over every person's holds together.
        names = {limit.id}
        subject = f"limit:{limit.id}"
        now = self._clock.now()
        since = now - timedelta(days=watch.window_days)
        async with self._work.transaction(tenant):
            entries = await self._ledger.of_kinds(tenant, (HELD, RELEASED), since=since)
        holds: list[Held] = []
        for entry in entries:
            if entry.kind != HELD or entry.outcome not in names or entry.refs.run_id is None:
                continue
            released = next(
                (
                    e
                    for e in entries
                    if e.kind == RELEASED
                    and e.outcome == entry.outcome
                    and e.refs.run_id == entry.refs.run_id
                    and e.seq > entry.seq
                ),
                None,
            )
            seconds = (
                (now - entry.ts).total_seconds()
                if released is None
                else float(released.duration_seconds or 0.0)
            )
            version = entry.refs.process_version or process_version
            holds.append(
                Held(
                    run_id=entry.refs.run_id,
                    process=version.split("@", 1)[0],
                    since=entry.ts,
                    seconds=max(0.0, seconds),
                )
            )
        found = harm(holds, watch)
        if found is None:
            return
        lines = limit.amounts.lines()
        facts: dict[str, str | float | None] = {
            "unit": limit.where(),
            "role": limit.role,
            "period": key,
            "held_runs": float(found.runs),
            "held_seconds": found.seconds,
            "processes": ", ".join(found.processes),
            "window_days": float(watch.window_days),
            "exceeded": found.exceeded,
            "benefit": (
                f"{found.runs} run(s) and {found.seconds:g} s held in {watch.window_days} day(s) "
                "would have gone on"
            ),
            "decision": "a person's; Taktus never changes the limit (ADR-0282 §4)",
            "limit": limit.id,
            "individually": "yes" if limit.individually else "no",
        }
        for line, amount in lines.items():
            needed = spent.get(line, 0.0) + demand.get(line, 0.0) * max(1, found.runs)
            recommended = max(amount, needed)
            facts[f"amount_{line}"] = amount
            facts[f"recommended_{line}"] = round(recommended, 6)
            facts[f"cost_{line}"] = round(recommended - amount, 6)
        await self._raise(
            tenant,
            IncidentKind.LIMIT_HARMFUL,
            subject,
            key,
            process_version,
            rule="limit.harmful",
            facts=facts,
        )

    async def _raise(
        self,
        tenant: Tenant,
        kind: IncidentKind,
        subject: str,
        key: str,
        process_version: str,
        *,
        rule: str,
        facts: Mapping[str, str | float | None],
    ) -> None:
        iid = incident_id(tenant, kind, subject, key)
        async with self._work.transaction(tenant):
            if await self._incidents.get(tenant, iid) is not None:
                return
            await self._incidents.put(
                tenant,
                Incident(
                    id=iid,
                    tenant=tenant,
                    kind=kind,
                    process_id=subject,
                    process_version=process_version,
                    rule=rule,
                    facts=dict(facts),
                    raised_at=self._clock.now(),
                ),
            )
            await self._ledger.record(
                tenant,
                Fact(
                    kind=RAISED,
                    refs=LedgerRefs(
                        tenant=tenant, process_version=process_version, incident_id=iid
                    ),
                    outcome=kind.value.replace(".", "_"),
                ),
            )
