"""What acts for a tenant, and what depends on it, drawn from facts (ADR-0147 §2, §3).

Plain functions over the facts of `domain/model/acting.py`; nothing here reads a store. The
one projection, `UsedProjection`, folds what each adapter's steps used per day out of
`step.finished` entries (ADR-0105). No function takes a person or returns a figure about one.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from taktus.components.reporting.domain.model.acting import (
    ActorFacts,
    Reached,
    Register,
    RegisterRow,
    RemoveView,
    Residency,
    ResidencyRow,
    ResidencyView,
    Used,
    WrongResultView,
)
from taktus.ports.model import LOCATIONS, PERMITTED, admits
from taktus.shared.v1 import EGRESS_KINDS, ExactnessClass, LedgerEntry, Provenance

STRENGTH: tuple[ExactnessClass, ...] = (
    ExactnessClass.FREE,
    ExactnessClass.TOLERANT,
    ExactnessClass.SOURCED,
    ExactnessClass.EXACT,
)
"""The exactness classes from the weakest to the strongest."""

RETAIN_DAYS = 30
"""The days the projection of use keeps: the register's period, and one of margin."""

PERIOD_DAYS = 28
"""The register's period: four whole weeks."""

NOT_LEGALLY_REVIEWED = (
    "Generated from the configuration Taktus runs with. Not legally reviewed: it is a draft for "
    "the deployer's own inventory, never a statement of compliance."
)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}{'es' if word.endswith('s') else 's'}"


def residency_of(location: str | None, permitted: str) -> Residency:
    """Whether an adapter's location lies inside what the rule permits."""
    if location is None:
        return "undeclared"
    if permitted not in PERMITTED or location not in LOCATIONS:
        return "undeclared"
    inside = admits(permitted, location)
    return "inside" if inside else "outside"


def strongest(classes: Iterable[ExactnessClass | None]) -> ExactnessClass | None:
    found = [c for c in classes if c is not None]
    return max(found, key=STRENGTH.index) if found else None


def attention(facts: ActorFacts, residency: Residency) -> tuple[str, ...]:
    """Why a row needs a person's attention (ADR-0147 §2), most serious first."""
    reasons: list[str] = []
    if facts.stopped:
        reasons.append("a stop of it is held")
    breaking = sorted({u.process_id for u in facts.uses if u.without == "breaks"})
    if breaking:
        reasons.append(
            f"without it {_plural(len(breaking), 'process')} would break: {', '.join(breaking)}"
        )
    if facts.removal is not None and facts.removal.verdict == "broke":
        reasons.append(f"the removal test of {facts.removal.tested_at.date()} found it breaks")
    if facts.uses and facts.removal is None:
        reasons.append("processes use it and it was never removal-tested")
    if residency == "outside":
        reasons.append(f"it processes at {facts.location}, outside the tenant's residency rule")
    above = [u for u in facts.uses if u.level > 2]
    if above and facts.maturity not in ("verified", "reference", None):
        reasons.append(
            f"a step runs on it at level {max(u.level for u in above)} while it is {facts.maturity}"
        )
    return tuple(reasons)


def row(facts: ActorFacts, permitted: str) -> RegisterRow:
    residency = residency_of(facts.location, permitted)
    reasons = attention(facts, residency)
    processes = tuple(sorted({u.process_id for u in facts.uses}))
    level = max((u.level for u in facts.uses), default=None)
    exactness = strongest(u.exactness for u in facts.uses)
    text = [f"{facts.adapter}, a {facts.family}"]
    if facts.serves:
        text.append(f"serves {', '.join(facts.serves)}")
    if processes:
        text.append(
            f"acts in {_plural(len(processes), 'process')} up to level {level}"
            + ("" if exactness is None else f", producing {exactness} results at most")
        )
    else:
        text.append("no process uses it")
    text.append(f"maturity {facts.maturity or 'none: it is no integration'}")
    if facts.removal is not None:
        text.append(
            f"last removal test {facts.removal.verdict} on {facts.removal.tested_at.date()}"
        )
    sentence = "; ".join(text) + "."
    if reasons:
        sentence += " Needs attention: " + "; ".join(reasons) + "."
    return RegisterRow(
        adapter=facts.adapter,
        family=facts.family,
        serves=facts.serves,
        maturity=facts.maturity,
        missing=facts.missing,
        removal=facts.removal,
        level=level,
        exactness=exactness,
        location=facts.location,
        residency=residency,
        processes=processes,
        uses=facts.uses,
        used=facts.used,
        stopped=facts.stopped,
        attention=reasons,
        text=sentence,
    )


