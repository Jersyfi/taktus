"""The entries of an iCalendar text (RFC 5545) whose moment falls within a window.

What is read is what a deadline needs: of every `VEVENT` and `VTODO`, its `UID`, `SUMMARY`,
`DESCRIPTION`, `CATEGORIES`, `DTSTART`, `DTEND` or `DUE`, `RRULE`, `EXDATE` and
`RECURRENCE-ID`. An entry's moment is its start, or its due for a to-do (ADR-0197 §3).

- A date without a time (`VALUE=DATE`) is all day, at the start of the day in the zone given.
- A time with `TZID` is read in that zone from the time zone database; a time ending in `Z` is
  UTC; a time without either is read in the zone given.
- A rule is expanded when it has `FREQ` of `DAILY`, `WEEKLY`, `MONTHLY` or `YEARLY` and no part
  but `INTERVAL`, `COUNT`, `UNTIL` and `WKST`. A month or a year without the start's day — the
  31st, the 29th of February — has no occurrence, as RFC 5545 §3.3.10 counts it. `EXDATE`
  removes an occurrence. An entry with `RECURRENCE-ID` replaces its rule's occurrence at that
  moment.
- An entry that cannot be read this way — a rule with another part, a zone the database does
  not know, no moment — is answered under `unread` with the reason, never guessed.

Every moment is answered in UTC. Nothing here makes a request.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

type Json = dict[str, Any]

FREQUENCIES = frozenset({"DAILY", "WEEKLY", "MONTHLY", "YEARLY"})
RULE_PARTS = frozenset({"FREQ", "INTERVAL", "COUNT", "UNTIL", "WKST"})
STEPS = 100_000
"""The most occurrences one rule is stepped through before it is left unread."""
DESCRIPTION = 2000
"""The most characters of a description that are answered."""
DATE = re.compile(r"^\d{8}$")
DATETIME = re.compile(r"^(\d{8})T(\d{6})(Z?)$")


class Unreadable(ValueError):
    """An entry this module does not read; the message says why."""


@dataclass
class Property:
    value: str
    params: dict[str, str]


@dataclass
class Component:
    kind: str
    props: dict[str, list[Property]] = field(default_factory=dict)

    def first(self, name: str) -> Property | None:
        found = self.props.get(name)
        return found[0] if found else None


def _unfolded(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif raw:
            lines.append(raw)
    return lines


def _split(line: str) -> tuple[str, dict[str, str], str]:
    """A content line's name, parameters and value; a quoted parameter may hold `:` and `;`."""
    quoted = False
    for i, c in enumerate(line):
        if c == '"':
            quoted = not quoted
        elif c == ":" and not quoted:
            head, value = line[:i], line[i + 1 :]
            break
    else:
        raise Unreadable("a content line without a value")
    parts: list[str] = []
    current, quoted = "", False
    for c in head:
        if c == '"':
            quoted = not quoted
        if c == ";" and not quoted:
            parts.append(current)
            current = ""
        else:
            current += c
    parts.append(current)
    params: dict[str, str] = {}
    for part in parts[1:]:
        key, _, val = part.partition("=")
        params[key.upper()] = val.strip('"')
    return parts[0].upper(), params, value


def components(text: str) -> list[Component]:
    """Every `VEVENT` and `VTODO` of the text; anything nested in them, such as an alarm, is
    not theirs."""
    lines = _unfolded(text)
    if not lines or lines[0].strip().upper() != "BEGIN:VCALENDAR":
        raise Unreadable("the text is not an iCalendar object")
    found: list[Component] = []
    stack: list[str] = []
    current: Component | None = None
    for line in lines:
        try:
            name, params, value = _split(line)
        except Unreadable:
            continue
        if name == "BEGIN":
            stack.append(value.upper())
            if value.upper() in ("VEVENT", "VTODO") and current is None:
                current = Component(value.upper())
            continue
        if name == "END":
            ended = stack.pop() if stack else ""
            if current is not None and ended == current.kind:
                found.append(current)
                current = None
            continue
        if current is not None and stack and stack[-1] == current.kind:
            current.props.setdefault(name, []).append(Property(value, params))
    return found


def _text(value: str) -> str:
    out, escaped = [], False
    for c in value:
        if escaped:
            out.append("\n" if c in "nN" else c)
            escaped = False
        elif c == "\\":
            escaped = True
        else:
            out.append(c)
    return "".join(out)


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise Unreadable(f"the zone {name!r} is not one the time zone database knows") from error


def moment(prop: Property, zone: ZoneInfo) -> tuple[datetime, bool]:
    """The moment a property names, in UTC, and whether it is a whole day."""
    try:
        return _moment(prop, zone)
    except ValueError as error:
        if isinstance(error, Unreadable):
            raise
        raise Unreadable(f"{prop.value!r} is not a moment of the calendar") from error


def _moment(prop: Property, zone: ZoneInfo) -> tuple[datetime, bool]:
    value = prop.value.strip().split(",")[0]
    if prop.params.get("VALUE", "").upper() == "DATE" or DATE.match(value):
        if not DATE.match(value):
            raise Unreadable(f"{value!r} is not a date")
        day = date(int(value[:4]), int(value[4:6]), int(value[6:]))
        there = _zone(prop.params["TZID"]) if "TZID" in prop.params else zone
        local = datetime.combine(day, time(), tzinfo=there)
        return local.astimezone(UTC), True
    match = DATETIME.match(value)
    if match is None:
        raise Unreadable(f"{value!r} is neither a date nor a date with a time")
    d, t, utc = match.groups()
    naive = datetime(int(d[:4]), int(d[4:6]), int(d[6:]), int(t[:2]), int(t[2:4]), int(t[4:]))
    if utc:
        return naive.replace(tzinfo=UTC), False
    there = _zone(prop.params["TZID"]) if "TZID" in prop.params else zone
    return naive.replace(tzinfo=there).astimezone(UTC), False


