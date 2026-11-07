"""The bottleneck and waiting analysis (UC-9.5 §2 bullets 3 to 6; ADR-0015, ADR-0283).

Each case runs plans through the run engine over fakes of every port, makes runs block at a
limit or wait on a person, lets the blocks end, and reads the analysis back through the
accounting component's handler, its ports answered as the composition root answers them: what a
higher limit would have bought, the recommendations and their check for a change of method, the
waits on people by role and by department, and the ways to wait less on them.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest
from fakes.connector import WRITE
from governance.test_anchors import COLLEAGUE, DECIDER, OUTSIDER, call, requests_of
from governance.test_anchors import TENANT as GOVERNED
from governance.test_anchors import World as Governed

from taktus.adapters.driven.memory import MemoryRepository
from taktus.adapters.driving.cli.bottlenecks_command import render
from taktus.components.accounting.application.service import (
    BottleneckAnalysis,
    BottlenecksHandler,
    BottlenecksOf,
)
from taktus.components.accounting.domain.service.bottleneck import (
    MarginalValue,
    Offer,
    Quantity,
    Recommendation,
    marginal_values,
    recommend,
)
from taktus.components.accounting.ports import (
    Blocked,
    MethodChecked,
    RecurringRule,
    WaitGroup,
)
from taktus.components.decision.domain.model.rule import DecisionRule, Kind, RuleStatus
from taktus.components.run.application.query import BlockedTime
from taktus.components.run.application.query.measures import StepMeasures
from taktus.components.run.domain.service.admission import admit
from taktus.components.run.domain.service.blocked import GroupedWait
from taktus.composition.bottlenecks import (
    DirectoryDepartments,
    MethodsOfTheRun,
    RulesOfTheDecisions,
    RunAccounts,
)
from taktus.ports.persistence import Tenant
from taktus.ports.worker import ComputeLimit, Limits, QuotaLimit, TokenLimit
from taktus.shared.v1 import ConsumptionQuantities

from ..run.test_blocked_time import (
    ENOUGH,
    GAP,
    PERSON,
    TENANT,
    World,
    every_cause,
    read,
    worker,
)

AT = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)


def analysis_of(w: World, rules: RulesOfTheDecisions | None = None) -> BottlenecksHandler:
    """The handler as the composition root wires it, over the world's stores."""
    return BottlenecksHandler(
        RunAccounts(BlockedTime(w.ledger, w.objects, w.persistence, w.runs)),
        MethodsOfTheRun(
            StepMeasures(w.runs, w.ledger, w.objects, w.persistence), w.runs, w.persistence
        ),
        rules,
    )


def block(
    run: str,
    *,
    cause: str = "rejected_by_admission",
    account: str = "limit.budget",
    start: int = 0,
    end: int = 60,
    short: dict[str, float] | None = None,
    step: str = "build",
) -> Blocked:
    return Blocked(
        account=account,
        cause=cause,
        run_id=run,
        step_id=step,
        process_version="p@1",
        since=AT + timedelta(seconds=start),
        until=AT + timedelta(seconds=end),
        seconds=end - start,
        short=short,
    )


class Checks:
    """A `MethodCheck` that finds a change of method for the steps it is given."""

    def __init__(self, *removing: str) -> None:
        self.removing = removing
        self.asked: list[tuple[str, str]] = []

    async def check(
        self, tenant: Tenant, steps: Sequence[tuple[str, str]]
    ) -> Sequence[MethodChecked]:
        self.asked.extend(steps)
        return [
            MethodChecked(
                process_version=pv,
                step_id=step,
                method="llm",
                alternative="ml" if step in self.removing else None,
                check="candidate" if step in self.removing else "no candidate: 3 cases",
            )
            for pv, step in steps
        ]


# --- admission records what it refused, and by how much -----------------------------------------


def test_admission_says_by_how_much_each_quantity_did_not_fit() -> None:
    budget = Limits(
        currency={"usd": 1.0},
        quota=QuotaLimit(units=2),
        compute=ComputeLimit(seconds=10, resource_class="cpu.small"),
        tokens=TokenLimit.of(100, 50),
    )
    demand = ConsumptionQuantities.model_validate(
        {
            "currency": {"usd": 1.5},
            "quota_units": 3,
            "compute_seconds": 12,
            "resource_class": "cpu.small",
            "tokens_in": 130,
            "tokens_out": 40,
        }
    )
    verdict = admit(demand, budget, budget)
    assert not verdict.fits
    assert verdict.short == {
        "currency.usd": 0.5,
        "quota_units": 1,
        "compute_seconds": 2,
        "tokens_in": 30,
    }, "every quantity that did not fit, by what it lacked; what fitted is not named"
    assert admit(demand, budget.model_copy(update={"quota": None}), budget).short["quota_units"]


