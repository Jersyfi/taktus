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

**A level lowered.** Every incident the governance component raised for a level that fell by rule
is one alert (ADR-0110). It stays in effect until the owner answers its report: a level that fell
rises again only by a person's approval, so nothing clears it on its own.

**A raise proposed.** Every raise Taktus proposed on the corrections is one alert, with the
figures it was proposed with. It stays in effect until the owner answers its report. The answer
does not raise anything: a raise is a version a person registers with their approval (UC-7.1).

**A local lack.** Every lack the rule over the release's list classifies as local is one alert
(ADR-0118). It is in effect while a step still waits for it, and identified by the lack and the
oldest occurrence still waiting. It clears when every step that waited for it could start. The
same lack met again after that is a new alert.

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
    AlertRef,
    BackupState,
    CapacityCrossing,
    ClaimLost,
    LevelLowered,
    RaiseProposed,
)
from taktus.components.reporting.domain.model.finding import Classified, Finding, short

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
        about=tuple(AlertRef(run_id=run) for run in runs),
    )


# --- the backup -----------------------------------------------------------------------------------


def backup_due(state: BackupState) -> datetime | None:
    """By when the next successful backup is due: the last success, or the tenant's creation
    where none was recorded, plus the expected interval. None where a missing backup is not
    watched, or where the tenant's creation is not known."""
    reference = state.watched_since if state.last_ok is None else state.last_ok.at
    if state.expected_hours is None or reference is None:
        return None
    return reference + timedelta(hours=state.expected_hours)


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


# --- a level lowered ----------------------------------------------------------------------------


def _unit(version: str, action: str | None) -> str:
    process = version.rsplit("@", 1)[0]
    return f"the process {process}" if action is None else f"the action {action} of {process}"


def lowered(found: Iterable[LevelLowered]) -> tuple[Alert, ...]:
    """Every alert of a level that fell, oldest first."""
    return tuple(_lowered(one) for one in sorted(found, key=lambda o: (o.at, o.incident)))


def _lowered(one: LevelLowered) -> Alert:
    unit = _unit(one.process_version, one.action)
    fell = one.after < one.before
    if one.rule == "anchor.breach":
        anchors = ", ".join(one.anchors) or "an anchor"
        why = (
            f"Step {one.step_id} of run {one.run_id} performed an act that {anchors} names, "
            "with no person's decision to perform it."
        )
        look = (
            "Read the run's ledger (`taktusctl ledger`) around the step: what it performed, and "
            "why the anchor did not halt it at its boundary — an anchor configured while the "
            "step ran, or an act its declaration did not name."
        )
    else:
        rate = 0.0 if one.rate is None else one.rate
        limit = 0.0 if one.limit is None else one.limit
        why = (
            f"Its correction rate over {one.window_days or 0:g} days was {rate:.0%} of "
            f"{one.decided or 0} decision(s), above the tenant's limit of {limit:.0%}."
        )
        look = (
            "Read what people corrected or rejected (`taktusctl corrections`): the "
            "proposals and the versions released are kept in the ledger by digest."
        )
    if fell:
        title = f"A level fell by rule: {unit} now runs at level {one.after}"
        held = (
            f"Its steps now ask what level {one.after} asks of a person before they start. "
            "Nothing else stands still."
        )
    else:
        title = f"An anchor was breached by {unit}, already at the lowest level"
        held = "Nothing more: it runs at level 1, where a person performs every act."
    return Alert(
        id=_id("lowered", one.incident),
        kind="lowered",
        since=one.at,
        in_effect=True,
        title=title,
        needed=(
            f"A look at {unit} ({one.process_version}): {why} Taktus lowered it from level "
            f"{one.before} to {one.after} at {_at(one.at)}, by rule and without asking "
            f"(incident {one.incident})."
            if fell
            else f"A look at {unit} ({one.process_version}): {why} (incident {one.incident}).",
        ),
        steps=(
            look,
            "Repair the cause in the process, or leave it at the lower level.",
            "A level that fell rises again only by a version you register with your approval "
            "and its evidence (`taktusctl submit` with `--approve-raise`). Answer this report once "
            "you have looked.",
        ),
        standing_still=(held,),
        summary=(
            f"Level lowered: {unit} from {one.before} to {one.after} at {_at(one.at)} ({one.rule})."
        ),
        about=(
            AlertRef(process_version=one.process_version, run_id=one.run_id, step_id=one.step_id),
        ),
    )


# --- a raise proposed ---------------------------------------------------------------------------


