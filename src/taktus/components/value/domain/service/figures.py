"""The value ledger's figures, computed from activity, accounting's cost and the stated basis
(ADR-0244 §3). Pure: the facts in, the figures out; nothing is stored.

Every figure names its method and its basis. A figure resting on the organisation's basis
says so, with the version and who set it when; a figure whose basis is missing is withheld
with what is missing, never shown as zero. No figure has a person as its scope.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import Any

from pydantic import Field

from taktus.components.value.domain.model import Figure, ValueBasis
from taktus.components.value.domain.model.figure import Scope
from taktus.components.value.domain.service.activity import Activity, Dependence
from taktus.shared.v1 import Value

OWNER = "value"
REPRODUCIBLE = frozenset({"rule", "statistics", "ml", "neural"})
VARIABLE = frozenset({"llm", "worker"})
PRODUCING = REPRODUCIBLE | VARIABLE
DAYS_PER_MONTH = 30.4375

DEFINITIONS: dict[str, tuple[str, str]] = {
    "value.runs_ended": ("runs of the process that finished or escalated in the period", "runs"),
    "value.cycle_seconds": (
        "the mean seconds from a run's creation to its end, over the runs that ended",
        "seconds",
    ),
    "value.quality": (
        "the share of ended runs that finished with no result a person corrected",
        "share",
    ),
    "value.cost_money": ("what the process's steps cost, as accounting priced them", "money"),
    "value.cost_takt": ("what the process's steps used, in Takt, as accounting counts it", "takt"),
    "value.automation": (
        "the share of step results produced by a method other than a person",
        "share",
    ),
    "value.escalation_rate": ("the share of ended runs that escalated", "share"),
    "value.time_saved_hours": (
        "runs finished times the minutes one case takes by hand, in hours",
        "hours",
    ),
    "value.personnel_equivalent": (
        "the time saved at the mean personnel cost rate of the roles that would do it by hand",
        "money",
    ),
    "value.error_cost": (
        "results a person corrected times the minutes by hand, at the same rate",
        "money",
    ),
    "value.licence_cost": ("the process's stated share of licences over the period", "money"),
    "value.balance": (
        "the personnel equivalent less the cost of steps, licences and rework",
        "money",
    ),
    "value.errors_avoided": (
        "step results a check that ran refused before they counted",
        "results",
    ),
    "value.payback_months": (
        "the investment the process took over its balance per month",
        "months",
    ),
    "value.cost_per_case": ("the cost of steps per run finished", "money"),
    "value.cost_per_case_by_hand": (
        "the minutes one case takes by hand at the personnel cost rate",
        "money",
    ),
    "value.revert_hours_month": (
        "the hours a month people would need to do the process again by hand",
        "hours",
    ),
    "value.revert_learn_hours": (
        "the hours a person needs to learn the process from its takeover instructions",
        "hours",
    ),
    "value.revert_response_minutes": (
        "how many minutes longer a case takes from request to done when people do it",
        "minutes",
    ),
    "value.bus_factor.without_taktus": (
        "processes whose active version has no passed takeover trial",
        "processes",
    ),
    "value.bus_factor.role": ("processes a person of the role is needed for", "processes"),
    "value.bus_factor.supplier": (
        "processes the supplier's current removal verdict says broke",
        "processes",
    ),
    "value.maturity": (
        "the mean of four shares: autonomy level over 4, reproducible step methods, passed "
        "takeover trials, suppliers whose removal broke nothing",
        "share",
    ),
    "value.plan_progress": ("the unit's maturity over the maturity its plan sets", "share"),
    "value.time_saved_change": (
        "the unit's time saved in the period less the period of the same length before",
        "hours",
    ),
    "value.simulated_unasked": (
        "decisions people took at the current level that would have run without asking at the next",
        "decisions",
    ),
    "value.simulated_wrong": (
        "of those, the decisions people corrected or rejected: what would have gone wrong",
        "decisions",
    ),
}
COCKPIT = (
    "value.cycle_seconds",
    "value.quality",
    "value.cost_money",
    "value.automation",
    "value.escalation_rate",
)
RELIEF = frozenset({"value.time_saved_hours", "value.personnel_equivalent"})
"""Figures of what Taktus took off people (UC-13.5 §2)."""


class ProcessFacts(Value):
    """One process's active version, as the composition gathers it from its owners."""

    process: str = Field(min_length=1)
    version: str = Field(min_length=1)
    """`process@version`."""
    level: int = Field(ge=0, le=4)
    methods: tuple[str, ...] = ()
    """The method kind of every step."""
    variable_steps: tuple[str, ...] = ()
    """The steps of a variable method (`llm`, `worker`)."""
    roles: tuple[str, ...] = ()
    """The roles a person of which the process needs: its steps' and its fallbacks'."""
    instructions: bool = False
    owner_role: str = "owner"
    stream: str | None = None
    unit: str | None = None
    cost_money: float | None = None
    """Accounting's cost of the period in the basis's currency; None where it priced nothing."""
    cost_takt: float | None = None
    trial_passed: bool | None = None
    """The newest takeover trial of the active version; None where there is none."""