def _rule(text: str) -> dict[str, str]:
    parts = {}
    for part in text.split(";"):
        key, _, value = part.partition("=")
        parts[key.strip().upper()] = value.strip().upper()
    if parts.get("FREQ") not in FREQUENCIES:
        raise Unreadable(f"the rule's frequency {parts.get('FREQ')!r} is not expanded")
    other = set(parts) - RULE_PARTS
    if other:
        raise Unreadable(f"the rule's parts {', '.join(sorted(other))} are not expanded")
    return parts


def _shifted(start: datetime, freq: str, n: int) -> datetime | None:
    """The n-th step of a rule from its start in the start's own zone; None where the step's
    month or year has no such day."""
    if freq == "DAILY":
        return start + timedelta(days=n)
    if freq == "WEEKLY":
        return start + timedelta(weeks=n)
    months = n if freq == "MONTHLY" else 12 * n
    year, month = divmod(start.month - 1 + months, 12)
    try:
        return start.replace(year=start.year + year, month=month + 1)
    except ValueError:
        return None


def occurrences(
    start: datetime, rule: str | None, end: datetime, zone: ZoneInfo, start_prop: Property
) -> list[datetime]:
    """Every occurrence of an entry from its start up to `end`, in UTC."""
    if rule is None:
        return [start] if start < end else []
    parts = _rule(rule)
    try:
        interval = int(parts.get("INTERVAL", "1") or "1")
        count = int(parts["COUNT"]) if "COUNT" in parts else None
    except ValueError as error:
        raise Unreadable("the rule's INTERVAL or COUNT is not a whole number") from error
    if interval < 1:
        raise Unreadable("the rule's INTERVAL is not positive")
    until = moment(Property(parts["UNTIL"], {}), zone)[0] if "UNTIL" in parts else None
    # Steps are taken in the start's own zone, so that a monthly 9 o'clock stays 9 o'clock.
    there = _zone(start_prop.params["TZID"]) if "TZID" in start_prop.params else zone
    local = start.astimezone(there)
    found: list[datetime] = []
    counted = 0
    for n in range(STEPS):
        step = _shifted(local, parts["FREQ"], n * interval)
        if step is None:
            continue
        at = step.astimezone(UTC)
        if at >= end or (until is not None and at > until):
            return found
        counted += 1
        found.append(at)
        if count is not None and counted >= count:
            return found
    raise Unreadable(f"the rule has more than {STEPS} occurrences before the window ends")


def _excluded(component: Component, zone: ZoneInfo) -> set[datetime]:
    excluded: set[datetime] = set()
    for prop in component.props.get("EXDATE", []):
        for value in prop.value.split(","):
            excluded.add(moment(Property(value, prop.params), zone)[0])
    return excluded


def _summary(component: Component) -> str | None:
    prop = component.first("SUMMARY")
    return _text(prop.value) if prop else None


def entries(text: str, start: datetime, end: datetime, zone: ZoneInfo) -> Json:
    """The entries whose moment lies in [start, end), ordered by moment, and those not read."""
    found: list[Json] = []
    unread: list[Json] = []
    moved: set[tuple[str, datetime]] = set()
    parsed = components(text)
    for component in parsed:
        rid = component.first("RECURRENCE-ID")
        owner = component.first("UID")
        if rid is not None and owner is not None:
            try:
                moved.add((owner.value, moment(rid, zone)[0]))
            except Unreadable:
                pass
    for component in parsed:
        uid_prop = component.first("UID")
        uid = uid_prop.value if uid_prop else None
        try:
            if uid is None:
                raise Unreadable("the entry has no UID")
            todo = component.kind == "VTODO"
            anchor = component.first("DUE") if todo else None
            anchor = anchor or component.first("DTSTART")
            if anchor is None:
                raise Unreadable("the entry has no start" + (" and no due" if todo else ""))
            first, all_day = moment(anchor, zone)
            rule = component.first("RRULE")
            is_override = component.first("RECURRENCE-ID") is not None
            if is_override:
                rule = None
            duration: timedelta | None = None
            end_prop = component.first("DTEND")
            if not todo and end_prop is not None:
                duration = moment(end_prop, zone)[0] - first
            excluded = _excluded(component, zone)
            for at in occurrences(first, rule.value if rule else None, end, zone, anchor):
                if at < start or at in excluded:
                    continue
                if not is_override and rule is not None and (uid, at) in moved:
                    continue
                entry: Json = {
                    "uid": uid,
                    "kind": "todo" if todo else "event",
                    "summary": _summary(component),
                    "description": _text(d.value)[:DESCRIPTION]
                    if (d := component.first("DESCRIPTION"))
                    else None,
                    "categories": [
                        _text(c).strip()
                        for p in component.props.get("CATEGORIES", [])
                        for c in re.split(r"(?<!\\),", p.value)
                        if c.strip()
                    ],
                    "all_day": all_day,
                    "repeats": rule is not None,
                    "key": f"{uid}@{_utc(at)}",
                }
                entry["due" if todo else "start"] = _utc(at)
                entry["at"] = _utc(at)
                if duration is not None:
                    entry["end"] = _utc(at + duration)
                found.append(entry)
        except Unreadable as reason:
            unread.append({"uid": uid, "summary": _summary(component), "reason": str(reason)})
    found.sort(key=lambda e: (e["at"], e["uid"]))
    return {"entries": found, "unread": unread}


def _utc(at: datetime) -> str:
    return at.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