async def test_a_refusal_s_block_carries_its_shortfall_from_the_refusal_that_began_it() -> None:
    w = World()
    run = await w.start("quota", read("look"), budget=Limits(quota=QuotaLimit(units=0.5)))
    held = run.step_run("look").block
    assert held is not None and held.short == {"quota_units": 0.5}
    w.later()
    run = await w.resume(run)  # refused again, still short: one stretch, its first shortfall
    assert run.step_run("look").block == held
    w.later()
    await w.resume(run, budget=ENOUGH)
    (ended,) = await w.accounts.blocks(TENANT)
    assert (ended.cause, ended.short) == ("rejected_by_admission", {"quota_units": 0.5})
    assert ended.seconds >= 2 * GAP.total_seconds()


# --- the marginal value of a higher limit ------------------------------------------------------


async def test_the_marginal_value_says_what_would_have_started_when_and_how_much_higher() -> None:
    w = World()
    runs = await every_cause(w)
    found = await analysis_of(w).execute(BottlenecksOf(TENANT))
    by_account = {(v.account, v.process): v for v in found.marginal}
    assert set(by_account) == {
        ("limit.provider", "provider"),
        ("limit.quota", "quota"),
        ("limit.budget", "budget"),
        ("limit.compute", "compute"),
    }, "the four limits, and no wait on a person"
    blocks = {(b.account, b.process): b for b in await w.accounts.blocks(TENANT)}
    for key, value in by_account.items():
        held = blocks[key]
        assert value.steps == (f"{held.process_version}/{held.step_id}",)
        assert value.runs == 1 and value.blocks == 1
        assert value.seconds_earlier == held.seconds, "it would have started when refused"
        assert (value.since, value.until) == (held.since, held.until)

    quota = by_account[("limit.quota", "quota")]
    assert quota.raises == (Quantity(name="quota_units", amount=0.5, exact=True),)
    budget = by_account[("limit.budget", "budget")]
    (compute_seconds,) = budget.raises
    assert compute_seconds.name == "compute_seconds" and compute_seconds.exact
    assert compute_seconds.amount > 0 and not budget.estimate
    assert by_account[("limit.compute", "compute")].raises == (
        Quantity(name="places", amount=1, exact=True),
    )
    provider = by_account[("limit.provider", "provider")]
    assert provider.raises == () and provider.unmeasured, "a provider's limit is not guessed"
    assert "at_provider_limit" in provider.unmeasured[0]
    assert runs["quota"].id in {b.run_id for b in await w.accounts.blocks(TENANT)}


def test_money_is_marked_an_estimate_and_a_run_s_shortfalls_add_up() -> None:
    values = marginal_values(
        [
            block("run_1", short={"currency.usd": 0.5, "tokens_in": 10}),
            block("run_1", start=100, end=160, short={"currency.usd": 0.25}),
            block("run_2", short={"tokens_in": 30}),
        ]
    )
    (value,) = values
    assert value.raises == (
        Quantity(name="currency.usd", amount=0.75, exact=False),
        Quantity(name="tokens_in", amount=30, exact=True),
    ), "one run's steps add up against its budget; the largest run's sum is the raise"
    assert value.estimate, "money is reported per assignment: an estimate"
    assert value.runs == 2 and value.blocks == 3 and value.seconds_earlier == 180


def test_places_are_the_most_steps_waiting_at_capacity_at_one_moment() -> None:
    (value,) = marginal_values(
        [
            block("run_1", cause="at_capacity", account="limit.compute", start=0, end=60),
            block("run_2", cause="at_capacity", account="limit.compute", start=30, end=90),
            block("run_3", cause="rejected_by_capacity", account="limit.compute", start=60, end=70),
        ]
    )
    assert value.raises == (Quantity(name="places", amount=2, exact=True),)


def test_a_refusal_recorded_without_its_shortfall_is_named_and_not_guessed() -> None:
    (value,) = marginal_values(
        [block("run_1"), block("run_2", cause="at_tenant_budget", short=None)]
    )
    assert value.raises == ()
    assert len(value.unmeasured) == 2
    assert all(":" in why for why in value.unmeasured)


# --- a recommendation checks a change of method first -------------------------------------------