class SupplierFacts(Value):
    integration: str = Field(min_length=1)
    verdict: str | None = None
    current: bool = False
    """Taken under a recorded configuration (UC-6.7 §2)."""
    broke: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    """Per process version its removal broke: the steps that broke."""


class BacklogSource(Value):
    kind: str = Field(pattern=r"^(proposal|discovered|entered)$")
    id: str = Field(min_length=1)
    unit: str | None = None
    title: str = Field(min_length=1)
    hours_per_month: float | None = None
    basis: str = Field(min_length=1)


class Facts(Value):
    tenant: str = Field(min_length=1)
    since: datetime
    until: datetime
    basis: ValueBasis | None = None
    basis_set: dict[str, Any] = Field(default_factory=dict)
    """The version, when it was set and by whom, as the ledger records it."""
    processes: tuple[ProcessFacts, ...] = ()
    suppliers: tuple[SupplierFacts, ...] = ()
    backlog: tuple[BacklogSource, ...] = ()


def _days(facts: Facts) -> tuple[date, date]:
    return facts.since.date(), (facts.until - timedelta(microseconds=1)).date()


def _months(facts: Facts) -> float:
    return max((facts.until - facts.since).total_seconds() / 86400 / DAYS_PER_MONTH, 1e-9)


class _Make:
    def __init__(self, facts: Facts) -> None:
        self.facts = facts

    def __call__(
        self,
        id: str,
        scope: Scope,
        subject: str,
        value: float | None,
        method: str,
        *,
        withheld: str | None = None,
        assumption: bool = False,
        simulation: bool = False,
        basis: Mapping[str, Any] | None = None,
    ) -> Figure:
        definition, unit = DEFINITIONS[id]
        if unit == "money" and self.facts.basis is not None:
            unit = self.facts.basis.currency
        given = dict(basis or {})
        given.setdefault("period", [self.facts.since.isoformat(), self.facts.until.isoformat()])
        if assumption and self.facts.basis_set:
            given.setdefault("basis", dict(self.facts.basis_set))
        return Figure(
            id=id,
            component=OWNER,
            definition=definition,
            unit=unit,
            scope=scope,
            subject=subject,
            since=self.facts.since,
            until=self.facts.until,
            value=None if withheld is not None or value is None else round(value, 6),
            withheld=withheld if withheld is not None else (None if value is not None else "none"),
            assumption=assumption,
            simulation=simulation,
            method=method,
            basis=given,
        )


def _share(part: float, whole: float) -> float | None:
    return None if whole == 0 else part / whole


