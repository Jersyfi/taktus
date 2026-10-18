"""Which recorded facts make an alert, and the words it is reported in (ADR-0106).

**Capacity.** Every `capacity.<resource>` entry with outcome `act` that follows no open one
begins an alert. The alert is in effect while no entry of its kind with outcome `ok` follows it;
that entry clears it. A crossing to *act* after that begins a new alert.

**A lost claim.** Every `run.claim_lost` entry belongs to one alert, from the first after the
last alert of this kind was answered done. An answer closes it at that moment; a loss after it
begins a new one. A loss is an event, so the alert never clears on its own.

**The backup.** One alert at most, identified by the last successful backup, or by `never`. It
is in effect when a run failed after that success, or when that success is older than the
expected interval. A tenant with no success at all counts from when it began to be watched. A
new success that is recent enough ends it.

Nothing else decides: no model, no estimate, no reading of words (ADR-0023). Pure: facts and the
closing times in, alerts and their words out.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta

from taktus.components.reporting.domain.model.alert import (
    ID_PREFIXES,
    Alert,
    BackupState,
    CapacityCrossing,
    ClaimLost,
)
from taktus.components.reporting.domain.model.finding import short

RUNS_SHOWN = 10
"""How many runs a report names one by one; the rest are counted."""

FAILED_STEP: dict[str, str] = {
    "configuration": "its configuration could not be read",
    "database": "the database could not be read or dumped",
    "encryption": "the backup could not be encrypted to its recipient",
    "objects": "the object store could not be archived",
    "store": "the backup store could not be written or listed",
    "retention": "older backups could not be deleted from the store",
}
"""One phrase per step the backup program names when a run fails."""


def _at(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def _id(kind: str, basis: str) -> str:
    return ID_PREFIXES[kind] + short(basis)


# --- capacity -----------------------------------------------------------------------------------


def subject(kind: str) -> str:
    """`capacity.storage.database` → `storage (database)`; `capacity.memory` → `memory`."""
    parts = kind.split(".")[1:]
    place = " ".join(p.replace("_", " ") for p in parts[1:])
    return parts[0] if not place else f"{parts[0]} ({place})"


def capacity(crossings: Iterable[CapacityCrossing]) -> tuple[Alert, ...]:
    """Every capacity alert the crossings make, oldest first, cleared ones included."""
    by_kind: dict[str, list[CapacityCrossing]] = defaultdict(list)
    for crossing in sorted(crossings, key=lambda c: c.seq):
        by_kind[crossing.kind].append(crossing)
    found: list[Alert] = []
    for entries in by_kind.values():
        opened: CapacityCrossing | None = None
        for entry in entries:
            if entry.outcome == "act" and opened is None:
                opened = entry
            elif entry.outcome == "ok" and opened is not None:
                found.append(_capacity(opened, cleared=entry))
                opened = None
        if opened is not None:
            found.append(_capacity(opened, cleared=None))
    return tuple(sorted(found, key=lambda a: a.since))


def _capacity(opened: CapacityCrossing, *, cleared: CapacityCrossing | None) -> Alert:
    what = subject(opened.kind)
    storage = opened.kind.startswith("capacity.storage")
    remedy = (
        "Expand the volume, or plan a migration where it cannot be expanded."
        if storage
        else "Give the instance more memory, or let it run fewer jobs at once."
    )
    held = (
        "Nothing yet. Below the refusal share, a new run is refused before it writes."
        if storage
        else "Nothing yet. A job that needs more memory than is free is refused."
    )
    state = "in effect" if cleared is None else f"cleared at {_at(cleared.at)}"
    return Alert(
        id=_id("capacity", f"{opened.kind}|{opened.seq}"),
        kind="capacity",
        since=opened.at,
        in_effect=cleared is None,
        title=f"The instance's {what} needs a person's action",
        needed=(
            f"More room for the instance's work: its {what} turned to act at "
            f"{_at(opened.at)} (`{opened.kind}`). Taktus reports it; adding the room is a "
            "person's act.",
        ),
        steps=(
            "Run `taktusctl capacity` on the instance: it names the figure, the date and the "
            "remedy.",
            remedy,
            f"The alert clears by itself at the first capacity report that finds the {what} "
            "ok again.",
        ),
        standing_still=(held,),
        summary=f"Capacity: {what} turned to act at {_at(opened.at)}; {state}.",
    )


# --- a lost claim ---------------------------------------------------------------------------------


def claims_lost(losses: Iterable[ClaimLost], closed: Mapping[str, datetime]) -> tuple[Alert, ...]:
    """Every claim-lost alert, oldest first. `closed` holds, by identifier, when the owner
    answered an alert's report that it is done."""
    found: list[Alert] = []
    current: list[ClaimLost] = []
    for loss in sorted(losses, key=lambda c: c.seq):
        if current:
            ended = closed.get(_claims_id(current))
            if ended is not None and loss.at > ended:
                found.append(_claims(current))
                current = []
        current.append(loss)
    if current:
        found.append(_claims(current))
    return tuple(found)


