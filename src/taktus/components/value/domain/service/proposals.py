"""What to do, from the figures: a target missed, a dependency that deteriorated, and the
recommendation of each process's quadrant (ADR-0244 §4). Computed on every read; nothing is
stored, and nothing changes: every proposal is addressed to a role and stays a proposal.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence

from taktus.components.value.domain.model import Figure, ValueProposal
from taktus.components.value.domain.service.activity import Dependence
from taktus.components.value.domain.service.figures import Facts, _supplier_state

RELEVANT = frozenset({"critical", "important"})


def _value(figures: Sequence[Figure], id: str, process: str) -> Figure | None:
    return next(
        (f for f in figures if f.id == id and f.scope == "process" and f.subject == process), None
    )


def targets_missed(facts: Facts, figures: Sequence[Figure]) -> list[ValueProposal]:
    """A cockpit figure outside the target set for it (UC-9.1 §2)."""
    out: list[ValueProposal] = []
    owners = {p.process: p.owner_role for p in facts.processes}
    for target in facts.basis.targets if facts.basis else ():
        figure = _value(figures, target.figure, target.process)
        if figure is None or figure.value is None:
            continue
        low = target.low is not None and figure.value < target.low
        high = target.high is not None and figure.value > target.high
        if not (low or high):
            continue
        runs = _value(figures, "value.runs_ended", target.process)
        out.append(
            ValueProposal(
                kind="target",
                process=target.process,
                figure=target.figure,
                addressed_to=owners.get(target.process, "owner"),
                text=f"{target.figure} of {target.process} is {figure.value:g}, "
                f"{'below' if low else 'above'} its target "
                f"[{'' if target.low is None else f'{target.low:g}'}, "
                f"{'' if target.high is None else f'{target.high:g}'}] "
                f"from {facts.since.date()} to {facts.until.date()}: look at its runs.",
                basis={
                    "value": figure.value,
                    "low": target.low,
                    "high": target.high,
                    "period": [facts.since.isoformat(), facts.until.isoformat()],
                    "runs_ended": None if runs is None else runs.value,
                },
            )
        )
    return out


def deteriorations(facts: Facts, dependence: Dependence) -> list[ValueProposal]:
    """A process or a supplier that passed at the start of the period and no longer does
    (UC-6.7 §2): named with the test that failed and the step that would restore it."""
    out: list[ValueProposal] = []
    start = facts.since
    for p in facts.processes:
        if dependence.trial_at(p.version, start) is True and p.trial_passed is not True:
            out.append(
                ValueProposal(
                    kind="deterioration",
                    process=p.process,
                    addressed_to=p.owner_role,
                    text=f"The takeover trial of {p.version} no longer passes: complete its "
                    "takeover instructions with what the trial found missing, and run the "
                    "trial again.",
                    basis={"test": "takeover", "version": p.version},
                )
            )
    versions = frozenset(p.version for p in facts.processes)
    for s in facts.suppliers:
        state, _ = _supplier_state(s, versions)
        if state != "broke" or dependence.verdict_at(s.integration, start) == "broke":
            continue
        for version, steps in sorted(s.broke.items()):
            if version not in versions:
                continue
            out.append(
                ValueProposal(
                    kind="deterioration",
                    process=version.rsplit("@", 1)[0],
                    text=f"Removing {s.integration} breaks {version} at "
                    f"{', '.join(steps) or 'a step'}: give "
                    f"{'those steps' if len(steps) > 1 else 'that step'} a fallback that does "
                    "not need it.",
                    basis={"test": "removal", "integration": s.integration, "steps": list(steps)},
                )
            )
    return out


def quadrants(facts: Facts, figures: Sequence[Figure]) -> list[ValueProposal]:
    """Every process in the matrix of cost against relevance, with its recommendation
    (UC-9.3 §1). Cost is the cost of steps and licences per month; the boundary is the median
    over the tenant's processes."""
    months = max((facts.until - facts.since).total_seconds() / 86400 / 30.4375, 1e-9)
    cost: dict[str, float] = {}
    for p in facts.processes:
        money = _value(figures, "value.cost_money", p.process)
        licence = _value(figures, "value.licence_cost", p.process)
        cost[p.process] = (
            (money.value if money and money.value is not None else 0.0)
            + (licence.value if licence and licence.value is not None else 0.0)
        ) / months
    median = statistics.median(cost.values()) if cost else 0.0
    out: list[ValueProposal] = []
    for p in facts.processes:
        basis = facts.basis.of(p.process) if facts.basis else None
        relevance = "important" if basis is None else basis.relevance
        expensive = cost[p.process] > median
        relevant = relevance in RELEVANT
        quadrant = f"{'expensive' if expensive else 'cheap'} and " + (
            "relevant" if relevant else "not relevant"
        )
        data = {
            "quadrant": quadrant,
            "cost_per_month": round(cost[p.process], 6),
            "median_cost_per_month": round(median, 6),
            "relevance": relevance,
            "relevance_stated": basis is not None,
        }
        if expensive and relevant:
            first = (
                f"a more reproducible method for {', '.join(p.variable_steps)} first, a cheaper "
                "model second"
                if p.variable_steps
                else "no step is of a variable method: a cheaper adapter or fewer steps"
            )
            out.append(
                ValueProposal(
                    kind="optimise",
                    process=p.process,
                    addressed_to=p.owner_role,
                    text=f"{p.process} is {quadrant}: optimise it — {first}.",
                    basis={**data, "variable_steps": list(p.variable_steps)},
                )
            )
        elif relevant and p.level < 4:
            out.append(
                ValueProposal(
                    kind="raise_autonomy",
                    process=p.process,
                    addressed_to=p.owner_role,
                    text=f"{p.process} is {quadrant}: raising its autonomy from "
                    f"level {p.level} is proposed to its owner, who decides.",
                    basis=data,
                )
            )
        elif expensive:
            out.append(
                ValueProposal(
                    kind="switch_off",
                    process=p.process,
                    addressed_to="owner",
                    text=f"{p.process} is {quadrant}: a candidate to switch off or rebuild.",
                    basis=data,
                )
            )
        else:
            out.append(
                ValueProposal(
                    kind="observe",
                    process=p.process,
                    addressed_to=p.owner_role,
                    text=f"{p.process} is {quadrant}: observe it.",
                    basis=data,
                )
            )
    return out


def proposals(
    facts: Facts, figures: Sequence[Figure], dependence: Dependence
) -> list[ValueProposal]:
    return [
        *targets_missed(facts, figures),
        *deteriorations(facts, dependence),
        *quadrants(facts, figures),
    ]