def process_figures(facts: Facts, activity: Activity) -> list[Figure]:
    """The cockpit, the balance and the revert analysis of every process (UC-9.1, UC-9.3)."""
    make = _Make(facts)
    since, until = _days(facts)
    months = _months(facts)
    out: list[Figure] = []
    for p in facts.processes:
        c = activity.total(p.process, since, until)
        ended = c["finished"] + c["escalated"]
        runs = {"runs_ended": int(ended), "runs_finished": int(c["finished"])}
        none = "no run of the process ended in the period"
        out.append(make("value.runs_ended", "process", p.process, ended, "counted", basis=runs))
        cycle = None if ended == 0 else c["cycle_seconds"] / ended
        out.append(
            make(
                "value.cycle_seconds",
                "process",
                p.process,
                cycle,
                "mean over ended runs",
                withheld=none if cycle is None else None,
                basis=runs,
            )
        )
        quality = _share(c["finished"] - min(c["corrected"], c["finished"]), ended)
        out.append(
            make(
                "value.quality",
                "process",
                p.process,
                quality,
                "finished runs less corrected results, over ended runs",
                withheld=none if quality is None else None,
                basis={**runs, "corrected": int(c["corrected"])},
            )
        )
        out.append(
            make(
                "value.cost_money",
                "process",
                p.process,
                p.cost_money,
                "read from accounting's spend of the process",
                withheld="accounting priced no step of the period"
                if p.cost_money is None
                else None,
                basis=runs,
            )
        )
        out.append(
            make(
                "value.cost_takt",
                "process",
                p.process,
                p.cost_takt,
                "read from accounting's spend of the process",
                withheld="accounting counted no Takt in the period"
                if p.cost_takt is None
                else None,
                basis=runs,
            )
        )
        produced = c["by_person"] + c["by_method"]
        automation = _share(c["by_method"], produced)
        out.append(
            make(
                "value.automation",
                "process",
                p.process,
                automation,
                "step results by a method other than a person, over all step results",
                withheld="no step result in the period" if automation is None else None,
                basis={"by_person": int(c["by_person"]), "by_method": int(c["by_method"])},
            )
        )
        escalation = _share(c["escalated"], ended)
        out.append(
            make(
                "value.escalation_rate",
                "process",
                p.process,
                escalation,
                "escalated runs over ended runs",
                withheld=none if escalation is None else None,
                basis={**runs, "escalated": int(c["escalated"])},
            )
        )
        out.append(
            make(
                "value.errors_avoided",
                "process",
                p.process,
                c["check_failed"],
                "results a check refused, counted from the ledger",
                basis={"check_failed": int(c["check_failed"])},
            )
        )
        out.extend(_balance(make, facts, p, c, months))
        out.extend(_simulation(make, p, c))
    return out


def _balance(
    make: _Make, facts: Facts, p: ProcessFacts, c: Mapping[str, float], months: float
) -> list[Figure]:
    basis = None if facts.basis is None else facts.basis.of(p.process)
    out: list[Figure] = []
    stated: dict[str, Any] = {"roles_by_hand": list(basis.roles_by_hand) if basis else []}
    if basis is None or basis.minutes_by_hand is None:
        missing = "no time by hand is stated for the process"
        for id in (
            "value.time_saved_hours",
            "value.personnel_equivalent",
            "value.error_cost",
            "value.balance",
            "value.payback_months",
            "value.cost_per_case_by_hand",
            "value.revert_hours_month",
        ):
            out.append(
                make(
                    id,
                    "process",
                    p.process,
                    None,
                    "needs the time by hand",
                    withheld=missing,
                    assumption=True,
                    basis=stated,
                )
            )
    else:
        minutes = basis.minutes_by_hand
        stated = {**stated, "minutes_by_hand": minutes, "runs_finished": int(c["finished"])}
        hours = c["finished"] * minutes / 60
        out.append(
            make(
                "value.time_saved_hours",
                "process",
                p.process,
                hours,
                "runs finished times the minutes by hand",
                assumption=True,
                basis=stated,
            )
        )
        rate = None if facts.basis is None else facts.basis.rate(basis.roles_by_hand)
        no_rate = "no personnel cost rate is stated for the roles by hand"
        licence = basis.licence_per_month * months
        equivalent = None if rate is None else hours * rate
        error = None if rate is None else c["corrected"] * minutes / 60 * rate
        rated = {**stated, "rate_per_hour": rate, "corrected": int(c["corrected"])}
        out.append(
            make(
                "value.personnel_equivalent",
                "process",
                p.process,
                equivalent,
                "time saved at the mean rate of the roles by hand",
                withheld=no_rate if rate is None else None,
                assumption=True,
                basis=rated,
            )
        )
        out.append(
            make(
                "value.error_cost",
                "process",
                p.process,
                error,
                "corrected results times the minutes by hand at the rate",
                withheld=no_rate if rate is None else None,
                assumption=True,
                basis=rated,
            )
        )
        balance = None
        if equivalent is not None and error is not None:
            balance = equivalent - (p.cost_money or 0.0) - licence - error
        out.append(
            make(
                "value.balance",
                "process",
                p.process,
                balance,
                "personnel equivalent less cost of steps, licences and rework",
                withheld=no_rate if balance is None else None,
                assumption=True,
                basis={**rated, "cost_money": p.cost_money, "licence": licence},
            )
        )
        payback: float | None = None
        why = None
        if basis.investment is None:
            why = "no investment is stated for the process"
        elif balance is None:
            why = no_rate
        elif balance <= 0:
            why = "the balance is not positive: the investment does not pay back at this rate"
        else:
            payback = basis.investment / (balance / months)
        out.append(
            make(
                "value.payback_months",
                "process",
                p.process,
                payback,
                "investment over the balance per month",
                withheld=why,
                assumption=True,
                basis={**rated, "investment": basis.investment},
            )
        )
        out.append(
            make(
                "value.cost_per_case_by_hand",
                "process",
                p.process,
                None if rate is None else minutes / 60 * rate,
                "the minutes by hand at the rate",
                withheld=no_rate if rate is None else None,
                assumption=True,
                basis=rated,
            )
        )
        out.append(
            make(
                "value.revert_hours_month",
                "process",
                p.process,
                None if not p.instructions else hours / months,
                "hours saved per month: what people would need again",
                withheld=None if p.instructions else _NO_INSTRUCTIONS,
                assumption=True,
                basis=stated,
            )
        )
    out.append(
        make(
            "value.licence_cost",
            "process",
            p.process,
            0.0 if basis is None else basis.licence_per_month * months,
            "the stated licence share per month over the period",
            assumption=True,
        )
    )
    out.append(
        make(
            "value.cost_per_case",
            "process",
            p.process,
            None if p.cost_money is None or c["finished"] == 0 else p.cost_money / c["finished"],
            "accounting's cost over runs finished",
            withheld=None
            if p.cost_money is not None and c["finished"]
            else "no priced run finished in the period",
        )
    )
    learn = None if basis is None else basis.learn_hours
    out.append(
        make(
            "value.revert_learn_hours",
            "process",
            p.process,
            learn if p.instructions else None,
            "stated by the organisation",
            withheld=_NO_INSTRUCTIONS
            if not p.instructions
            else (None if learn is not None else "no time to learn is stated"),
            assumption=True,
        )
    )
    response = None if basis is None else basis.response_minutes_by_hand
    ended = c["finished"] + c["escalated"]
    change = None
    if p.instructions and response is not None and ended:
        change = response - c["cycle_seconds"] / ended / 60
    out.append(
        make(
            "value.revert_response_minutes",
            "process",
            p.process,
            change,
            "response by hand less the mean cycle of the runs",
            withheld=_NO_INSTRUCTIONS
            if not p.instructions
            else (None if change is not None else "no response by hand stated, or no run ended"),
            assumption=True,
            basis={"response_minutes_by_hand": response, "runs_ended": int(ended)},
        )
    )
    return out