def raises(found: Iterable[RaiseProposed]) -> tuple[Alert, ...]:
    """Every alert of a raise Taktus proposed, oldest first."""
    return tuple(_raise(one) for one in sorted(found, key=lambda o: o.seq))


def _raise(one: RaiseProposed) -> Alert:
    unit = _unit(one.process_version, one.action)
    return Alert(
        id=_id("raise", f"{one.process_version}|{one.action or ''}|{one.seq}"),
        kind="raise",
        since=one.at,
        in_effect=True,
        title=f"Taktus proposes raising {unit} one level",
        needed=(
            f"Your decision on a raise of {unit} ({one.process_version}). People corrected or "
            f"rejected {one.week_rate:.0%} of {one.week_decided} proposal(s) over 7 days and "
            f"{one.month_rate:.0%} of {one.month_decided} over 28 days, counted since "
            f"{_at(one.counted_since)}: the tenant's conditions for a raise hold.",
        ),
        steps=(
            "Read the figures and what was corrected: `taktusctl corrections`.",
            "To raise it, register a version one level higher with your approval "
            "(`taktusctl submit` with `--approve-raise`). Taktus never applies a raise itself.",
            "Answer this report once you have decided; leaving the level as it is needs nothing.",
        ),
        standing_still=("Nothing: the process runs at its level until you decide.",),
        summary=(
            f"Raise proposed: {unit}, {one.week_rate:.0%} over 7 days, {one.month_rate:.0%} "
            "over 28 days."
        ),
        about=(AlertRef(process_version=one.process_version),),
    )


# --- a local lack ------------------------------------------------------------------------------

ADAPTER_SETTING = {
    "no_worker": "a worker in `TAKTUS_WORKERS`",
    "no_connector": "a connector's label and address in `TAKTUS_CONNECTORS`",
    "operation_unsupported": "a connector's label and address in `TAKTUS_CONNECTORS`",
}
"""Where an adapter of each lack is configured."""


def local_lacks(found: Iterable[tuple[Finding, Classified]]) -> tuple[Alert, ...]:
    """Every local lack as one alert, oldest first; a product candidate is none."""
    alerts = [_local(finding, classified) for finding, classified in found if classified.local]
    return tuple(sorted(alerts, key=lambda a: a.since))


def _local(finding: Finding, classified: Classified) -> Alert:
    lack = finding.lack
    waiting = [o for o in finding.occurrences if not o.ended]
    basis = waiting[0] if waiting else finding.occurrences[-1]
    what = f"`{lack.lacking}`"
    runs = [
        f"Run `{o.run_id}`, step `{o.step_id}`, since {_at(o.since)}."
        for o in (waiting or finding.occurrences)
    ]
    if len(runs) > RUNS_SHOWN:
        runs = [*runs[:RUNS_SHOWN], f"And {len(runs) - RUNS_SHOWN} more."]
    if classified.kind == "configuration":
        adapters = ", ".join(f"`{name}`" for name in classified.adapters)
        title = f"A step lacks {what}, which an adapter the release ships offers"
        needed = (
            f"An adapter for {what}: the release ships {adapters}, and this instance did not "
            "configure it. It is a lack of this instance's configuration, not of the product, "
            "and it is not sent to the product.",
        )
        steps = (
            f"Configure {adapters} on this instance, as {ADAPTER_SETTING[lack.cause]}.",
            "Resume each run below: its step starts once the adapter resolves.",
            "The alert clears by itself when every step that waited for it could start.",
        )
    else:
        title = f"A step lacks {what}, which lies in this project's own development"
        needed = (
            f"{what} from an adapter, a process or a bundle this project brought: the release "
            "ships nothing that offers it, and it lies outside the product's vocabulary. It is "
            "not sent to the product.",
        )
        steps = (
            "Give the project's own adapter what the step needs, or change the process so that "
            "it needs what is configured.",
            "If the product should offer it, report it by hand: `taktusctl findings report`.",
            "The alert clears by itself when every step that waited for it could start.",
        )
    state = "in effect" if waiting else "cleared"
    return Alert(
        id=_id("local_lack", f"{lack.key}|{basis.id}"),
        kind="local_lack",
        since=basis.since,
        in_effect=bool(waiting),
        title=title,
        needed=needed,
        steps=steps,
        standing_still=tuple(runs),
        summary=(
            f"Local lack ({classified.kind}): {lack.lacking} since {_at(basis.since)}; {state}."
        ),
        about=tuple(
            AlertRef(run_id=o.run_id, step_id=o.step_id) for o in (waiting or finding.occurrences)
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
