"""The organisation seen as value streams (UC-15.6, ADR-0159 §5 and §6).

**The map.** Every value stream of the tenant, in three tiers: the management streams above, the
core streams from the customer's need to the customer's outcome in the middle, the support
streams below. Each shows, from the records of its processes:

- its **autonomy mix** — the share of its steps at each level, 1 to 4;
- its **method mix** — the share of its steps by method kind, and how many are reproducible;
- its **flow efficiency** — of the lead time of its processes' runs that ended in the period,
  the share in which nothing was blocked — and its **blocked share**, the rest, with the cause
  that held up most;
- the **department boundaries it crosses** — each handover from a person's step to the next
  person's step whose roles sit in no common unit of the organisation's structure (`org_path`).

**The stream.** One stream opens as role swimlanes: a column for each process in the order of
the stream, a lane for Taktus's reproducible methods, one for its variable methods, and one for
each role a person acts in, in the order the stream first needs it. Each step is a chip in its
process's column and its lane; a step that falls back to a person names that lane too. Each
role lane carries the units its holders sit in: the organisation's structure overlaid, not
replaced.

**No figure names a person** (principle 14). A role's waiting is shown only where at least two
identities hold the role (ADR-0015); a unit is a part of the structure, never a count of who sits
in it. A process the reader may not see is left out of every figure.

Pure: the facts in, the views out. Nothing is stored.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import Field

from taktus.shared.v1 import Value

REPRODUCIBLE = frozenset({"rule", "statistics", "ml", "neural", "wait"})
"""The method kinds whose result does not vary for the same input (methods.md); `human` is a
person's lane, not Taktus's."""
VARIABLE = frozenset({"llm", "worker"})
TOO_FEW = 2
"""Fewer identities than this hold a role: its figure would be one person's (ADR-0015)."""
TIERS = ("management", "core", "support")

type LaneKind = Literal["reproducible", "variable", "role"]


# --- the facts, as the composition hands them over -----------------------------------------


OWNER = "owner"
"""The role a `human` step that names none is shown in, as the stage view shows a wait that
names none (UC-6.15): never nobody."""


class StepFacts(Value):
    id: str = Field(min_length=1)
    method: str = Field(min_length=1)
    exactness: str | None = None
    role: str | None = None
    """The role a person acts in at this step, for a `human` step — the owner where it names
    none; None for every other step."""
    fallback_role: str | None = None
    """The role a fallback to a person names."""


class RunFacts(Value):
    """One run of a process that ended in the period: how long it took, how long it was held
    up, and by which account. No person."""

    lead_seconds: float = Field(ge=0)
    blocked: Mapping[str, float] = Field(default_factory=dict)
    """Seconds per account (`wait.human`, `limit.provider`, …)."""


class ProcessFacts(Value):
    process: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: str | None = None
    """The active version as `<process>@<version>`; None where the process is switched off."""
    level: int | None = Field(default=None, ge=1, le=4)
    steps: tuple[StepFacts, ...] = ()
    runs: tuple[RunFacts, ...] = ()
    waits: Mapping[str, float] = Field(default_factory=dict)
    """Seconds a step of this process waited on a person, per role it was addressed to."""


class StreamFacts(Value):
    stream: str = Field(min_length=1)
    revision: int = Field(ge=1)
    name: str = Field(min_length=1)
    kind: str = Field(pattern=r"^(core|management|support)$")
    trigger: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    role: str = Field(min_length=1)
    processes: tuple[str, ...]
    """In the order of the stream, those the reader may see."""


class RoleFacts(Value):
    holders: int = Field(ge=0)
    units: tuple[str, ...] = ()
    """The units of the structure its holders sit in, each as its `org_path` joined by `/`."""


# --- the views ------------------------------------------------------------------------------


class Crossing(Value):
    """A handover from one person's step to the next whose roles share no unit."""

    from_process: str
    from_step: str
    from_role: str
    from_units: tuple[str, ...]
    to_process: str
    to_step: str
    to_role: str
    to_units: tuple[str, ...]
    text: str = Field(min_length=1)


class StreamFigures(Value):
    steps: int
    autonomy: dict[str, float]
    """The share of the stream's steps at each level, `"1"` to `"4"`."""
    methods: dict[str, float]
    """The share of its steps by method kind."""
    reproducible: float | None
    """The share of its steps of a reproducible method kind; None without steps."""
    runs: int
    """The runs of its processes that ended in the period."""
    flow_efficiency: float | None
    """Of their lead time, the share in which nothing was blocked; None without a run."""
    blocked_share: float | None
    top_cause: str | None
    """The account that held up most; None where nothing was blocked."""
    crossings: tuple[Crossing, ...]


class StreamCard(Value):
    stream: str
    revision: int
    name: str
    kind: str
    trigger: str
    outcome: str
    role: str
    """The one role responsible for the stream. Never a person."""
    processes: tuple[str, ...]
    figures: StreamFigures
    text: str = Field(min_length=1)