_NO_INSTRUCTIONS = "the revert analysis cannot be made: the process has no takeover instructions"


def _simulation(make: _Make, p: ProcessFacts, c: Mapping[str, float]) -> list[Figure]:
    """What the next level would have meant, from the decisions people took (UC-9.1 §2)."""
    if p.level >= 4:
        return []
    decided = c["released"] + c["changed"] + c["refused"]
    basis = {
        "level_now": p.level,
        "level_simulated": p.level + 1,
        "released": int(c["released"]),
        "corrected": int(c["changed"]),
        "rejected": int(c["refused"]),
        "assumes": "every step a person decided at the current level would have run as decided, "
        "without asking, at the next",
    }
    return [
        make(
            "value.simulated_unasked",
            "process",
            p.process,
            decided,
            "decisions taken at the current level",
            simulation=True,
            basis=basis,
        ),
        make(
            "value.simulated_wrong",
            "process",
            p.process,
            c["changed"] + c["refused"],
            "decisions corrected or rejected",
            simulation=True,
            basis=basis,
        ),
    ]


def _sum(figures: Iterable[Figure], id: str) -> tuple[float | None, list[str]]:
    """The sum of a figure over the processes that have a value, and those that have none."""
    total, missing, any_value = 0.0, [], False
    for f in figures:
        if f.id != id:
            continue
        if f.value is None:
            missing.append(f.subject)
        else:
            total += f.value
            any_value = True
    return (total if any_value else None), missing


