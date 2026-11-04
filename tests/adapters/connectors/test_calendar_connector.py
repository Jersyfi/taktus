"""The calendar connector lists a calendar's entries within a window, from an iCalendar file or
over CalDAV, repeating entries expanded where their rule is plain (ADR-0197, UC-03 B-10.01).

Against `tests/fakes/calendar_service.py` in a thread of this process; the connector is served
in-process over MCP, as an instance reaches it.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fakes import calendar_service
from taktus_connectors.calendar import icalendar
from taktus_connectors.calendar.operations import Config
from taktus_connectors.calendar.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "tok-" + secrets.token_hex(8)
WINDOW = {"from": "2026-11-01", "days": 90}
EXPECTED = [
    ("vat-monthly@deadlines.example", "2026-11-12T00:00:00Z", "Advance VAT return (moved)"),
    (
        "office-notice@deadlines.example",
        "2026-11-30T17:00:00Z",
        "Notice period of the office lease ends",
    ),
    ("hosting-renewal@deadlines.example", "2026-12-15T09:00:00Z", "Hosting contract renews"),
    ("vat-monthly@deadlines.example", "2027-01-10T00:00:00Z", "Advance VAT return"),
    ("vat-yearly@deadlines.example", "2027-01-10T00:00:00Z", "VAT return for the year"),
]  # fmt: skip


@pytest.fixture
def credential(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    path = tmp_path / "calendar_token"
    path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_CALENDAR_TOKEN_FILE", str(path))
    yield path


@pytest.fixture
def server(credential: Path) -> Iterator[str]:
    running = calendar_service.make_server("127.0.0.1", 0, {TOKEN, "planner:pw-1"})
    threading.Thread(target=running.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{running.server_address[1]}"
    running.shutdown()
    running.server_close()


def context() -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_ops",
        run_id="run_read",
        step_id="read",
        attempt=1,
        idempotency_key=idempotency_key("run_read", "read", 1),
        credentials=(CredentialReference(name="CALENDAR_TOKEN", injected_as="env"),),
    )


def connector(url: str, *, caldav: bool = False) -> McpActionConnector:
    return McpActionConnector(build_server(Config(url, caldav=caldav, timeout=5.0)))


def replace(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def moments(output: dict[str, object]) -> list[tuple[str, str, str]]:
    entries = output["entries"]
    assert isinstance(entries, list)
    return [(e["uid"], e.get("start") or e["due"], e["summary"]) for e in entries]


@pytest.mark.parametrize(
    ("caldav", "path"), [(False, "/calendars/deadlines.ics"), (True, "/calendars/deadlines/")]
)
async def test_the_deadlines_of_the_window_are_listed_in_order_from_a_file_and_over_caldav(
    server: str, caldav: bool, path: str
) -> None:
    result = await connector(server, caldav=caldav).call(
        "calendar.events.list", context(), {"path": path, **WINDOW}
    )
    out = result.output
    assert result.effect.kind.value == "read"
    assert moments(out) == EXPECTED
    assert out["from"] == "2026-11-01T00:00:00Z" and out["until"] == "2027-01-30T00:00:00Z"
    assert out["complete"] is True
    [unread] = out["unread"]
    assert unread["uid"] == "payroll@deadlines.example" and "BYDAY" in unread["reason"]
    notice = out["entries"][1]
    assert notice["kind"] == "todo" and notice["categories"] == ["contract", "notice"]
    assert notice["key"] == "office-notice@deadlines.example@2026-11-30T17:00:00Z"
    hosting = out["entries"][2]
    assert hosting["end"] == "2026-12-15T09:30:00Z" and hosting["repeats"] is True
    yearly = out["entries"][4]
    assert yearly["description"] == "Filed with the tax office, signed by the managing director."
    assert yearly["all_day"] is True
    assert result.consumption is not None
    assert result.consumption.quota_units == (2 if caldav else 1)


async def test_basic_authentication_is_sent_for_a_user_and_password(
    server: str, credential: Path
) -> None:
    replace(credential, "planner:pw-1")
    result = await connector(server).call(
        "calendar.events.list", context(), {"path": "/calendars/deadlines.ics", **WINDOW}
    )
    assert len(result.output["entries"]) == len(EXPECTED)


async def test_the_limit_cuts_and_says_so(server: str) -> None:
    out = (
        await connector(server).call(
            "calendar.events.list",
            context(),
            {"path": "/calendars/deadlines.ics", **WINDOW, "limit": 2},
        )
    ).output
    assert moments(out) == EXPECTED[:2] and out["complete"] is False


@pytest.mark.parametrize(
    ("input", "cause"),
    [
        ({"path": "https://elsewhere.example/x.ics"}, "invalid"),
        ({"path": "/calendars/../etc"}, "invalid"),
        ({"path": "/calendars/deadlines.ics", "days": 0}, "invalid"),
        ({"path": "/calendars/deadlines.ics", "from": "tomorrow"}, "invalid"),
        ({"path": "/calendars/other.ics"}, "not_found"),
    ],
)
async def test_what_cannot_be_asked_or_is_not_there_fails_by_its_cause(
    server: str, input: dict[str, object], cause: str
) -> None:
    with pytest.raises(CallFailed) as failed:
        await connector(server).call("calendar.events.list", context(), input)
    assert failed.value.error.cause.value == cause


async def test_a_credential_the_server_does_not_admit_is_unauthenticated(
    server: str, credential: Path
) -> None:
    replace(credential, "tok-wrong")
    with pytest.raises(CallFailed) as failed:
        await connector(server).call(
            "calendar.events.list", context(), {"path": "/calendars/deadlines.ics"}
        )
    assert failed.value.error.cause.value == "unauthenticated"


# --- reading iCalendar ---------------------------------------------------------------------------

UTC_ZONE = ZoneInfo("UTC")


def read(body: str, start: str, end: str) -> dict[str, object]:
    text = f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\n{body}END:VCALENDAR\r\n"
    return icalendar.entries(
        text,
        datetime.fromisoformat(start).replace(tzinfo=UTC),
        datetime.fromisoformat(end).replace(tzinfo=UTC),
        UTC_ZONE,
    )


def test_a_month_without_the_starts_day_has_no_occurrence() -> None:
    body = (
        "BEGIN:VEVENT\r\nUID:a\r\nDTSTART;VALUE=DATE:20260131\r\n"
        "RRULE:FREQ=MONTHLY\r\nEND:VEVENT\r\n"
    )
    found = read(body, "2026-01-01", "2026-06-01")["entries"]
    assert isinstance(found, list)
    assert [e["start"][:10] for e in found] == ["2026-01-31", "2026-03-31", "2026-05-31"]


def test_count_until_and_interval_bound_a_rule() -> None:
    start = "BEGIN:VEVENT\r\nUID:c\r\nDTSTART:20260101T080000Z\r\n"
    counted = start + "RRULE:FREQ=WEEKLY;INTERVAL=2;COUNT=3\r\nEND:VEVENT\r\n"
    until = start + "RRULE:FREQ=DAILY;UNTIL=20260103T080000Z\r\nEND:VEVENT\r\n"
    weekly = read(counted, "2026-01-01", "2027-01-01")["entries"]
    daily = read(until, "2026-01-01", "2027-01-01")["entries"]
    assert isinstance(weekly, list) and isinstance(daily, list)
    assert [e["start"] for e in weekly] == [
        "2026-01-01T08:00:00Z", "2026-01-15T08:00:00Z", "2026-01-29T08:00:00Z",
    ]  # fmt: skip
    assert len(daily) == 3


def test_a_monthly_time_in_a_zone_keeps_its_local_hour_across_daylight_saving() -> None:
    body = (
        "BEGIN:VEVENT\r\nUID:z\r\nDTSTART;TZID=Europe/Berlin:20260310T090000\r\n"
        "RRULE:FREQ=MONTHLY;COUNT=2\r\nEND:VEVENT\r\n"
    )
    found = read(body, "2026-01-01", "2027-01-01")["entries"]
    assert isinstance(found, list)
    assert [e["start"] for e in found] == ["2026-03-10T08:00:00Z", "2026-04-10T07:00:00Z"]


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ("BEGIN:VEVENT\r\nDTSTART:20260101T080000Z\r\nEND:VEVENT\r\n", "no UID"),
        ("BEGIN:VEVENT\r\nUID:n\r\nSUMMARY:x\r\nEND:VEVENT\r\n", "no start"),
        ("BEGIN:VEVENT\r\nUID:t\r\nDTSTART;TZID=Mars/Olympus:20260101T080000\r\nEND:VEVENT\r\n",
         "zone"),
        ("BEGIN:VEVENT\r\nUID:h\r\nDTSTART:20260101T080000Z\r\nRRULE:FREQ=HOURLY\r\nEND:VEVENT\r\n",
         "frequency"),
    ],
)  # fmt: skip
def test_an_entry_that_is_not_read_is_named_with_the_reason(body: str, reason: str) -> None:
    out = read(body, "2026-01-01", "2027-01-01")
    assert out["entries"] == []
    [unread] = out["unread"]  # type: ignore[misc]
    assert reason in unread["reason"]


def test_a_text_that_is_not_icalendar_is_refused() -> None:
    with pytest.raises(icalendar.Unreadable):
        icalendar.entries("<html></html>", datetime.now(UTC), datetime.now(UTC), UTC_ZONE)