class Outside(Value):
    """A process the reader may see that no stream names."""

    process: str
    name: str


class StreamMap(Value):
    days: int
    management: tuple[StreamCard, ...]
    core: tuple[StreamCard, ...]
    support: tuple[StreamCard, ...]
    outside: tuple[Outside, ...]
    summary: str = Field(min_length=1)


class Lane(Value):
    key: str
    """`taktus.reproducible`, `taktus.variable` or `role:<role>`."""
    kind: LaneKind
    title: str
    role: str | None = None
    units: tuple[str, ...] = ()
    """For a role lane: the units its holders sit in — the structure overlaid."""
    waiting_seconds: float | None = None
    """For a role lane: how long the stream's steps waited on the role in the period; None
    where fewer than two hold it, or nothing waited."""
    text: str = Field(min_length=1)


class Column(Value):
    process: str
    name: str
    version: str | None
    level: int | None


class Chip(Value):
    process: str
    step: str
    method: str
    exactness: str | None
    lane: str
    fallback_lane: str | None = None
    """The role lane a fallback to a person goes to."""
    text: str = Field(min_length=1)


class StreamLanes(Value):
    card: StreamCard
    columns: tuple[Column, ...]
    lanes: tuple[Lane, ...]
    chips: tuple[Chip, ...]
    units: tuple[str, ...]
    """Every unit a lane sits in, for the overlay of the structure."""
    summary: str = Field(min_length=1)


# --- drawing --------------------------------------------------------------------------------


def _percent(share: float) -> str:
    return f"{round(share * 100)} %"


def _shares(counts: Mapping[str, int], total: int) -> dict[str, float]:
    return {k: round(v / total, 4) for k, v in sorted(counts.items())} if total else {}


def _crossings(
    processes: Sequence[ProcessFacts], roles: Mapping[str, RoleFacts]
) -> tuple[Crossing, ...]:
    found: list[Crossing] = []
    before: tuple[ProcessFacts, StepFacts] | None = None
    for process in processes:
        for step in process.steps:
            role = step.role or step.fallback_role
            if role is None:
                continue
            if before is not None:
                was_process, was = before
                was_role = was.role or was.fallback_role or ""
                was_units = roles.get(was_role, RoleFacts(holders=0)).units
                units = roles.get(role, RoleFacts(holders=0)).units
                if was_units and units and not set(was_units) & set(units):
                    found.append(
                        Crossing(
                            from_process=was_process.process,
                            from_step=was.id,
                            from_role=was_role,
                            from_units=was_units,
                            to_process=process.process,
                            to_step=step.id,
                            to_role=role,
                            to_units=units,
                            text=f"{was_process.process}/{was.id} ({was_role}, "
                            f"{', '.join(was_units)}) hands over to {process.process}/{step.id} "
                            f"({role}, {', '.join(units)}).",
                        )
                    )
            before = (process, step)
    return tuple(found)


def _figures(processes: Sequence[ProcessFacts], roles: Mapping[str, RoleFacts]) -> StreamFigures:
    steps = [(p, s) for p in processes for s in p.steps]
    levels: dict[str, int] = {}
    methods: dict[str, int] = {}
    for process, step in steps:
        if process.level is not None:
            levels[str(process.level)] = levels.get(str(process.level), 0) + 1
        methods[step.method] = methods.get(step.method, 0) + 1
    total = len(steps)
    runs = [r for p in processes for r in p.runs]
    lead = sum(r.lead_seconds for r in runs)
    causes: dict[str, float] = {}
    blocked = 0.0
    for run in runs:
        for account, seconds in run.blocked.items():
            causes[account] = causes.get(account, 0.0) + seconds
        blocked += min(sum(run.blocked.values()), run.lead_seconds)
    reproducible = sum(1 for _, s in steps if s.method in REPRODUCIBLE)
    return StreamFigures(
        steps=total,
        autonomy=_shares(levels, total),
        methods=_shares(methods, total),
        reproducible=round(reproducible / total, 4) if total else None,
        runs=len(runs),
        flow_efficiency=round((lead - blocked) / lead, 4) if lead else None,
        blocked_share=round(blocked / lead, 4) if lead else None,
        top_cause=max(sorted(causes), key=lambda k: causes[k]) if blocked else None,
        crossings=_crossings(processes, roles),
    )


def _card(
    stream: StreamFacts, processes: Mapping[str, ProcessFacts], roles: Mapping[str, RoleFacts]
) -> StreamCard:
    mine = [processes[p] for p in stream.processes if p in processes]
    figures = _figures(mine, roles)
    text = (
        f"{stream.name} ({stream.kind}): from {stream.trigger.rstrip('.')} to "
        f"{stream.outcome.rstrip('.')}, the role {stream.role} responsible; "
        f"{len(mine)} {'process' if len(mine) == 1 else 'processes'}, {figures.steps} steps"
    )
    if figures.reproducible is not None:
        text += f", {_percent(figures.reproducible)} reproducible"
    if figures.flow_efficiency is not None:
        runs = "run" if figures.runs == 1 else "runs"
        text += f"; flow efficiency {_percent(figures.flow_efficiency)} over {figures.runs} {runs}"
    else:
        text += "; no run ended in the period"
    count = len(figures.crossings)
    text += f"; {count} department {'boundary' if count == 1 else 'boundaries'} crossed."
    return StreamCard(
        stream=stream.stream,
        revision=stream.revision,
        name=stream.name,
        kind=stream.kind,
        trigger=stream.trigger,
        outcome=stream.outcome,
        role=stream.role,
        processes=tuple(p.process for p in mine),
        figures=figures,
        text=text,
    )


