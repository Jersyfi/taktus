"""What a higher limit would have bought, what to do about it, and how to wait less on people
(ADR-0015 §2 to §4, ADR-0283, UC-9.5).

Three answers, each a rule over the blocks the run recorded:

1. **Marginal value**, per limit account and process: the steps and runs the blocks held up,
   how many seconds earlier they would have started had the limit been higher — each when it
   was refused, not when it was admitted — and by how much higher, per quantity. Tokens, quota
   units, compute seconds and places are exact; money is an estimate, because the money a step
   uses is known only when its assignment reports it (ADR-0005). A cause whose record carries no
   shortfall is named, never guessed.
2. **A recommendation** per marginal value, naming its expected effect, its cost and its value.
   A change of method is checked first (ADR-0004); a raise is recommended only where every check
   found none, and every check is named.
3. **Offers** of the four ways to wait less on people, each where the records give a reason
   for it, with the mechanism that carries it out. No offer names a person.

Pure: blocks, checks, groups and rules in; values out. The order is by key, never by a figure.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Literal

from pydantic import Field

from taktus.components.accounting.ports.bottlenecks import (
    Blocked,
    MethodChecked,
    RecurringRule,
    WaitGroup,
)
from taktus.shared.v1 import Value

LIMIT_ACCOUNTS = ("limit.provider", "limit.quota", "limit.budget", "limit.compute")
"""The accounts whose blocks a higher limit would have ended sooner (ADR-0015 §1)."""
ADMISSION = "rejected_by_admission"
"""A refusal by admission control: its record carries the shortfall (ADR-0283 §1)."""
CAPACITY = frozenset({"at_capacity", "rejected_by_capacity"})
"""The causes whose raise is counted in places: more assignments at once."""
PLACES = "places"
HELD_BACK = "held_back"
UNMEASURED: Mapping[str, str] = {
    "at_provider_limit": "a provider's rate limit is the provider's; its height is not recorded",
    "halted_at_limit": "the worker halted at its own ceiling; what it would have used is not "
    "recorded",
    "at_unit_quota": "a unit's places are a quota of the tenant; the raise is not recorded",
    "at_unit_budget": "a unit's monthly budget holds the run's whole budget; the raise is not "
    "recorded",
    "at_tenant_budget": "the tenant's monthly budget holds every run; the raise is not recorded",
}
"""Why a cause's raise cannot be read from its records."""
BEFORE = "a refusal recorded before its shortfall was (ADR-0283)"


class Quantity(Value):
    """How much higher one limit would have had to be."""

    name: str = Field(min_length=1)
    """`currency.<code>`, `quota_units`, `tokens_in`, `tokens_out`, `compute_seconds` or
    `places`."""
    amount: float = Field(ge=0)
    exact: bool
    """True for tokens, quota units, compute seconds and places; money is an estimate."""


class MarginalValue(Value):
    """What a higher limit of one account would have bought in one process."""

    account: str
    process: str
    blocks: int = Field(ge=1)
    runs: int = Field(ge=1)
    """The runs that would have gone on sooner."""
    steps: tuple[str, ...]
    """The steps that would have started sooner, as `<process version>/<step>`."""
    seconds_earlier: float = Field(ge=0)
    """How much sooner, added up: each step when it was refused, not when it was admitted."""
    since: datetime
    until: datetime
    raises: tuple[Quantity, ...] = ()
    """How much higher, per quantity: the raise that would have let every step start when it
    was refused."""
    unmeasured: tuple[str, ...] = ()
    """The causes whose raise the records do not say, each with why."""
    estimate: bool = False
    """True where a raise is in money: an estimate, not a measure."""


def _is_exact(name: str) -> bool:
    return not name.startswith("currency.")


def _places(blocks: Sequence[Blocked]) -> int:
    """The most blocks open at the same moment: the places that would have let each start when
    it was refused. A block that ends when another begins does not overlap it."""
    events = sorted(
        [(b.since, 1) for b in blocks] + [(b.until, -1) for b in blocks],
        key=lambda event: (event[0], event[1]),
    )
    now = most = 0
    for _, change in events:
        now += change
        most = max(most, now)
    return most