def _claims_id(losses: list[ClaimLost]) -> str:
    return _id("claim_lost", str(losses[0].seq))


def _claims(losses: list[ClaimLost]) -> Alert:
    first, last = losses[0], losses[-1]
    runs = tuple(dict.fromkeys(loss.run_id for loss in losses))
    named = ", ".join(runs[:RUNS_SHOWN])
    rest = len(runs) - RUNS_SHOWN
    listed = named if rest <= 0 else f"{named} and {rest} more"
    return Alert(
        id=_claims_id(losses),
        kind="claim_lost",
        since=first.at,
        in_effect=True,
        title="A runner lost its claim on a run",
        needed=(
            f"A look at the runners: {len(losses)} claim(s) on {len(runs)} run(s) were lost "
            f"since {_at(first.at)}. A runner loses its claim when it cannot reach the "
            "database, or is paused, for longer than the lease (`TAKTUS_LEASE_SECONDS`).",
        ),
        steps=(
            f"First loss: run {first.run_id}, at {_at(first.at)}. Last loss: run "
            f"{last.run_id}, at {_at(last.at)}.",
            "Read the runners' log and the database's log around those times: a lost "
            "connection, a pause, a lock that was waited for.",
            "Repair the cause, then answer this report that it is done. A claim lost after "
            "that is a new report.",
        ),
        standing_still=(
            "Nothing, as far as the claim goes: another runner took each run over at its "
            f"last step boundary. Runs: {listed}.",
        ),
        summary=(
            f"Claim lost: {len(losses)} time(s) on {len(runs)} run(s), first at "
            f"{_at(first.at)}, last at {_at(last.at)}."
        ),
    )


# --- the backup -----------------------------------------------------------------------------------


def backup(state: BackupState, now: datetime) -> Alert | None:
    """The backup alert in effect, or None."""
    reference = state.watched_since if state.last_ok is None else state.last_ok.at
    failing = state.failed_count > 0
    missing = (
        state.expected_hours is not None
        and reference is not None
        and now - reference > timedelta(hours=state.expected_hours)
    )
    if not failing and not missing:
        return None
    basis = "never" if state.last_ok is None else state.last_ok.name
    if state.last_ok is None:
        last = "No successful backup was ever recorded."
    else:
        last = f"The last successful backup is {state.last_ok.name}, at {_at(state.last_ok.at)}."
    needed: list[str] = []
    if failing and state.failed:
        newest = state.failed[0]
        why = FAILED_STEP.get(newest.reason or "", "it failed")
        needed.append(
            f"A working backup: the newest run, {newest.name} at {_at(newest.at)}, failed at "
            f"the step `{newest.reason}`: {why}. {state.failed_count} run(s) failed since the "
            "last success."
        )
    if missing:
        needed.append(
            f"A backup: none succeeded in the last {state.expected_hours} hours "
            "(`TAKTUS_BACKUP_EXPECTED_HOURS`)."
        )
    since = (
        state.failed[-1].at
        if failing and state.failed
        else (reference if reference is not None else now)
    )
    return Alert(
        id=_id("backup", basis),
        kind="backup",
        since=since,
        in_effect=True,
        title=("The instance's backup failed" if failing else "The instance has no recent backup"),
        needed=(*needed, last),
        steps=(
            "Read the log of the backup program's last run: it names the step and the tool "
            "that failed.",
            "Repair what the step names: `configuration` the backup's settings, `database` the "
            "database or the backup's login, `encryption` the recipient, `objects` the state "
            "volume, `store` the backup store or its credential, `retention` the deletions in "
            "the store.",
            "Run the backup once by hand. The alert clears by itself when a successful run is "
            "recorded.",
        ),
        standing_still=(
            "Nothing of the work. A restore can reach back only to the last successful "
            "backup, and the work since would be lost with the database.",
        ),
        summary=(
            f"Backup: {'failing' if failing else 'missing'}; "
            + (
                "never succeeded."
                if state.last_ok is None
                else f"last success {state.last_ok.name}."
            )
        ),
    )


def shown(alert: Alert, state: str) -> str:
    """The alert as the operator reads it, with what became of its report."""
    return "\n".join(
        (
            f"{alert.title}.",
            alert.summary,
            *alert.needed,
            f"Report {alert.id}: {state}.",
        )
    )