def register(tenant: str, facts: Sequence[ActorFacts], permitted: str) -> Register:
    """Every adapter, those that need attention first, then by identifier."""
    rows = sorted((row(f, permitted) for f in facts), key=lambda r: (not r.attention, r.adapter))
    needing = sum(1 for r in rows if r.attention)
    if not rows:
        summary = "Nothing acts for this tenant: no worker, connector or model is configured."
    else:
        summary = f"{_plural(len(rows), 'adapter')} can act for this tenant; " + (
            "none needs attention." if needing == 0 else f"{needing} need attention."
        )
    return Register(tenant=tenant, permitted=permitted, rows=tuple(rows), summary=summary)


def inventory(register: Register, generated_at: datetime) -> dict[str, Any]:
    """The register in the shape a deployer's inventory of AI systems asks for, marked as not
    legally reviewed (ADR-0147 §2)."""
    systems = []
    for r in register.rows:
        roles = sorted({u.role for u in r.uses if u.role is not None})
        systems.append(
            {
                "identifier": r.adapter,
                "kind": r.family,
                "purpose": {
                    "serves": list(r.serves),
                    "processes": list(r.processes),
                },
                "human_oversight": {
                    "highest_autonomy_level": r.level,
                    "roles_taking_over": roles,
                    "stop": "a person stops it at any time; every run halts at its next step "
                    "boundary (ADR-0138)",
                },
                "results": {"strongest_exactness": r.exactness},
                "processing_location": r.location or "undeclared",
                "within_residency_rule": r.residency,
                "evidence": {
                    "maturity": r.maturity,
                    "missing": list(r.missing),
                    "removal_test": None if r.removal is None else r.removal.document(),
                },
            }
        )
    return {
        "tenant": register.tenant,
        "generated_at": generated_at.isoformat(),
        "legally_reviewed": False,
        "notice": NOT_LEGALLY_REVIEWED,
        "systems": systems,
    }


def remove_view(adapter: str, facts: ActorFacts | None) -> RemoveView:
    """What breaks and what degrades if the adapter goes (ADR-0147 §3)."""
    if facts is None:
        return RemoveView(
            adapter=adapter,
            configured=False,
            breaks=(),
            degrades=(),
            removal=None,
            summary=f"{adapter} is not configured: nothing depends on it.",
        )
    breaks = tuple(u for u in facts.uses if u.without == "breaks")
    degrades = tuple(u for u in facts.uses if u.without == "degrades")
    broken = sorted({u.process_id for u in breaks})
    degraded = sorted({u.process_id for u in degrades} - set(broken))
    if not facts.uses:
        summary = f"No process uses {adapter}: removing it breaks nothing and changes nothing."
    else:
        parts = []
        if broken:
            parts.append(f"{_plural(len(broken), 'process')} would break ({', '.join(broken)})")
        if degraded:
            parts.append(
                f"{_plural(len(degraded), 'process')} would only degrade ({', '.join(degraded)})"
            )
        summary = f"Without {adapter}: " + "; ".join(parts) + "."
    return RemoveView(
        adapter=adapter,
        configured=True,
        breaks=breaks,
        degrades=degrades,
        removal=facts.removal,
        summary=summary,
    )


def wrong_result(
    run_id: str,
    step_id: str,
    own: Provenance | None,
    reached: Sequence[Provenance],
    egress: Iterable[LedgerEntry],
) -> WrongResultView:
    """Where a wrong result went: every step run that read it, forward, and what of them left
    the system. The window of UC-4.11 is not computed here, and the view says so."""
    left_by: dict[tuple[str, str], set[str]] = {}
    for entry in egress:
        if entry.kind in EGRESS_KINDS and entry.refs.run_id and entry.refs.step_id:
            left_by.setdefault((entry.refs.run_id, entry.refs.step_id), set()).add(entry.kind)
    steps = tuple(
        Reached(
            run_id=p.run_id,
            step_id=p.step_id,
            process_version=p.process_version,
            exactness=p.exactness,
            recorded_at=p.recorded_at,
            left=tuple(sorted(left_by.get((p.run_id, p.step_id), ()))),
        )
        for p in reached
    )
    itself = tuple(sorted(left_by.get((run_id, step_id), ())))
    built: dict[str, int] = {}
    for s in steps:
        built[s.process_version] = built.get(s.process_version, 0) + 1
    left = sum(1 for s in steps if s.left) + (1 if itself else 0)
    since = (
        "Since when is UC-4.11's error window, which this view does not compute: it starts "
        "from this one result."
    )
    if own is None:
        summary = f"No record of {step_id} in {run_id} you may see: nothing to follow."
    else:
        summary = (
            f"The result of {step_id} in {run_id} reached "
            f"{_plural(len(steps), 'step run')} in {_plural(len(built), 'process version')}; "
            f"{left} of them, the result included, left the system."
        )
    return WrongResultView(
        run_id=run_id,
        step_id=step_id,
        process_version=None if own is None else own.process_version,
        exactness=None if own is None else own.exactness,
        left_itself=itself,
        reached=steps,
        affected=len(steps) + (0 if own is None else 1),
        built_on=dict(sorted(built.items())),
        left=left,
        since_when=since,
        summary=summary,
    )


