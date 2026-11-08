"""The same work with and without a knowledge source connected, compared on the cockpit's
figures (UC-5.5 §2, ADR-0291). Pure: the ledger's entries and the knowledge reads of each
version in, the figures out; nothing is stored.

A run of a version with knowledge reads is *with knowledge* when one of them finished with a
result a connector produced — its `step.finished` names an adapter and its method is not
`human` — and *without* otherwise. Each side gets the cockpit's figures by the value ledger's
own definitions; a side without an ended run withholds them, and so does the difference.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from taktus.components.value.domain.model import Figure
from taktus.components.value.domain.service.figures import DEFINITIONS, OWNER
from taktus.shared.v1 import LedgerEntry, Method

type Side = Literal["with", "without"]
SIDES: tuple[Side, ...] = ("with", "without")
KINDS = frozenset(
    {"run.created", "run.finished", "run.escalated", "step.finished", "step.corrected"}
)
COMPARED = (
    "value.cycle_seconds",
    "value.quality",
    "value.cost_per_case",
    "value.automation",
    "value.escalation_rate",
)
"""The cockpit's figures the two sides are compared on; the cost per case stands for the cost,
since the sides differ in their number of runs."""
SIDE_ID = {"with": "value.with_knowledge", "without": "value.without_knowledge"}
EFFECT_ID = "value.knowledge_effect"
SIDE_WORDS = {
    "with": "the runs whose knowledge read a connected source answered",
    "without": "the runs whose knowledge read no connected source answered",
}


def figure_id(prefix: str, compared: str) -> str:
    """`value.with_knowledge.quality` for `value.quality`."""
    return f"{prefix}.{compared.split('.', 1)[1]}"


def compared_of(id: str) -> str | None:
    """The cockpit figure a comparison's figure compares; None for another figure."""
    for prefix in (*SIDE_ID.values(), EFFECT_ID):
        if id.startswith(prefix + "."):
            return "value." + id[len(prefix) + 1 :]
    return None


def knowledge_reads(work: Mapping[str, Any]) -> frozenset[str]:
    """The steps of a version's work that read knowledge: connector calls of a capability one
    of its `citation` steps names (ADR-0291 §1)."""
    cited = {
        str(w.get("capability"))
        for w in work.values()
        if isinstance(w, Mapping) and w.get("rule") == "citation" and w.get("capability")
    }
    return frozenset(
        step
        for step, w in work.items()
        if isinstance(w, Mapping)
        and w.get("rule") == "connector"
        and str(w.get("operation", "")).rsplit(".", 1)[0] in cited
    )


@dataclass
class _Run:
    process: str
    version: str
    created: datetime | None = None
    ended: datetime | None = None
    escalated: bool = False
    served: bool = False
    by_hand: int = 0
    by_method: int = 0
    corrected: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class Tally:
    """One side of one process: the runs that ended in the period."""

    runs: tuple[str, ...] = ()
    finished: int = 0
    escalated: int = 0
    cycle_seconds: float = 0.0
    corrected: int = 0
    by_hand: int = 0
    by_method: int = 0

    @property
    def ended(self) -> int:
        return self.finished + self.escalated


def sides(
    entries: Iterable[LedgerEntry],
    reads: Mapping[str, frozenset[str]],
    since: datetime,
    until: datetime,
) -> dict[str, dict[Side, Tally]]:
    """Per process, both sides' tallies of the runs that ended from `since` to `until`.
    `reads` gives the knowledge reads per version, `process@version`; a version it does not
    name, or names with none, is not compared."""
    runs: dict[str, _Run] = {}
    for e in sorted(entries, key=lambda e: e.seq):
        version, run_id = e.refs.process_version, e.refs.run_id
        if e.rehearsal or version is None or run_id is None or not reads.get(version):
            continue
        if e.ts > until:
            continue
        run = runs.setdefault(run_id, _Run(process=version.rsplit("@", 1)[0], version=version))
        if e.kind == "run.created":
            run.created = e.ts
        elif e.kind in ("run.finished", "run.escalated"):
            run.ended, run.escalated = e.ts, e.kind == "run.escalated"
        elif e.kind == "step.finished" and e.outcome == "succeeded":
            if e.method is Method.HUMAN:
                run.by_hand += 1
            else:
                run.by_method += 1
            if e.refs.step_id in reads[version] and e.adapter and e.method is not Method.HUMAN:
                run.served = True
        elif e.kind == "step.corrected" and e.refs.step_id is not None:
            run.corrected.add(e.refs.step_id)
    out: dict[str, dict[Side, dict[str, Any]]] = {}
    for run_id, run in sorted(runs.items()):
        if run.ended is None or run.ended < since:
            continue
        side: Side = "with" if run.served else "without"
        t = out.setdefault(run.process, {s: _empty() for s in SIDES})[side]
        t["runs"].append(run_id)
        t["escalated" if run.escalated else "finished"] += 1
        if run.created is not None:
            t["cycle_seconds"] += max((run.ended - run.created).total_seconds(), 0.0)
        t["corrected"] += len(run.corrected)
        t["by_hand"] += run.by_hand
        t["by_method"] += run.by_method
    return {
        p: {s: Tally(**{**t, "runs": tuple(t["runs"])}) for s, t in by.items()}
        for p, by in out.items()
    }


