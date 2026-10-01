"""The capacity report: observations and growth in, findings out — a figure and a date a
person can act on before it is tight, never a warning light (docs/architecture/platform.md).

Pure: no clock, no port. The moment is the observation's.

**Storage.** The state only grows — the ledger is append-only by construction — so a volume
that is not watched fills and work stops. For each place the state grows in:

- *growth per run* is what the state occupies divided by the runs it holds. That is an upper
  bound: it counts what an empty instance already occupies as if runs had written it, so the
  dates it gives come early, never late, and the bound tightens as runs accumulate;
- *runs per day* are the runs created within the window, over the window's length;
- the day the volume is full, and the day it crosses the warning threshold, follow at that
  growth. A person must act when the threshold is crossed, or will be within the agreed
  horizon — the time a migration needs;
- with no run yet, or none in the window, growth is not measurable, and the finding says so
  instead of inventing a rate.

**Memory and CPU.** What is free against the warning share. Memory is what a job that does
not fit is refused for (`run/domain/service/capacity.py`); a busy CPU slows work down and
stops none.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date, datetime, timedelta

from taktus.components.governance.domain.model.capacity import (
    CapacityThresholds,
    Finding,
    RunActivity,
    Status,
    StorageStore,
)
from taktus.ports.platform import PlatformObservation, Reading, Unobserved

HORIZON_DAYS = 36_500
"""Beyond a hundred years a date is not a date a person plans by; the finding says so."""
ACT_NOW = "a person must act now"


def assess(
    observation: PlatformObservation,
    stores: Sequence[StorageStore],
    activity: RunActivity,
    thresholds: CapacityThresholds,
    *,
    job_memory_bytes: int | None = None,
    platform_adapter: str = "platform.host",
) -> tuple[Finding, ...]:
    """One finding per place the state grows in, then memory, then CPU. `job_memory_bytes` is
    the memory limit of the configured execution unit, where a unit is started on this
    platform: the memory finding then says how many such jobs still fit."""
    findings = [storage(store, activity, thresholds, observation.at) for store in stores]
    findings.append(memory(observation.memory, thresholds, job_memory_bytes, platform_adapter))
    findings.append(cpu(observation.cpu, thresholds, platform_adapter))
    return tuple(findings)


def storage(
    store: StorageStore, activity: RunActivity, thresholds: CapacityThresholds, at: datetime
) -> Finding:
    subject = f"storage ({store.name})"
    kind = f"capacity.storage.{store.label}"
    reading = store.reading
    if isinstance(reading, Unobserved):
        return Finding(
            resource="storage",
            subject=subject,
            kind=kind,
            adapter=store.adapter,
            status=Status.UNKNOWN,
            used_bytes=store.used_bytes,
            text=f"{subject}: not observed — {reading.reason}",
        )
    free, total = reading.free, reading.total
    warn_share = thresholds.storage_warn_free_percent / 100
    floor = total * warn_share
    parts = [f"{subject}: {size(free)} free of {size(total)} ({percent(free / total)})"]

    per_run: float | None = None
    per_day: float | None = None
    threshold_on = full_on = None
    days_to_threshold: float | None = None
    if store.used_bytes is None:
        parts.append(
            "what the state occupies here could not be measured, so its growth is not known"
        )
    elif activity.runs == 0:
        parts.append("no run is recorded yet, so the growth per run is not measurable")
    else:
        per_run = store.used_bytes / activity.runs
        per_day = activity.runs_per_day
        parts.append(
            f"{size(per_run)} per run at most, over the {activity.runs} runs the state holds"
        )
        if per_day == 0:
            parts.append(f"no run in the last {days(activity.window_days)}, so it is not growing")
        else:
            parts.append(f"{per_day:.1f} runs/day over the last {days(activity.window_days)}")
            growth = per_run * per_day
            days_to_full = free / growth
            days_to_threshold = max(0.0, (free - floor) / growth)
            full_on = _on(at, days_to_full)
            threshold_on = _on(at, days_to_threshold)
            parts.append(
                f"full on {full_on.isoformat()}"
                if full_on is not None
                else "full in more than a hundred years"
            )
    below = free < floor
    if below:
        threshold_on = at.date()
    elif threshold_on is not None:
        parts.append(f"below {percent(warn_share)} on {threshold_on.isoformat()}")
    act = below or (
        days_to_threshold is not None and days_to_threshold <= thresholds.act_within_days
    )
    text = "; ".join(parts)
    if below:
        text += f" — below {percent(warn_share)}: {ACT_NOW} ({_remedy(store.expandable)})"
    elif act and threshold_on is not None:
        text += (
            f" — a person must act before {threshold_on.isoformat()} ({_remedy(store.expandable)})"
        )
    return Finding(
        resource="storage",
        subject=subject,
        kind=kind,
        adapter=store.adapter,
        status=Status.ACT if act else Status.OK,
        text=text,
        free=free,
        total=total,
        used_bytes=store.used_bytes,
        bytes_per_run=per_run,
        runs_per_day=per_day,
        threshold_on=threshold_on,
        full_on=full_on,
    )


def memory(
    reading: Reading,
    thresholds: CapacityThresholds,
    job_memory_bytes: int | None,
    adapter: str,
) -> Finding:
    if isinstance(reading, Unobserved):
        known = f" (the total is {size(reading.total)})" if reading.total is not None else ""
        return Finding(
            resource="memory",
            subject="memory",
            kind="capacity.memory",
            adapter=adapter,
            status=Status.UNKNOWN,
            total=reading.total,
            text=f"memory: not observed{known} — {reading.reason}",
        )
    share = thresholds.memory_warn_free_percent / 100
    text = (
        f"memory: {size(reading.free)} free of {size(reading.total)} "
        f"({percent(reading.free_fraction)})"
    )
    if job_memory_bytes is not None:
        fit = math.floor(reading.free / job_memory_bytes)
        text += f"; room for {fit} job(s) at the unit's limit of {size(job_memory_bytes)}"
    act = reading.free_fraction < share
    if act:
        text += (
            f" — below {percent(share)}: {ACT_NOW}; a job that does not fit is refused, and a "
            "process that outgrows what is left is killed by the kernel without warning"
        )
    return Finding(
        resource="memory",
        subject="memory",
        kind="capacity.memory",
        adapter=adapter,
        status=Status.ACT if act else Status.OK,
        text=text,
        free=reading.free,
        total=reading.total,
    )


def cpu(reading: Reading, thresholds: CapacityThresholds, adapter: str) -> Finding:
    if isinstance(reading, Unobserved):
        return Finding(
            resource="cpu",
            subject="cpu",
            kind="capacity.cpu",
            adapter=adapter,
            status=Status.UNKNOWN,
            total=reading.total,
            text=f"cpu: not observed — {reading.reason}",
        )
    share = thresholds.cpu_warn_free_percent / 100
    text = (
        f"cpu: {reading.free:.1f} of {reading.total:g} cores idle "
        f"({percent(reading.free_fraction)}, {reading.source})"
    )
    act = reading.free_fraction < share
    if act:
        text += f" — below {percent(share)}: work is slowed, none is stopped; a person should look"
    return Finding(
        resource="cpu",
        subject="cpu",
        kind="capacity.cpu",
        adapter=adapter,
        status=Status.ACT if act else Status.OK,
        text=text,
        free=reading.free,
        total=reading.total,
    )


def _remedy(expandable: bool | None) -> str:
    if expandable is False:
        return "expanding this volume is impossible on its storage class: plan a migration"
    if expandable is True:
        return "expand the volume"
    return "whether this volume can be expanded is not configured; if it cannot, plan a migration"


def _on(at: datetime, after_days: float) -> date | None:
    if after_days > HORIZON_DAYS:
        return None
    return (at + timedelta(days=after_days)).date()


def size(value: float) -> str:
    """Bytes for a person: binary units, one decimal."""
    for unit, factor in (("TiB", 1024**4), ("GiB", 1024**3), ("MiB", 1024**2), ("KiB", 1024)):
        if value >= factor:
            return f"{value / factor:.1f} {unit}"
    return f"{value:.0f} B"


def percent(share: float) -> str:
    return f"{share * 100:.1f} %".replace(".0 %", " %")


def days(value: float) -> str:
    whole = round(value)
    if abs(value - whole) < 0.05:
        return "day" if whole == 1 else f"{whole} days"
    return f"{value:.1f} days"
