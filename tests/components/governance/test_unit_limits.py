"""The rules that watch a unit limit: periods, the forecast band, the anomaly, the harm, and a
limit held per person that tells no role (ADR-0282, UC-8.5, UC-8.10)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fakes import FakeClock

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.governance.application.service.unit_limits import (
    SetUnitLimit,
    UnitLimits,
)
from taktus.components.governance.domain.model.incident import Incident, IncidentKind
from taktus.components.governance.domain.model.unit_limits import (
    Held,
    LimitWatch,
    UnitLimit,
    anomalous,
    forecast,
    harm,
    period_of,
)
from taktus.components.ledger.application.service import ChainedLedger
from taktus.ports.persistence import Tenant

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
TENANT = "t"


def test_periods_are_a_day_an_iso_week_or_a_month_in_utc() -> None:
    assert period_of("day", NOW)[0] == "2026-11-11"
    key, start, end = period_of("week", NOW)
    assert key == "2026-W46" and start.date() == date(2026, 11, 9) and end - start == timedelta(7)
    key, start, end = period_of("month", NOW)
    assert key == "2026-11" and start.day == 1 and end == datetime(2026, 12, 1, tzinfo=UTC)
    assert period_of("month", datetime(2026, 12, 31, tzinfo=UTC))[2].year == 2027


def test_a_forecast_is_a_band_and_says_what_it_was_computed_from() -> None:
    _, start, end = period_of("month", NOW)
    daily = {start.date() + timedelta(days=i): 1.0 + (i % 3) for i in range(11)}
    spent = sum(daily.values())
    band = forecast("money.eur", 40.0, spent, daily, start, end, NOW)
    assert spent < band.low < band.high, "a band, never a point, never below what is spent"
    assert band.days == 11 and band.first_day == date(2026, 11, 1)
    assert band.last_day == date(2026, 11, 11)
    assert "11 day(s)" in band.basis and "not counted" in band.basis
    assert band.reached_earliest is not None and band.reached_latest is not None
    assert band.reached_earliest <= band.reached_latest, "the upper edge reaches it first"
    far = forecast("money.eur", 10_000.0, spent, daily, start, end, NOW)
    assert far.reached_earliest is None, "not within the period"


def test_an_anomaly_is_a_day_far_above_the_robust_median_of_the_days_before() -> None:
    history = [1.0, 1.2, 0.9, 1.1, 1.0, 0.8, 1.3, 1.0, 1.1, 0.9]
    found = anomalous(date(2026, 11, 11), 10.0, history)
    assert found is not None and found.cost > found.threshold > found.median
    assert anomalous(date(2026, 11, 11), 1.4, history) is None, "within the unit's history"
    assert anomalous(date(2026, 11, 11), 10.0, history[:5]) is None, "too little history"
    assert anomalous(date(2026, 11, 11), 0.0, history) is None


def test_a_limit_does_harm_where_it_held_more_runs_or_longer_than_the_watch() -> None:
    watch = LimitWatch(id=TENANT, tenant=TENANT, held_runs=3, held_seconds=600, configured_at=NOW)
    holds = [Held(run_id=f"r{i}", process="p", since=NOW, seconds=100) for i in range(2)]
    assert harm(holds, watch) is None
    longer = [*holds, Held(run_id="r0", process="q", since=NOW, seconds=500)]
    found = harm(longer, watch)
    assert found is not None and found.exceeded == "seconds" and found.runs == 2
    assert found.processes == ("p", "q")


async def _person(tenant: Tenant, name: str) -> bool:
    return name.startswith("idn_")


def service() -> tuple[UnitLimits, MemoryRepository[Incident], FakeClock, MemoryPersistence]:
    clock = FakeClock(NOW)
    persistence = MemoryPersistence()
    incidents = MemoryRepository(persistence, Incident)
    limits = UnitLimits(
        MemoryRepository(persistence, UnitLimit),
        MemoryRepository(persistence, LimitWatch),
        incidents,
        ChainedLedger(MemoryLedgerStore(persistence), clock),
        persistence,
        clock,
        _person,
    )
    return limits, incidents, clock, persistence


async def test_a_day_far_above_its_history_raises_an_anomaly_to_the_role_once() -> None:
    limits, incidents, clock, persistence = service()
    await limits.set(
        SetUnitLimit(tenant=TENANT, name="sales", role="sales-lead", unit=("sales",), tokens=10**9),
        by="idn_owner",
    )
    today = clock.current.date()
    daily = {today - timedelta(days=i): {"tokens": 1000.0 + 10 * i} for i in range(1, 15)}
    daily[today] = {"tokens": 50_000.0}
    for _ in range(2):
        await limits.observed(TENANT, "sales", {"tokens": 60_000.0}, daily, "p@1")
    async with persistence.transaction(TENANT):
        found = [i for i in await incidents.list(TENANT) if i.kind is IncidentKind.COST_ANOMALY]
    [anomaly] = found
    assert anomaly.facts["role"] == "sales-lead" and anomaly.facts["line"] == "tokens"
    assert anomaly.rule == "cost.anomaly.robust_median"


async def test_a_forecast_that_reaches_the_share_alerts_before_the_cost_does() -> None:
    limits, incidents, clock, persistence = service()
    await limits.set(
        SetUnitLimit(
            tenant=TENANT, name="sales", role="sales-lead", unit=("sales",), money={"eur": 100.0}
        ),
        by="idn_owner",
    )
    _, start, _ = period_of("month", clock.current)
    daily = {start.date() + timedelta(days=i): {"money.eur": 5.0} for i in range(11)}
    await limits.observed(TENANT, "sales", {"money.eur": 55.0}, daily, "p@1")
    async with persistence.transaction(TENANT):
        [alert] = [i for i in await incidents.list(TENANT) if i.kind is IncidentKind.LIMIT_ALERT]
    assert alert.rule == "limit.alert.forecast", "55 of 100 spent, the forecast reaches 80"
    assert alert.facts["forecast_high"] >= 80.0  # type: ignore[operator]


async def test_a_limit_held_per_person_raises_no_alert_to_a_role() -> None:
    limits, incidents, clock, persistence = service()
    await limits.set(
        SetUnitLimit(
            tenant=TENANT, name="each", role="lead", unit=("sales",), individually=True, tokens=10
        ),
        by="idn_owner",
    )
    today = clock.current.date()
    await limits.observed(TENANT, "each", {"tokens": 10.0}, {today: {"tokens": 10.0}}, "p@1")
    async with persistence.transaction(TENANT):
        assert await incidents.list(TENANT) == [], "what one person spent is theirs alone"
    stored = await limits.get(TENANT, "each")
    assert stored is not None and "idn" not in str(stored.document()), "it names no one"