def _empty() -> dict[str, Any]:
    return {
        "runs": [],
        "finished": 0,
        "escalated": 0,
        "cycle_seconds": 0.0,
        "corrected": 0,
        "by_hand": 0,
        "by_method": 0,
    }


def _value(compared: str, t: Tally, cost: float | None) -> tuple[float | None, str | None]:
    """A cockpit figure of one side, and why it is withheld where it is."""
    none = "no run of the process ended on this side in the period"
    if t.ended == 0:
        return None, none
    if compared == "value.cycle_seconds":
        return t.cycle_seconds / t.ended, None
    if compared == "value.quality":
        return (t.finished - min(t.corrected, t.finished)) / t.ended, None
    if compared == "value.escalation_rate":
        return t.escalated / t.ended, None
    if compared == "value.automation":
        produced = t.by_hand + t.by_method
        return (
            (None, "no step result on this side")
            if produced == 0
            else (
                t.by_method / produced,
                None,
            )
        )
    if compared == "value.cost_per_case":
        if t.finished == 0:
            return None, "no run of the process finished on this side in the period"
        if cost is None:
            return None, "accounting priced no step of this side's runs"
        return cost / t.finished, None
    raise ValueError(f"no comparison of {compared}")


METHODS = {
    "value.cycle_seconds": "mean seconds from creation to end over the side's ended runs",
    "value.quality": "finished runs less corrected results, over the side's ended runs",
    "value.cost_per_case": "accounting's spend of the side's runs over its finished runs",
    "value.automation": "step results by a method other than a person, over the side's",
    "value.escalation_rate": "escalated runs over the side's ended runs",
}


def comparison(
    process: str,
    tallies: Mapping[Side, Tally],
    reads: Iterable[str],
    *,
    since: datetime,
    until: datetime,
    costs: Mapping[Side, float | None],
    currency: str,
) -> list[Figure]:
    """Both sides' cockpit figures of one process, and each figure's difference: with less
    without, withheld where a side has none (ADR-0291 §2)."""
    period = [since.isoformat(), until.isoformat()]
    steps = sorted(reads)
    out: list[Figure] = []

    def make(
        id: str,
        definition: str,
        unit: str,
        value: float | None,
        why: str | None,
        method: str,
        basis: dict[str, Any],
    ) -> Figure:
        return Figure(
            id=id,
            component=OWNER,
            definition=definition,
            unit=unit,
            scope="process",
            subject=process,
            since=since,
            until=until,
            value=None if why is not None or value is None else round(value, 6),
            withheld=why if why is not None else (None if value is not None else "none"),
            method=method,
            basis={**basis, "period": period, "knowledge_reads": steps},
        )

    for side in SIDES:
        t = tallies[side]
        out.append(
            make(
                f"{SIDE_ID[side]}.runs_ended",
                f"{DEFINITIONS['value.runs_ended'][0]}, of {SIDE_WORDS[side]}",
                "runs",
                t.ended,
                None,
                "counted",
                {"side": side, "runs": list(t.runs)},
            )
        )
    for compared in COMPARED:
        definition, unit = DEFINITIONS[compared]
        unit = currency if unit == "money" else unit
        values: dict[Side, float | None] = {}
        for side in SIDES:
            t = tallies[side]
            value, why = _value(compared, t, costs.get(side))
            values[side] = None if why is not None else value
            out.append(
                make(
                    figure_id(SIDE_ID[side], compared),
                    f"{definition}, of {SIDE_WORDS[side]}",
                    unit,
                    value,
                    why,
                    METHODS[compared],
                    {
                        "side": side,
                        "compares": compared,
                        "runs": list(t.runs),
                        "runs_ended": t.ended,
                        "runs_finished": t.finished,
                        "escalated": t.escalated,
                        "corrected": t.corrected,
                        **({"cost": costs.get(side)} if compared == "value.cost_per_case" else {}),
                    },
                )
            )
        missing = [s for s in SIDES if values[s] is None]
        why = (
            None
            if not missing
            else "the comparison needs the figure on both sides; it is withheld "
            + " and ".join(f"{s} knowledge" for s in missing)
        )
        effect = None if why else values["with"] - values["without"]  # type: ignore[operator]
        out.append(
            make(
                figure_id(EFFECT_ID, compared),
                f"{definition}: with knowledge connected less without",
                unit,
                effect,
                why,
                "the side with knowledge less the side without, each by its own method",
                {
                    "compares": compared,
                    "with": values["with"],
                    "without": values["without"],
                    "runs_with": tallies["with"].ended,
                    "runs_without": tallies["without"].ended,
                },
            )
        )
    return out