def residency_view(facts: Sequence[ActorFacts], permitted: str) -> ResidencyView:
    rows = tuple(
        ResidencyRow(
            adapter=f.adapter,
            family=f.family,
            location=f.location,
            residency=residency_of(f.location, permitted),
            processes=tuple(sorted({u.process_id for u in f.uses})),
        )
        for f in sorted(facts, key=lambda f: f.adapter)
    )
    outside = [r.adapter for r in rows if r.residency == "outside"]
    undeclared = sum(1 for r in rows if r.residency == "undeclared")
    summary = f"The tenant's rule permits processing {permitted}. " + (
        "Nothing processes outside it" if not outside else f"Outside it: {', '.join(outside)}"
    )
    summary += "." if not undeclared else f"; {_plural(undeclared, 'adapter')} declare no location."
    return ResidencyView(permitted=permitted, rows=rows, summary=summary)


# --- what each adapter used, as a projection of the ledger ---------------------------------------


@dataclass
class Uses:
    """Per day, per adapter: steps finished, the runs they belong to, tokens, compute seconds
    and money by currency."""

    days: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    newest: str = ""

    def used(self, adapter: str, since: date, period: int = PERIOD_DAYS) -> Used:
        steps = tokens = 0
        compute = 0.0
        runs: set[str] = set()
        money: dict[str, float] = {}
        for day, adapters in self.days.items():
            if date.fromisoformat(day) < since:
                continue
            held = adapters.get(adapter)
            if held is None:
                continue
            steps += held["steps"]
            tokens += held["tokens"]
            compute += held["compute_seconds"]
            runs.update(held["runs"])
            for currency, amount in held["money"].items():
                money[currency] = money.get(currency, 0.0) + amount
        return Used(
            days=period,
            steps=steps,
            runs=len(runs),
            tokens=tokens,
            compute_seconds=round(compute, 3),
            money={k: round(v, 6) for k, v in sorted(money.items())},
        )


def fold_use(state: Uses, entry: LedgerEntry) -> Uses:
    if entry.kind != "step.finished" or entry.adapter is None or entry.rehearsal:
        return state
    day = entry.ts.date().isoformat()
    held = state.days.setdefault(day, {}).setdefault(
        entry.adapter,
        {"steps": 0, "runs": [], "tokens": 0, "compute_seconds": 0.0, "money": {}},
    )
    held["steps"] += 1
    if entry.refs.run_id is not None and entry.refs.run_id not in held["runs"]:
        held["runs"].append(entry.refs.run_id)
    used = entry.consumption
    if used is not None:
        held["tokens"] += (used.tokens_in or 0) + (used.tokens_out or 0)
        held["compute_seconds"] += used.compute_seconds or 0.0
        for currency, amount in (used.currency or {}).items():
            held["money"][currency] = held["money"].get(currency, 0.0) + amount
    if day > state.newest:
        state.newest = day
        cutoff = (date.fromisoformat(day) - timedelta(days=RETAIN_DAYS)).isoformat()
        for old in [d for d in state.days if d < cutoff]:
            del state.days[old]
    return state


def every_use(entries: Iterable[LedgerEntry]) -> Uses:
    """The full computation the projection must equal."""
    state = Uses()
    for entry in entries:
        fold_use(state, entry)
    return state


class UsedProjection:
    name = "reporting.used.v1"
    kinds: frozenset[str] | None = frozenset({"step.finished"})

    def empty(self) -> Uses:
        return Uses()

    def fold(self, state: Uses, entry: LedgerEntry) -> Uses:
        return fold_use(state, entry)

    def dump(self, state: Uses) -> dict[str, Any]:
        return {"newest": state.newest, "days": state.days}

    def load(self, document: Mapping[str, Any]) -> Uses:
        return Uses(
            days={k: dict(v) for k, v in document["days"].items()}, newest=document["newest"]
        )


USED = UsedProjection()