def proof_of_value(facts: Facts, per_process: Sequence[Figure]) -> list[Figure]:
    """The sums of the balance over the processes, each with its method and basis (UC-6.6)."""
    make = _Make(facts)
    out: list[Figure] = []
    for id in (
        "value.time_saved_hours",
        "value.personnel_equivalent",
        "value.cost_money",
        "value.error_cost",
        "value.licence_cost",
        "value.balance",
        "value.errors_avoided",
    ):
        total, missing = _sum(per_process, id)
        out.append(
            make(
                id,
                "tenant",
                facts.tenant,
                total,
                "the sum over the processes of the per-process figure of the same name",
                withheld=None if total is not None else "no process has a value for it",
                assumption=id not in ("value.cost_money", "value.errors_avoided"),
                basis={
                    "processes_without_value": missing,
                    "processes": [p.process for p in facts.processes],
                },
            )
        )
    finished = sum(
        f.basis.get("runs_finished", 0) for f in per_process if f.id == "value.runs_ended"
    )
    cost, _ = _sum(per_process, "value.cost_money")
    out.append(
        make(
            "value.cost_per_case",
            "tenant",
            facts.tenant,
            None if cost is None or not finished else cost / finished,
            "accounting's cost over every run finished",
            withheld=None if cost is not None and finished else "no priced run finished",
            basis={"runs_finished": finished},
        )
    )
    by_hand = [
        f.value
        for f in per_process
        if f.id == "value.cost_per_case_by_hand" and f.value is not None
    ]
    out.append(
        make(
            "value.cost_per_case_by_hand",
            "tenant",
            facts.tenant,
            None if not by_hand else statistics.fmean(by_hand),
            "the mean over the processes of a case by hand at its rate",
            withheld=None if by_hand else "no process states its time by hand and rate",
            assumption=True,
        )
    )
    investment = sum((p.investment or 0.0) for p in (facts.basis.processes if facts.basis else ()))
    balance, _ = _sum(per_process, "value.balance")
    months = _months(facts)
    payback = None
    why: str | None = "no investment is stated"
    if investment and balance is not None and balance > 0:
        payback, why = investment / (balance / months), None
    elif investment:
        why = "the balance is not positive"
    out.append(
        make(
            "value.payback_months",
            "tenant",
            facts.tenant,
            payback,
            "the stated investments over the balance per month",
            withheld=why,
            assumption=True,
            basis={"investment": investment},
        )
    )
    return out


# --- the bus-factor index (UC-6.7) -----------------------------------------------------------


class Index(Value):
    figures: tuple[Figure, ...]
    trend: tuple[dict[str, Any], ...]
    graph: tuple[dict[str, str], ...]
    """Edges: a process to `taktus`, to a role, to a supplier."""


def _supplier_state(s: SupplierFacts, versions: frozenset[str]) -> tuple[str, tuple[str, ...]]:
    """`broke`, `unknown` or `passed`, and the processes its removal broke."""
    if s.verdict is None or s.verdict == "untested":
        return "unknown", ()
    if not s.current:
        return "unknown", ()
    broke = tuple(sorted(v.rsplit("@", 1)[0] for v in s.broke if v in versions))
    stale = [v for v in s.broke if v not in versions]
    if s.verdict == "broke":
        return ("broke", broke) if broke or not stale else ("unknown", ())
    return "passed", ()


def bus_factor(facts: Facts, dependence: Dependence) -> Index:
    make = _Make(facts)
    versions = frozenset(p.version for p in facts.processes)
    without = [p.process for p in facts.processes if p.trial_passed is not True]
    figures = [
        make(
            "value.bus_factor.without_taktus",
            "tenant",
            facts.tenant,
            len(without),
            "counted from the newest takeover trial of each active version",
            basis={"processes": without},
        )
    ]
    streams = sorted({p.stream for p in facts.processes if p.stream})
    for stream in streams:
        held = [p.process for p in facts.processes if p.stream == stream and p.process in without]
        figures.append(
            make(
                "value.bus_factor.without_taktus",
                "stream",
                stream,
                len(held),
                "counted per value stream",
                basis={"processes": held},
            )
        )
    roles: dict[str, list[str]] = {}
    for p in facts.processes:
        by_hand = facts.basis.of(p.process) if facts.basis else None
        for role in {*p.roles, *(by_hand.roles_by_hand if by_hand else ())}:
            roles.setdefault(role, []).append(p.process)
    for role, processes in sorted(roles.items()):
        figures.append(
            make(
                "value.bus_factor.role",
                "role",
                role,
                len(processes),
                "counted from the steps and fallbacks that need the role",
                basis={"processes": sorted(processes)},
            )
        )
    graph: list[dict[str, str]] = [
        {"process": p, "on": "taktus", "kind": "taktus"} for p in without
    ]
    graph += [{"process": p, "on": r, "kind": "role"} for r, ps in roles.items() for p in ps]
    for s in facts.suppliers:
        state, broke = _supplier_state(s, versions)
        if state == "unknown":
            figures.append(
                make(
                    "value.bus_factor.supplier",
                    "supplier",
                    s.integration,
                    None,
                    "the supplier's current removal verdict",
                    withheld=f"unknown: verdict {s.verdict or 'none recorded'}"
                    + ("" if s.current else ", or taken without a configuration"),
                )
            )
        else:
            figures.append(
                make(
                    "value.bus_factor.supplier",
                    "supplier",
                    s.integration,
                    len(broke),
                    "the supplier's current removal verdict",
                    basis={"processes": list(broke), "verdict": s.verdict},
                )
            )
            graph += [{"process": p, "on": s.integration, "kind": "supplier"} for p in broke]
    trend = []
    day = facts.since.date()
    while day <= _days(facts)[1]:
        end = datetime.combine(day, datetime.min.time(), facts.since.tzinfo) + timedelta(days=1)
        trend.append(
            {
                "day": day.isoformat(),
                "without_taktus": sum(
                    1 for p in facts.processes if dependence.trial_at(p.version, end) is not True
                ),
                "suppliers_broke": sum(
                    1 for i in dependence.integrations() if dependence.verdict_at(i, end) == "broke"
                ),
            }
        )
        day += timedelta(days=1)
    return Index(figures=tuple(figures), trend=tuple(trend), graph=tuple(graph))