def test_a_raise_is_recommended_only_after_every_check_found_no_change_of_method() -> None:
    blocks = [
        block("run_1", step="draft", short={"tokens_in": 100}),
        block("run_2", step="review", short={"tokens_in": 50}),
    ]
    (value,) = marginal_values(blocks)
    none_found = {
        ("p@1", s): MethodChecked(
            process_version="p@1", step_id=s, method="llm", check=f"no candidate for {s}"
        )
        for s in ("draft", "review")
    }
    raised = recommend(value, none_found)
    assert raised.action == "raise_limit"
    assert raised.cost == (Quantity(name="tokens_in", amount=100, exact=True),)
    assert raised.effect_seconds == 120 and "2 step(s) of 2 run(s)" in raised.effect
    assert raised.value == {"tokens_in": 1.2}, "seconds sooner per token raised"
    assert raised.checks == (
        "p@1/draft: no candidate for draft",
        "p@1/review: no candidate for review",
    ), "the check is named in the recommendation"

    one_moves = {
        **none_found,
        ("p@1", "draft"): MethodChecked(
            process_version="p@1", step_id="draft", method="llm", alternative="ml", check="ok"
        ),
    }
    moved = recommend(value, one_moves)
    assert moved.action == "change_method" and moved.cost == ()
    assert moved.alternatives == ("p@1/draft: ml",)
    assert "no raise" in moved.cost_text and moved.checks

    unchecked = recommend(value, {})
    assert unchecked.action == "raise_limit" and all("not checked" in c for c in unchecked.checks)


async def test_every_recommendation_names_effect_cost_value_and_the_check_of_its_steps() -> None:
    w = World()
    await every_cause(w)
    checks = Checks("draft")
    handler = BottlenecksHandler(
        RunAccounts(BlockedTime(w.ledger, w.objects, w.persistence, w.runs)), checks
    )
    found = await handler.execute(BottlenecksOf(TENANT))
    assert len(found.recommendations) == len(found.marginal)
    assert sorted(checks.asked) == sorted(
        {(s.rsplit("/", 1)[0], s.rsplit("/", 1)[1]) for v in found.marginal for s in v.steps}
    ), "every step held up at a limit is checked"
    for advice in found.recommendations:
        assert advice.effect and advice.cost_text and advice.value_text and advice.checks
    actions = {(r.account, r.action) for r in found.recommendations}
    assert ("limit.provider", "change_method") in actions, "the llm step may move first"
    assert ("limit.quota", "raise_limit") in actions

    # The instance's own check, over the run's measures: a rule or a worker is no candidate.
    instance = await analysis_of(w).execute(BottlenecksOf(TENANT))
    for advice in instance.recommendations:
        assert all("maturation candidacy (ADR-0084)" in c for c in advice.checks), advice
        assert advice.action != "change_method", "too few cases for any step to move"


# --- waits on people, by role and by department, never by person --------------------------------


async def decided_by(*deciders: str) -> Governed:
    """One run whose anchored writes each wait for a decision, one per decider."""
    names = [f"write-{n}" for n in range(len(deciders))]
    w = await Governed(*(call(name, WRITE) for name in names)).setup()
    run = await w.start()
    for name, decider in zip(names, deciders, strict=True):
        w.clock.current += timedelta(minutes=5)
        (request_id,) = requests_of(run, name)
        await w.answer(request_id, option="A", by=decider)
        await w.confirm(request_id, by=decider)
    return w


def governed_accounts(w: Governed) -> RunAccounts:
    return RunAccounts(
        BlockedTime(
            w.ledger,
            w.engine._objects,
            w.persistence,
            w.runs,
            DirectoryDepartments(w.people.directory),
        )
    )


async def test_waits_on_people_are_summed_by_role_and_by_department_over_two_persons() -> None:
    w = await decided_by(DECIDER, COLLEAGUE)
    accounts = governed_accounts(w)
    (role,) = await accounts.waits(GOVERNED, "role", "month")
    assert (role.grouping, role.group, role.blocks, role.runs_held_up) == (
        "role",
        "finance.lead",
        2,
        1,
    )
    assert role.seconds is not None and role.seconds >= 5 * 60
    (department,) = await accounts.waits(GOVERNED, "department", "month")
    assert (department.group, department.blocks) == ("finance", 2)
    text = json.dumps([role.document(), department.document()])
    assert DECIDER not in text and COLLEAGUE not in text