def marginal_values(blocks: Iterable[Blocked]) -> tuple[MarginalValue, ...]:
    """Per limit account and process, what a higher limit would have bought."""
    held: dict[tuple[str, str], list[Blocked]] = defaultdict(list)
    for block in blocks:
        if block.account in LIMIT_ACCOUNTS:
            held[(block.account, block.process)].append(block)
    found: list[MarginalValue] = []
    for (account, process), group in sorted(held.items()):
        per_run: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        unmeasured: set[str] = set()
        capacity: list[Blocked] = []
        for block in group:
            if block.cause == ADMISSION and block.short is not None:
                for name, amount in block.short.items():
                    per_run[block.run_id][name] += amount
            elif block.cause == ADMISSION:
                unmeasured.add(f"{block.cause}: {BEFORE}")
            elif block.cause in CAPACITY:
                capacity.append(block)
            else:
                why = UNMEASURED.get(block.cause, "its raise is not recorded")
                unmeasured.add(f"{block.cause}: {why}")
        most: dict[str, float] = {}
        for shortfalls in per_run.values():
            for name, amount in shortfalls.items():
                most[name] = max(most.get(name, 0.0), amount)
        raises = [
            Quantity(name=name, amount=round(amount, 9), exact=_is_exact(name))
            for name, amount in sorted(most.items())
        ]
        if capacity:
            raises.append(Quantity(name=PLACES, amount=_places(capacity), exact=True))
        found.append(
            MarginalValue(
                account=account,
                process=process,
                blocks=len(group),
                runs=len({b.run_id for b in group}),
                steps=tuple(sorted({f"{b.process_version}/{b.step_id}" for b in group})),
                seconds_earlier=sum(b.seconds for b in group),
                since=min(b.since for b in group),
                until=max(b.until for b in group),
                raises=tuple(raises),
                unmeasured=tuple(sorted(unmeasured)),
                estimate=any(not q.exact for q in raises),
            )
        )
    return tuple(found)


def held_up(value: MarginalValue) -> tuple[tuple[str, str], ...]:
    """The steps a marginal value held up, as (process version, step)."""
    return tuple((step.rsplit("/", 1)[0], step.rsplit("/", 1)[1]) for step in value.steps)


type Action = Literal["change_method", "raise_limit", "none"]


class Recommendation(Value):
    """What to do about one marginal value: its action, its expected effect, its cost and its
    value, and the check for a change of method it rests on."""

    account: str
    process: str
    action: Action
    effect: str
    """What the action would have changed, in one line."""
    effect_seconds: float = Field(ge=0)
    """How many seconds sooner the work would have gone on, added up."""
    cost: tuple[Quantity, ...] = ()
    """What the action costs, per quantity, in the limit's own units: a raise for
    `raise_limit`, nothing for a change of method."""
    cost_text: str
    value: dict[str, float] = Field(default_factory=dict)
    """Seconds sooner per unit raised, per quantity."""
    value_text: str
    checks: tuple[str, ...]
    """Every check for a change of method, by step, with what it found (ADR-0004)."""
    alternatives: tuple[str, ...] = ()
    """The steps where a change of method may remove the bottleneck, with the method."""


def _amount(quantity: Quantity) -> str:
    mark = "" if quantity.exact else " (estimate)"
    return f"{quantity.name} by {quantity.amount:g}{mark}"


def recommend(
    value: MarginalValue, checked: Mapping[tuple[str, str], MethodChecked]
) -> Recommendation:
    """The recommendation for one marginal value. A change of method comes first: a raise is
    recommended only where every step's check found none (ADR-0015 §3)."""
    steps = held_up(value)
    checks = tuple(
        f"{pv}/{step}: {checked[(pv, step)].check}"
        if (pv, step) in checked
        else f"{pv}/{step}: not checked"
        for pv, step in steps
    )
    alternatives = tuple(
        f"{pv}/{step}: {found.alternative}"
        for pv, step in steps
        if (found := checked.get((pv, step))) is not None and found.alternative is not None
    )
    effect = (
        f"{len(value.steps)} step(s) of {value.runs} run(s) would have started "
        f"{value.seconds_earlier:g} s sooner in all"
    )
    if alternatives:
        return Recommendation(
            account=value.account,
            process=value.process,
            action="change_method",
            effect=effect + ", without consuming the limit as they do now",
            effect_seconds=value.seconds_earlier,
            cost_text="no raise of the limit: a move is proposed only on evidence of a lower "
            "cost per case (ADR-0084)",
            value_text=f"{value.seconds_earlier:g} s sooner at no extra cost",
            checks=checks,
            alternatives=alternatives,
        )
    if value.raises:
        per_unit = {
            q.name: round(value.seconds_earlier / q.amount, 9) for q in value.raises if q.amount > 0
        }
        return Recommendation(
            account=value.account,
            process=value.process,
            action="raise_limit",
            effect=effect,
            effect_seconds=value.seconds_earlier,
            cost=value.raises,
            cost_text="raise " + ", ".join(_amount(q) for q in value.raises),
            value=per_unit,
            value_text=", ".join(
                f"{seconds:g} s sooner per unit of {name}" for name, seconds in per_unit.items()
            )
            or "no time gained",
            checks=checks,
        )
    return Recommendation(
        account=value.account,
        process=value.process,
        action="none",
        effect=effect,
        effect_seconds=value.seconds_earlier,
        cost_text="not measured: " + "; ".join(value.unmeasured),
        value_text="not measured without a raise",
        checks=checks,
    )


