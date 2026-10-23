"""Use cases of a deadline (ADR-0133, UC-4.17): start and meet one as the run's ledger says,
take each action once, list the open ones, and set the tenant's working time.

`observe` runs inside the run engine's own transaction, for every entry the engine records: the
deadline starts and is met in the same transaction as the entry that says so. `due` and `take`
are the elected scheduler's: an action is taken in one transaction with its ledger entry, and
the record is read again under the tenant's ledger lock, so that a second scheduler that took
the same action meanwhile rolls this one back (issue #317).

What an action of kind `start` starts is not this component's: the scheduler's tick starts the
process through the one path every channel takes (`composition/deadlines.py`), and hands the run
it started to `take`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time

from taktus.components.run.domain.model import Run
from taktus.components.run.domain.model.deadline import (
    Deadline,
    DeadlineRule,
    DeadlineState,
    WorkingTime,
    deadline_id,
    shipped_working_time,
)
from taktus.components.run.domain.service import deadlines as rules
from taktus.components.run.ports.deadlines import DeclaredDeadlines
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs


@dataclass(frozen=True)
class ConfigureWorkingTime:
    """What a tenant sets of its working time; what it leaves out stays. Who sets it is the
    actor of the ledger entry, never a field beside these values."""

    tenant: Tenant
    zone: str | None = None
    days: tuple[int, ...] | None = None
    begins: time | None = None
    ends: time | None = None
    holidays: tuple[date, ...] | None = None


@dataclass(frozen=True)
class Taken:
    """What taking one action did."""

    deadline: Deadline
    kind: str
    """`deadline.lead` or `deadline.reached`."""
    outcome: str
    """The action's kind, or `refused` for a start the engine refused."""


class _AlreadyTaken(Exception):
    """Another scheduler took the action while this one took it."""


@dataclass
class _Cache:
    versions: dict[str, tuple[DeadlineRule, ...]] = field(default_factory=dict)