async def test_a_role_or_department_one_person_answered_is_withheld_count_and_all() -> None:
    w = await decided_by(DECIDER, DECIDER)
    accounts = governed_accounts(w)
    for grouping in ("role", "department"):
        (group,) = await accounts.waits(GOVERNED, grouping, "month")
        assert group.withheld and "fewer than 2 persons" in group.withheld
        assert (group.seconds, group.blocks, group.runs_held_up) == (None, None, None)
    # The decider reads their own waits; nobody else reads them under the name.
    blocked = BlockedTime(w.ledger, w.engine._objects, w.persistence)
    assert len(await blocked.own(GOVERNED, DECIDER)) == 2
    assert await blocked.own(GOVERNED, OUTSIDER) == ()


async def test_no_value_of_the_analysis_can_hold_a_person_and_none_is_ranked() -> None:
    personal = {"actor", "person", "identity", "by", "who", "decided_by", "answered_by"}
    for kind in (
        Blocked,
        WaitGroup,
        GroupedWait,
        MethodChecked,
        RecurringRule,
        MarginalValue,
        Recommendation,
        Offer,
        BottleneckAnalysis,
    ):
        assert not set(kind.model_fields) & personal, kind.__name__
    w = await decided_by(DECIDER, COLLEAGUE)
    accounts = governed_accounts(w)
    assert all(b.account != "wait.human" for b in await accounts.blocks(GOVERNED)), (
        "a wait on a person is never handed over one by one"
    )
    found = await BottlenecksHandler(accounts, Checks()).execute(
        BottlenecksOf(GOVERNED, "department", "day")
    )
    text = json.dumps(found.document(), default=str)
    assert DECIDER not in text and COLLEAGUE not in text
    keys = [(g.grouping, g.group, g.period) for g in found.waits]
    assert keys == sorted(keys), "ordered by key, never by a figure"


# --- the four ways to wait less on people ---------------------------------------------------------


async def test_each_of_the_four_ways_to_wait_less_on_people_is_offered_where_it_applies() -> None:
    w = await decided_by(DECIDER, COLLEAGUE)
    rules = MemoryRepository(w.persistence, DecisionRule)
    adopted = DecisionRule(
        id="rul_1",
        tenant=GOVERNED,
        kind=Kind(process="p", step_id="write-0", anchor="payments"),
        option="A",
        proposal="pay",
        decider="finance.lead",
        precedents=("reg_1", "reg_2", "reg_3", "reg_4", "reg_5"),
        request_id="req_9",
        status=RuleStatus.ADOPTED,
        created_at=AT,
        decided_by=DECIDER,
        decided_at=AT,
    )
    async with w.persistence.transaction(GOVERNED):
        await rules.put(GOVERNED, adopted)
    precedent = w.decisions.rules
    precedent._rules = rules
    found = await BottlenecksHandler(
        governed_accounts(w), Checks(), RulesOfTheDecisions(precedent)
    ).execute(BottlenecksOf(GOVERNED))
    ways = {o.way: o for o in found.offers}
    assert set(ways) == {"deadline_with_deputy", "batching", "rule"}
    assert "escalate" in ways["deadline_with_deputy"].how
    assert ways["deadline_with_deputy"].where == "finance.lead"
    assert "2 waits" in ways["batching"].evidence
    rule = ways["rule"]
    assert (rule.decider, rule.withdrawable) == ("finance.lead", True), (
        "the decider's, withdrawable"
    )
    assert "retired by the deciding role" in rule.how
    assert DECIDER not in json.dumps(found.document(), default=str), "who adopted it stays out"

    # Steps held back behind a person's wait: carry on with the work that does not need it.
    world = World()
    await every_cause(world)
    held = await analysis_of(world).execute(BottlenecksOf(TENANT))
    (carry_on,) = [o for o in held.offers if o.way == "carry_on"]
    assert carry_on.where == "human" and "held back" in carry_on.evidence
    assert "ADR-0039" in carry_on.how
    assert PERSON not in json.dumps(held.document(), default=str)


# --- the command line ---------------------------------------------------------------------------


async def test_the_command_line_prints_limits_advice_waits_and_offers() -> None:
    w = World()
    await every_cause(w)
    found = await analysis_of(w).execute(BottlenecksOf(TENANT))
    text = render(found)
    assert "limit    limit.quota in quota" in text
    assert "raise  quota_units by 0.5 (exact)" in text
    assert "check  " in text and "advice raise_limit" in text
    assert "offer    carry_on for human" in text
    assert "waits    role unaddressed" in text and "withheld" in text


@pytest.mark.parametrize("budget", [ENOUGH])
async def test_a_run_that_was_never_held_has_no_bottleneck(budget: Limits) -> None:
    w = World()
    await w.start("clear", worker("build"), budget=budget)
    found = await analysis_of(w).execute(BottlenecksOf(TENANT))
    assert found.marginal == () and found.recommendations == () and found.offers == ()
