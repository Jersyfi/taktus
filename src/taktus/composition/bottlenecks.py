"""The ports of the bottleneck analysis, answered from the components that hold the facts
(ADR-0283, UC-9.5).

The accounting component analyses; the run component keeps the blocks and the step measures,
the decision component the rules from precedent, the identity component the departments.
Components never import each other, so the answers are joined here.

- `RunAccounts` hands accounting the ended blocks of the limit accounts and the steps held
  back, and the waits on a person only as the run groups them. A wait on a person is never
  handed over one by one (ADR-0283 §4).
- `MethodsOfTheRun` checks each held-up step for a change of method: a step on a language
  model whose cases meet the maturation candidacy may move to a trained model (ADR-0084).
- `RulesOfTheDecisions` hands over the rules from precedent with the role that decides them;
  who accepted or retired one stays with the decision component.
- `DirectoryDepartments` places the person who answered a wait in a department, for the run to
  count, as `DirectoryDeciders` does for decisions (ADR-0042).
"""

from __future__ import annotations

from collections.abc import Sequence

from taktus.components.accounting.ports import (
    Blocked,
    Grouping,
    MethodChecked,
    Period,
    RecurringRule,
    WaitGroup,
)
from taktus.components.decision.application.service.rules import PrecedentRules
from taktus.components.identity.application.service import IdentityDirectory
from taktus.components.run.application.query import BlockedTime
from taktus.components.run.application.query.measures import StepMeasures
from taktus.components.run.domain.model import Run
from taktus.components.run.domain.service import maturation
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Method

HANDED = frozenset({"limit.provider", "limit.quota", "limit.budget", "limit.compute"})
HELD_BACK = "wait.dependency"


class RunAccounts:
    """The accounting port `BlockAccounts`, over the run's blocked-time accounts."""

    def __init__(self, accounts: BlockedTime) -> None:
        self._accounts = accounts

    async def blocks(self, tenant: Tenant) -> Sequence[Blocked]:
        return [
            Blocked(
                account=b.account,
                cause=b.cause,
                run_id=b.run_id,
                step_id=b.step_id,
                process_version=b.process_version,
                since=b.since,
                until=b.until,
                seconds=b.seconds,
                on=b.on,
                short=b.short,
            )
            for b in await self._accounts.blocks(tenant)
            if b.account in HANDED or b.account == HELD_BACK
        ]

    async def waits(
        self, tenant: Tenant, grouping: Grouping, period: Period
    ) -> Sequence[WaitGroup]:
        return [
            WaitGroup.model_validate(group.document())
            for group in await self._accounts.grouped(tenant, grouping, period)
        ]


class MethodsOfTheRun:
    """The accounting port `MethodCheck`, over the run's step measures (ADR-0084)."""

    def __init__(self, measures: StepMeasures, runs: Repository[Run], work: UnitOfWork) -> None:
        self._measures = measures
        self._runs = runs
        self._work = work

    async def check(
        self, tenant: Tenant, steps: Sequence[tuple[str, str]]
    ) -> Sequence[MethodChecked]:
        if not steps:
            return []
        cases = {(s.process_version, s.step_id): s for s in await self._measures.steps(tenant)}
        async with self._work.transaction(tenant):
            runs = await self._runs.list(tenant)
        methods: dict[tuple[str, str], Method] = {}
        for run in runs:
            for step in run.steps:
                methods.setdefault((run.process_version, step.id), step.method)
        found: list[MethodChecked] = []
        for process_version, step_id in steps:
            held = cases.get((process_version, step_id))
            method = held.method if held is not None else methods.get((process_version, step_id))
            if method is None:
                found.append(
                    MethodChecked(
                        process_version=process_version,
                        step_id=step_id,
                        check="the step is in no run of the tenant: nothing to check",
                    )
                )
                continue
            candidacy = maturation.candidacy(method, () if held is None else held.cases)
            if candidacy.candidate:
                found.append(
                    MethodChecked(
                        process_version=process_version,
                        step_id=step_id,
                        method=str(method),
                        alternative=str(Method.ML),
                        check="maturation candidacy (ADR-0084): the cases a trained classifier "
                        "needs are recorded; `taktusctl maturation propose` trains it and "
                        "proposes the move on evidence of a lower cost per case",
                    )
                )
                continue
            found.append(
                MethodChecked(
                    process_version=process_version,
                    step_id=step_id,
                    method=str(method),
                    check="maturation candidacy (ADR-0084), no change of method: "
                    + "; ".join(candidacy.findings),
                )
            )
        return found


class RulesOfTheDecisions:
    """The accounting port `RecurringDecisions`, over the decision component's rules."""

    def __init__(self, rules: PrecedentRules) -> None:
        self._rules = rules

    async def rules(self, tenant: Tenant) -> Sequence[RecurringRule]:
        return [
            RecurringRule(
                rule_id=rule.id,
                process=rule.kind.process,
                step_id=rule.kind.step_id,
                anchor=rule.kind.anchor,
                role=rule.decider,
                status=rule.status.value,
                precedents=len(rule.precedents),
                request_id=rule.request_id,
            )
            for rule in await self._rules.all(tenant)
        ]


class DirectoryDepartments:
    """The run's port `Departments`, answered from the identity directory: the second element
    of an identity's place in the tenant's structure, as for a decider (ADR-0042)."""

    def __init__(self, directory: IdentityDirectory) -> None:
        self._directory = directory

    async def department(self, tenant: Tenant, identity: str) -> str | None:
        known = await self._directory.identity(tenant, identity)
        if known is None or len(known.org_path) < 2:
            return None
        return known.org_path[1]