class DeadlineKeeper:
    def __init__(
        self,
        deadlines: Repository[Deadline],
        working_times: Repository[WorkingTime],
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
        declared: DeclaredDeadlines | None = None,
    ) -> None:
        self._deadlines = deadlines
        self._working = working_times
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._declared = declared
        self._cache = _Cache()

    # --- the run engine's side ---------------------------------------------------------------

    async def declared(self, tenant: Tenant, process_version: str) -> tuple[DeadlineRule, ...]:
        """The deadlines a version declares, for a run created from it. Outside a transaction:
        the port opens its own. A version never changes, so what was read once is kept."""
        if self._declared is None:
            return ()
        found = self._cache.versions.get(process_version)
        if found is None:
            found = await self._declared.deadlines(tenant, process_version)
            self._cache.versions[process_version] = found
        return found

    async def observe(self, run: Run, kind: str, step_id: str | None, outcome: str | None) -> None:
        """Inside the engine's transaction: start and meet the run's deadlines as the entry
        just recorded says (ADR-0133 §2). A rehearsal starts none."""
        if not run.deadlines or run.rehearsal:
            return
        now = self._clock.now()
        for rule in run.deadlines:
            did = deadline_id(run.id, rule.name)
            if rules.starts(rule, kind, step_id, outcome):
                await self._start(run, rule, did, now)
            through = rules.meets(rule, kind, step_id, outcome)
            if through is not None:
                await self._meet(run, did, through, now)

    async def _start(self, run: Run, rule: DeadlineRule, did: str, now: datetime) -> None:
        if await self._deadlines.get(run.tenant, did) is not None:
            return  # started already: the same moment recorded again opens nothing
        started_at = rules.starting_moment(rule, run.inputs, now)
        if started_at is None:
            await self._record(run.tenant, rules.REFUSED, run, did, "no_date")
            return
        working = await self._working.get(run.tenant, run.tenant) or shipped_working_time(
            run.tenant
        )
        when = rules.schedule(rule, started_at, working)
        deadline = Deadline(
            id=did,
            tenant=run.tenant,
            run_id=run.id,
            process_version=run.process_version,
            rule=rule,
            started_at=started_at,
            due_at=when.due_at,
            lead_at=when.lead_at,
            created_at=now,
        )
        await self._deadlines.put(run.tenant, deadline)
        await self._record(
            run.tenant, rules.STARTED, run, did, "working" if rule.working else "calendar"
        )

    async def _meet(self, run: Run, did: str, through: str, now: datetime) -> None:
        deadline = await self._deadlines.get(run.tenant, did)
        if deadline is None or deadline.state is not DeadlineState.OPEN:
            return
        await self._deadlines.put(run.tenant, rules.met(deadline, through, now))
        await self._record(run.tenant, rules.MET, run, did, through)

    # --- the scheduler's side ----------------------------------------------------------------

    async def due(self, tenant: Tenant) -> list[rules.Due]:
        """Every action due now on the tenant's deadlines, the earliest first."""
        now = self._clock.now()
        async with self._work.transaction(tenant):
            found = list(await self._deadlines.list(tenant))
        actions = [d for deadline in found for d in rules.due(deadline, now)]
        actions.sort(key=lambda d: (d.at, d.deadline.id, d.moment))
        return actions

    async def take(
        self,
        tenant: Tenant,
        due: rules.Due,
        *,
        started_run: str | None = None,
        refused: str | None = None,
    ) -> Taken | None:
        """Take the action once: its entry and the record's note in one transaction. None when
        it was taken already, by this scheduler or another (ADR-0133 §3)."""
        now = self._clock.now()
        outcome = "refused" if refused is not None else due.action.kind.value
        try:
            async with self._work.transaction(tenant):
                # The entry first: writing it takes the tenant's ledger lock, and the record is
                # read again under it.
                await self._ledger.record(
                    tenant,
                    Fact(
                        kind=due.kind,
                        refs=LedgerRefs(
                            tenant=tenant,
                            process_version=due.deadline.process_version,
                            run_id=due.deadline.run_id,
                            deadline_id=due.deadline.id,
                        ),
                        outcome=outcome,
                    ),
                )
                current = await self._deadlines.get(tenant, due.deadline.id)
                if current is None or not any(
                    d.moment == due.moment for d in rules.due(current, now)
                ):
                    raise _AlreadyTaken
                updated = rules.taken(current, due.moment, now)
                if started_run is not None or refused is not None:
                    updated = updated.model_copy(
                        update={"started_run": started_run, "refused": refused}
                    )
                await self._deadlines.put(tenant, updated)
        except _AlreadyTaken:
            return None
        return Taken(deadline=updated, kind=due.kind, outcome=outcome)

    # --- the reader's side -------------------------------------------------------------------

    async def open(self, tenant: Tenant, *, role: str | None = None) -> list[Deadline]:
        """The tenant's open deadlines, ordered by when they fall due; with `role`, those whose
        reminder or escalation went to it."""
        async with self._work.transaction(tenant):
            found = list(await self._deadlines.list(tenant))
        listed = [
            d
            for d in found
            if d.state is DeadlineState.OPEN and (role is None or role in d.roles())
        ]
        listed.sort(key=lambda d: (d.due_at, d.id))
        return listed

    async def listing(self, tenant: Tenant, *, role: str | None = None) -> list[dict[str, object]]:
        now = self._clock.now()
        return [rules.document(d, now) for d in await self.open(tenant, role=role)]

    async def working_time(self, tenant: Tenant) -> WorkingTime:
        """The tenant's working time, or the shipped default where it configured none."""
        async with self._work.transaction(tenant):
            found = await self._working.get(tenant, tenant)
        return found or shipped_working_time(tenant)

    async def configure(self, command: ConfigureWorkingTime, *, by: str) -> WorkingTime:
        """Set what the command names, keep the rest. A working time that does not hold is
        refused as a ValueError and changes nothing. It counts for deadlines started after."""
        current = await self.working_time(command.tenant)
        changes = {
            name: value
            for name, value in (
                ("zone", command.zone),
                ("days", command.days),
                ("begins", command.begins),
                ("ends", command.ends),
                ("holidays", command.holidays),
            )
            if value is not None
        }
        configured = WorkingTime.model_validate(
            {**current.model_dump(), **changes, "configured_at": self._clock.now()}
        )
        async with self._work.transaction(command.tenant):
            await self._working.put(command.tenant, configured)
            await self._ledger.record(
                command.tenant,
                Fact(
                    kind="working_time.configured",
                    refs=LedgerRefs(tenant=command.tenant, actor=by),
                    outcome="configured",
                ),
            )
        return configured

    async def _record(self, tenant: Tenant, kind: str, run: Run, did: str, outcome: str) -> None:
        await self._ledger.record(
            tenant,
            Fact(
                kind=kind,
                refs=LedgerRefs(
                    tenant=tenant,
                    process_version=run.process_version,
                    run_id=run.id,
                    deadline_id=did,
                ),
                outcome=outcome,
            ),
        )