def stream_map(
    streams: Sequence[StreamFacts],
    processes: Sequence[ProcessFacts],
    roles: Mapping[str, RoleFacts],
    days: int,
) -> StreamMap:
    """The map of every stream; `processes` are those the reader may see."""
    by_id = {p.process: p for p in processes}
    cards = [_card(s, by_id, roles) for s in sorted(streams, key=lambda s: s.stream)]
    named = {p for s in streams for p in s.processes}
    outside = tuple(
        Outside(process=p.process, name=p.name)
        for p in sorted(processes, key=lambda p: p.process)
        if p.process not in named
    )
    tiers = {t: tuple(c for c in cards if c.kind == t) for t in TIERS}
    summary = (
        "No value stream is declared yet."
        if not cards
        else f"{len(tiers['core'])} core, {len(tiers['management'])} management and "
        f"{len(tiers['support'])} support streams over {days} days"
    )
    if cards:
        if outside:
            processes_word = "process" if len(outside) == 1 else "processes"
            summary += f"; {len(outside)} {processes_word} in no stream."
        else:
            summary += "."
    return StreamMap(
        days=days,
        management=tiers["management"],
        core=tiers["core"],
        support=tiers["support"],
        outside=outside,
        summary=summary,
    )


def _role_lane(role: str, facts: RoleFacts | None, waited: float) -> Lane:
    held = facts or RoleFacts(holders=0)
    shown = held.holders >= TOO_FEW
    where = f" in {', '.join(held.units)}" if held.units else ""
    if not waited:
        said = "nothing waited on it"
    elif shown:
        said = f"waited on for {round(waited / 3600, 1)} h"
    else:
        said = "too few hold it to show its waiting"
    return Lane(
        key=f"role:{role}",
        kind="role",
        title=role,
        role=role,
        units=held.units,
        waiting_seconds=round(waited, 3) if waited and shown else None,
        text=f"The role {role}{where}: {said}.",
    )


def stream_lanes(
    stream: StreamFacts,
    processes: Sequence[ProcessFacts],
    roles: Mapping[str, RoleFacts],
) -> StreamLanes:
    """One stream as role swimlanes; `processes` are those the reader may see."""
    by_id = {p.process: p for p in processes}
    card = _card(stream, by_id, roles)
    mine = [by_id[p] for p in stream.processes if p in by_id]
    order: list[str] = []
    waited: dict[str, float] = {}
    chips: list[Chip] = []
    for process in mine:
        for role, seconds in process.waits.items():
            waited[role] = waited.get(role, 0.0) + seconds
        for step in process.steps:
            for named in (step.role, step.fallback_role):
                if named is not None and named not in order:
                    order.append(named)
            if step.role is not None:
                lane = f"role:{step.role}"
            elif step.method in VARIABLE:
                lane = "taktus.variable"
            else:
                lane = "taktus.reproducible"
            fallback = None if step.fallback_role is None else f"role:{step.fallback_role}"
            text = f"{process.process}/{step.id}: {step.method}"
            if step.exactness is not None:
                text += f", {step.exactness}"
            if step.role is not None:
                text += f", by the role {step.role}"
            if step.fallback_role is not None:
                text += f", falls back to the role {step.fallback_role}"
            chips.append(
                Chip(
                    process=process.process,
                    step=step.id,
                    method=step.method,
                    exactness=step.exactness,
                    lane=lane,
                    fallback_lane=fallback,
                    text=text + ".",
                )
            )
    lanes = [
        Lane(
            key="taktus.reproducible",
            kind="reproducible",
            title="Taktus — reproducible",
            text="Taktus, by a method whose result does not vary: rule, statistics, ml, "
            "neural, wait.",
        ),
        Lane(
            key="taktus.variable",
            kind="variable",
            title="Taktus — variable",
            text="Taktus, by a method whose result can vary: llm, worker.",
        ),
        *(_role_lane(r, roles.get(r), waited.get(r, 0.0)) for r in order),
    ]
    units = tuple(sorted({u for lane in lanes for u in lane.units}))
    return StreamLanes(
        card=card,
        columns=tuple(
            Column(process=p.process, name=p.name, version=p.version, level=p.level) for p in mine
        ),
        lanes=tuple(lanes),
        chips=tuple(chips),
        units=units,
        summary=f"{card.text} {len(order)} roles act along it.",
    )
