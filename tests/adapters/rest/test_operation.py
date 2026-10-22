"""What keeps the operation running, on the control plane's surface (ADR-0121, issue #562).

The incidents and the signals are read by every reader who may see their process, through the
one predicate. The alerts, the backup and the daily report are reports to the owner: the owner
and the people the owner named read them. The start page's summary carries a figure only for
what its reader may read. No answer names a person (principle 14).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from taktus.components.governance.domain.model import (
    Happening,
    Incident,
    IncidentKind,
    IncidentState,
    RunSeen,
)
from taktus.components.reporting.application.service import (
    Alerted,
    BackupWatched,
    ConfigureChannel,
    RaiseReport,
)
from taktus.components.reporting.domain.model import (
    BackupRun,
    BackupState,
    ClaimLost,
    Corridor,
    Judged,
    Level,
    ProcessRef,
    Reader,
    ReportKind,
)
from taktus.components.reporting.domain.service import alerts as rule
from taktus.components.reporting.domain.service import visibility

from .conftest import OTHER, TENANT, Services
from .test_surface import is_problem

type Client = tuple[httpx.AsyncClient, Services, str]

OWNER = "idn_owner"
NAMED = "idn_deputy"
OUTSIDER = "idn_outsider"
NOW = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)
ROUTES = (
    "/operation",
    "/incidents",
    "/alerts",
    "/backup",
    "/signals",
    "/signals/daily-report",
)
OWNERS_ONLY = ("/alerts", "/backup", "/signals/daily-report")


def missing(tenant: str = TENANT, process: str = "watch") -> Incident:
    return Incident(
        id=f"inc_{process}",
        tenant=tenant,
        kind=IncidentKind.MISSING,
        process_id=process,
        process_version=f"{process}@1",
        expected_at=NOW - 2 * HOUR,
        last_run=RunSeen(at=NOW - 3 * HOUR, run_id=f"run_{process}_3", kind="run.started"),
        rule="expected.slot",
        facts={"schedule": "0 * * * *"},
        raised_at=NOW - HOUR,
        timeline=(
            Happening(
                at=NOW - HOUR,
                what="missed",
                expected_at=NOW - 2 * HOUR,
                deadline=NOW - 2 * HOUR + timedelta(minutes=15),
            ),
            Happening(
                at=NOW,
                what="happened",
                run=RunSeen(at=NOW, run_id=f"run_{process}_4", kind="run.started"),
            ),
        ),
    )


def overdue_closed() -> Incident:
    return Incident(
        id="inc_overdue",
        tenant=TENANT,
        kind=IncidentKind.OVERDUE,
        process_id="orders",
        process_version="orders@2",
        expected_at=NOW - 30 * HOUR,
        run_id="run_orders_1",
        rule="expected.bound",
        raised_at=NOW - 29 * HOUR,
        state=IncidentState.CLOSED,
        closed_at=NOW - 20 * HOUR,
        timeline=(Happening(at=NOW - 20 * HOUR, what="closed"),),
    )


def corridor(signal: str, process: str, tenant: str = TENANT) -> Corridor:
    return Corridor.model_validate(
        {
            "id": f"{signal}@1",
            "tenant": tenant,
            "signal": signal,
            "version": 1,
            "process": process,
            "step": "count",
            "about": {"kind": "department", "name": "support"},
            "bounds": "fixed",
            "yellow": 5,
            "red": 10,
            "role": "sales",
            "case": f"https://tracker.example/cases/{signal}",
            "changed_at": NOW - 240 * HOUR,
        }
    )


def judged(c: Corridor, level: Level, value: float | None = None) -> Judged:
    measured = value is not None
    return Judged(
        signal=c.signal,
        corridor=c.id,
        level=level,
        reason=None if measured else "no_measurement",
        value=value,
        yellow_at=5.0 if measured else None,
        red_at=10.0 if measured else None,
        run_id=f"run_{c.process}_9" if measured else None,
        step_id="count" if measured else None,
        process_version=f"{c.process}@2" if measured else None,
        at=NOW - HOUR if measured else None,
    )


def failing_backup() -> BackupWatched:
    state = BackupState(
        watched_since=NOW - 240 * HOUR,
        expected_hours=26,
        last_ok=BackupRun(name="taktus-20261021T020000Z", at=NOW - 31 * HOUR),
        failed=(BackupRun(name="taktus-20261022T020000Z", at=NOW - 7 * HOUR, reason="store"),),
        failed_count=1,
    )
    return BackupWatched(
        state=state, next_due=rule.backup_due(state), alert=rule.backup(state, NOW)
    )


def lost_claim() -> Alerted:
    [alert] = rule.claims_lost([ClaimLost(seq=7, at=NOW - 4 * HOUR, run_id="run_orders_1")], {})
    return Alerted(alert=alert, report=None, closed=False, delivered=False, reason="no_channel")


async def readers(given: Services) -> dict[str, dict[str, str]]:
    """The owner, someone the owner named, and a reader of the tenant who is neither; and the
    records of both tenants."""
    keys: dict[str, dict[str, str]] = {}
    for name in (OWNER, NAMED, OUTSIDER):
        _, key = await given.identities.add(TENANT, name, (TENANT,), roles=("owner",))
        keys[name] = {"Authorization": f"Bearer {key}"}
    await given.owner.configure.execute(
        ConfigureChannel(
            tenant=TENANT,
            document={
                "owner": OWNER,
                "named": [NAMED],
                "channel": "channel.repo",
                "address": "acme/taktus#412",
                "language": "en",
            },
            actor="operator",
        )
    )
    late, open_ = corridor("orders.late", "orders"), corridor("tickets.open", "tickets")
    stock = corridor("stock.low", "stock")
    operation = given.operation
    operation.incidents_of[TENANT] = [missing(), overdue_closed()]
    operation.incidents_of[OTHER] = [missing(OTHER, "elsewhere")]
    operation.signals_of[TENANT] = [
        (late, judged(late, Level.RED, 12.0)),
        (open_, judged(open_, Level.YELLOW, 7.0)),
        (stock, judged(stock, Level.UNMEASURED)),
    ]
    elsewhere = corridor("elsewhere.count", "elsewhere", OTHER)
    operation.signals_of[OTHER] = [(elsewhere, judged(elsewhere, Level.RED, 99.0))]
    operation.alerts_of[TENANT] = [lost_claim()]
    operation.backup_of[TENANT] = failing_backup()
    return keys


async def daily(given: Services, day: int) -> None:
    await given.owner.raising.execute(
        RaiseReport(
            tenant=TENANT,
            id=f"signals-2026-10-{day:02d}",
            kind=ReportKind.SIGNALS,
            title=f"Daily report of 2026-10-{day:02d}",
            needed=["orders.late is red: 12 above 10, run run_orders_9, step count."],
            steps=["Open the case each line names."],
            standing_still=["1 red signal has an open incident."],
            due=NOW.date(),
        )
    )


async def test_every_route_needs_an_account_key(client: Client) -> None:
    http, given, base = client
    await readers(given)
    for path in ROUTES:
        is_problem(await http.get(f"{base}{path}"), 401)
        is_problem(await http.get(f"{base}{path}", headers={"Authorization": "Bearer no"}), 401)


async def test_the_reports_are_read_by_the_owner_and_whom_the_owner_named_only(
    client: Client,
) -> None:
    http, given, base = client
    keys = await readers(given)
    await daily(given, 22)
    for path in OWNERS_ONLY:
        is_problem(await http.get(f"{base}{path}", headers=keys[OUTSIDER]), 403)
        assert (await http.get(f"{base}{path}", headers=keys[OWNER])).status_code == 200
        assert (await http.get(f"{base}{path}", headers=keys[NAMED])).status_code == 200
    for path in ("/incidents", "/signals"):
        assert (await http.get(f"{base}{path}", headers=keys[OUTSIDER])).status_code == 200


async def test_the_start_page_carries_one_entry_per_kind_with_how_many_are_open_or_red(
    client: Client,
) -> None:
    http, given, base = client
    keys = await readers(given)
    await daily(given, 22)
    seen = (await http.get(f"{base}/operation", headers=keys[OWNER])).json()
    assert seen["incidents"] == {"readable": True, "open": 1, "total": 2}
    assert seen["signals"] == {
        "readable": True,
        "red": 1,
        "yellow": 1,
        "unmeasured": 1,
        "total": 3,
    }
    assert seen["alerts"] == {"readable": True, "in_effect": 1, "total": 1}
    assert seen["backup"]["standing"] == "failing"
    assert seen["backup"]["next_due"] == (NOW - 31 * HOUR + 26 * HOUR).isoformat()
    assert seen["daily_report"]["id"] == "signals-2026-10-22"
    withheld = (await http.get(f"{base}/operation", headers=keys[OUTSIDER])).json()
    assert withheld["incidents"] == seen["incidents"]
    for kind in ("alerts", "backup", "daily_report"):
        assert withheld[kind] == {"readable": False}, "no figure of what the reader may not read"


async def test_an_incident_says_what_was_expected_and_links_its_runs_and_process(
    client: Client,
) -> None:
    http, given, base = client
    keys = await readers(given)
    found = (await http.get(f"{base}/incidents", headers=keys[OUTSIDER])).json()["incidents"]
    assert [i["id"] for i in found] == ["inc_watch", "inc_overdue"]
    watch, closed = found
    assert watch["state"] == "open" and watch["kind"] == "run.missing"
    assert watch["process_id"] == "watch" and watch["process_version"] == "watch@1"
    assert watch["expected_at"] == (NOW - 2 * HOUR).isoformat()
    assert watch["last_run"]["run_id"] == "run_watch_3"
    assert [h["what"] for h in watch["timeline"]] == ["missed", "happened"]
    assert watch["timeline"][1]["run_id"] == "run_watch_4"
    assert closed["state"] == "closed" and closed["run_id"] == "run_orders_1"
    assert closed["closed_at"] == (NOW - 20 * HOUR).isoformat()


async def test_an_alert_names_the_runs_it_is_about_and_what_became_of_its_report(
    client: Client,
) -> None:
    http, given, base = client
    keys = await readers(given)
    [alert] = (await http.get(f"{base}/alerts", headers=keys[OWNER])).json()["alerts"]
    assert alert["kind"] == "claim_lost" and alert["in_effect"] is True
    assert alert["about"] == [{"run_id": "run_orders_1"}]
    assert alert["delivered"] is False and alert["reason"] == "no_channel"
    assert alert["state"].startswith("not delivered")


async def test_the_backup_says_its_last_outcome_and_by_when_the_next_is_due(
    client: Client,
) -> None:
    http, given, base = client
    keys = await readers(given)
    backup = (await http.get(f"{base}/backup", headers=keys[OWNER])).json()
    assert backup["standing"] == "failing" and backup["watched"] is True
    assert backup["last_ok"]["name"] == "taktus-20261021T020000Z"
    assert backup["newest_failed"] == {
        "name": "taktus-20261022T020000Z",
        "at": (NOW - 7 * HOUR).isoformat(),
        "reason": "store",
    }
    assert backup["next_due"] == (NOW + 5 * HOUR - 10 * HOUR).isoformat()
    assert backup["alert"]["title"] == "The instance's backup failed"


async def test_a_signal_is_judged_beside_its_corridor_and_links_the_run_that_measured_it(
    client: Client,
) -> None:
    http, given, base = client
    keys = await readers(given)
    found = (await http.get(f"{base}/signals", headers=keys[OUTSIDER])).json()["signals"]
    assert [(s["signal"], s["level"]) for s in found] == [
        ("orders.late", "red"),
        ("tickets.open", "yellow"),
        ("stock.low", "unmeasured"),
    ]
    late = found[0]
    assert (late["value"], late["yellow_at"], late["red_at"]) == (12.0, 5.0, 10.0)
    assert (late["run_id"], late["step_id"], late["process_version"]) == (
        "run_orders_9",
        "count",
        "orders@2",
    )
    assert late["role"] == "sales" and late["about"] == {"kind": "department", "name": "support"}
    assert found[2]["reason"] == "no_measurement" and found[2]["run_id"] is None


async def test_the_newest_daily_report_is_answered_and_none_before_the_first(
    client: Client,
) -> None:
    http, given, base = client
    keys = await readers(given)
    is_problem(await http.get(f"{base}/signals/daily-report", headers=keys[OWNER]), 404)
    await daily(given, 21)
    await daily(given, 22)
    report = (await http.get(f"{base}/signals/daily-report", headers=keys[OWNER])).json()
    assert report["id"] == "signals-2026-10-22" and report["kind"] == "signals"
    assert report["needed"] == ["orders.late is red: 12 above 10, run run_orders_9, step count."]


async def test_a_record_whose_process_the_predicate_withholds_is_absent_and_not_counted(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    http, given, base = client
    keys = await readers(given)
    original = visibility.may_see_process

    def narrowed(reader: Reader, process: ProcessRef) -> bool:
        return process.id not in {"watch", "orders"} and original(reader, process)

    monkeypatch.setattr(visibility, "may_see_process", narrowed)
    incidents = (await http.get(f"{base}/incidents", headers=keys[OWNER])).json()["incidents"]
    signals = (await http.get(f"{base}/signals", headers=keys[OWNER])).json()["signals"]
    seen = (await http.get(f"{base}/operation", headers=keys[OWNER])).json()
    assert incidents == []
    assert [s["signal"] for s in signals] == ["tickets.open", "stock.low"]
    assert seen["incidents"] == {"readable": True, "open": 0, "total": 0}
    assert seen["signals"]["red"] == 0 and seen["signals"]["total"] == 2


async def test_another_tenants_records_are_never_read(client: Client) -> None:
    http, given, base = client
    keys = await readers(given)
    for path in ("/incidents", "/signals", "/operation"):
        body = (await http.get(f"{base}{path}", headers=keys[OWNER])).text
        assert "elsewhere" not in body


async def test_no_answer_names_a_person(client: Client) -> None:
    http, given, base = client
    keys = await readers(given)
    await daily(given, 22)
    for path in ROUTES:
        body = json.dumps((await http.get(f"{base}{path}", headers=keys[OWNER])).json())
        for name in (OWNER, NAMED, OUTSIDER):
            assert name not in body, f"{path} names {name}"