# --- the transformation (UC-9.2) --------------------------------------------------------------


def _maturity(p: ProcessFacts, broken: frozenset[str]) -> dict[str, float]:
    producing = [m for m in p.methods if m in PRODUCING]
    return {
        "autonomy": p.level / 4,
        "reproducible": 0.0
        if not producing
        else sum(1 for m in producing if m in REPRODUCIBLE) / len(producing),
        "takeover": 1.0 if p.trial_passed is True else 0.0,
        "suppliers": 0.0 if p.process in broken else 1.0,
    }


def transformation(
    facts: Facts, activity: Activity, per_process: Sequence[Figure]
) -> tuple[list[Figure], list[dict[str, Any]]]:
    """The maturity of each unit, its progress against the plan with the change in time saved
    it brought, and the backlog of potential."""
    make = _Make(facts)
    versions = frozenset(p.version for p in facts.processes)
    broken = frozenset(p for s in facts.suppliers for p in _supplier_state(s, versions)[1])
    units: dict[str, list[ProcessFacts]] = {}
    for p in facts.processes:
        if p.unit:
            units.setdefault(p.unit, []).append(p)
    out: list[Figure] = []
    length = facts.until - facts.since
    before = Facts(**{**facts.model_dump(), "since": facts.since - length, "until": facts.since})
    earlier = process_figures(before, activity)
    for unit, processes in sorted(units.items()):
        parts = {p.process: _maturity(p, broken) for p in processes}
        maturity = statistics.fmean(statistics.fmean(v.values()) for v in parts.values())
        out.append(
            make(
                "value.maturity",
                "unit",
                unit,
                maturity,
                "computed from the unit's processes as they run",
                basis={"processes": parts},
            )
        )
        target = next(
            (t for t in (facts.basis.plan if facts.basis else ()) if t.unit == unit), None
        )
        out.append(
            make(
                "value.plan_progress",
                "unit",
                unit,
                None if target is None or target.maturity == 0 else maturity / target.maturity,
                "maturity over the plan's target",
                withheld=None if target is not None else "the plan sets no target for it",
                basis={}
                if target is None
                else {"target": target.maturity, "due": target.due.isoformat()},
            )
        )
        names = {p.process for p in processes}
        now, _ = _sum([f for f in per_process if f.subject in names], "value.time_saved_hours")
        then, _ = _sum([f for f in earlier if f.subject in names], "value.time_saved_hours")
        out.append(
            make(
                "value.time_saved_change",
                "unit",
                unit,
                None if now is None else now - (then or 0.0),
                "the time saved now less the period before",
                withheld=None if now is not None else "no time by hand is stated",
                assumption=True,
                basis={"before": [before.since.isoformat(), before.until.isoformat()]},
            )
        )
    backlog = [
        {**b.model_dump(), "expectation": True}
        for b in sorted(facts.backlog, key=lambda b: -(b.hours_per_month or 0.0))
    ]
    return out, backlog