type Way = Literal["carry_on", "deadline_with_deputy", "batching", "rule"]


class Offer(Value):
    """One way to wait less on people, offered where the records give a reason for it."""

    way: Way
    where: str = Field(min_length=1)
    """The process or the role it is offered for."""
    evidence: str = Field(min_length=1)
    how: str = Field(min_length=1)
    """The mechanism that carries it out."""
    decider: str | None = None
    """For a rule: the role whose rule it is, and who retires it. Never a person."""
    withdrawable: bool = False


def offers(
    blocks: Iterable[Blocked],
    by_role: Iterable[WaitGroup],
    rules: Iterable[RecurringRule],
) -> tuple[Offer, ...]:
    """The four ways to wait less on people (ADR-0015 §4), in the order of the ways and then of
    where they are offered."""
    found: list[Offer] = []
    held: dict[str, list[Blocked]] = defaultdict(list)
    for block in blocks:
        if block.account == "wait.dependency" and block.cause == HELD_BACK:
            held[block.process].append(block)
    for process, group in sorted(held.items()):
        found.append(
            Offer(
                way="carry_on",
                where=process,
                evidence=f"{len({(b.run_id, b.step_id) for b in group})} step(s) of "
                f"{len({b.run_id for b in group})} run(s) were held back "
                f"{sum(b.seconds for b in group):g} s behind a step that waited for a person",
                how="a waiting step holds back only the steps that depend on it (ADR-0039): a "
                "step that does not need the awaited result drops it from its dependencies "
                "and runs while the person decides",
            )
        )
    roles: dict[str, list[WaitGroup]] = defaultdict(list)
    for wait in by_role:
        if wait.grouping == "role":
            roles[wait.group].append(wait)
    for role, groups in sorted(roles.items()):
        shown = [g for g in groups if g.withheld is None]
        evidence = (
            f"{sum(g.blocks or 0 for g in shown)} wait(s) addressed to {role} held up "
            f"{sum(g.runs_held_up or 0 for g in shown)} run(s) for "
            f"{sum(g.seconds or 0.0 for g in shown):g} s"
            if shown
            else f"the waits addressed to {role} are withheld: fewer than two persons answered"
        )
        found.append(
            Offer(
                way="deadline_with_deputy",
                where=role,
                evidence=evidence,
                how="a deadline on the waiting step with `at_limit: {escalate: <deputy role>}` "
                "hands the wait to a deputy when it falls due (ADR-0133)",
            )
        )
    for role, groups in sorted(roles.items()):
        busy = [g for g in groups if g.withheld is None and (g.blocks or 0) > 1]
        if not busy:
            continue
        found.append(
            Offer(
                way="batching",
                where=role,
                evidence=", ".join(f"{g.blocks} waits in {g.period}" for g in busy),
                how="the decider answers the requests that are not urgent together, at a time "
                "they choose; Taktus offers this and holds no request back on its own",
            )
        )
    for rule in rules:
        if rule.status not in ("proposed", "adopted"):
            continue
        state = (
            f"proposed to {rule.role} by request {rule.request_id}"
            if rule.status == "proposed"
            else f"adopted, answering for {rule.role}"
        )
        found.append(
            Offer(
                way="rule",
                where=rule.role,
                evidence=f"{rule.precedents} agreeing decisions of {rule.anchor} at "
                f"{rule.process}/{rule.step_id}: a rule is {state}",
                how="the rule takes effect only on a person's acceptance and is retired by the "
                "deciding role at any time; the kind is then asked again (ADR-0161)",
                decider=rule.role,
                withdrawable=True,
            )
        )
    return tuple(found)
