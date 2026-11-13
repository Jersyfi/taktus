"""A chain of processes stored, started, run link by link and shown, every handover recorded
(UC-15.4, ADR-0274, ADR-0301, ADR-0302).

`ChainRuns.declare` holds a chain to the versions it links (`process/domain/service/chains.py`)
and stores it as the tenant's `DeclaredChain`. `start` runs a declared chain; `run` runs one
handed in. Either keeps a `ChainRun`: the chain it started with, the link it stands at, the run
of every link and the digest of every handover.

The first link starts with the chain's inputs. After each link that finished, the handover is
built from its recorded results — read from the object store by each step run's checkpoint. A
handover that lacks a declared item does not happen: `chain.halted` names the boundary, the
chain run is `halted`, and the situation package goes to the role the chain names
(`chain.escalated`). A person then gives the missing items or stops the chain (`decide`).
Otherwise `chain.handover` records the handover's document by digest — every item with its
value's digest, its step and its clause — and the next link starts with exactly those inputs.

A link that did not finish — one waiting at an anchor, for a person, or escalated — leaves the
chain `waiting` at that link; the links before it keep their results. `advance`, which the
scheduler calls, goes on with every waiting chain whose link has since finished: the chain
resumes at that boundary once the person decided. A chain that ended is measured once against
its own objectives (`chain.measured`).

This is wiring, because the chain is the process component's, its links are runs of the run
component, its package the governance component's and the channel the reporting component's.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import structlog

from taktus.components.governance.domain.model.defects import SituationPackage
from taktus.components.governance.domain.model.escalation import HandoverHalted, Lacking
from taktus.components.governance.domain.service import escalations as escalation_rule
from taktus.components.governance.domain.service import objectives as objective_rule
from taktus.components.process.domain.model import InvalidProcess, ProcessVersion
from taktus.components.process.domain.model.chain import (
    Chain,
    ChainRefused,
    ChainRun,
    ChainState,
    DeclaredChain,
)
from taktus.components.process.domain.service import chains
from taktus.components.process.domain.service.chains import Handed
from taktus.components.reporting.application.service import (
    ChannelOf,
    NoChannel,
    NotSent,
    RaiseReport,
    RaiseReportHandler,
)
from taktus.components.reporting.domain.model import ReportKind
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState
from taktus.composition.tenancy import this_round
from taktus.ports.clock import Clock
from taktus.ports.identity import ServedTenants
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Repository, Stored, Tenant, UnitOfWork
from taktus.ports.worker import Limits
from taktus.shared.v1 import Commissioned, LedgerRefs, Plan, PlanResult, PlanStatus

DECLARED = "chain.declared"
HANDOVER = "chain.handover"
HALTED = "chain.halted"
ESCALATED = "chain.escalated"
STOPPED = "chain.stopped"
MEASURED = "chain.measured"
OWNER = "owner"
"""The role a halted handover reaches where the chain names none."""
COMPLETION_WINDOW = 20
"""How many of a chain's latest ended runs its completion share is taken over."""
_LINK_PLAN = re.compile(r"^pln_([a-z][a-z0-9-]*)_[1-9][0-9]*$")

log = structlog.get_logger("taktusd")


def link_plan(chain: str, index: int) -> str:
    """The identifier of the plan of the chain's link at `index`, counted from zero."""
    return f"pln_{chain}_{index + 1}"


def chain_of(plan_id: str) -> str | None:
    """The chain whose link the plan is, read back from `link_plan`; None for any other plan.
    What sums the value balance per chain reads a chain's processes by it (ADR-0288)."""
    found = _LINK_PLAN.match(plan_id)
    return None if found is None else found.group(1)


def report_id(chain_run: str, boundary: int) -> str:
    """The report of a chain run's halt at the boundary before link `boundary`."""
    return f"chain-{chain_run}-{boundary}"


@dataclass(frozen=True)
class ChainOutcome:
    runs: tuple[Run, ...]
    """The run of every link that started in this call, in order."""
    handovers: tuple[dict[str, Any], ...] = field(default=())
    """The document of every handover recorded in this call."""
    halted: str | None = None
    """Why the chain stopped before its last link ended; None where every link finished."""
    chain_run: ChainRun | None = None
    """The chain run as it stands after the call."""
    package: SituationPackage | None = None
    """The situation package of a handover that halted the chain."""


class ChainRuns:
    def __init__(
        self,
        *,
        engine: RunEngine,
        versions: Repository[ProcessVersion],
        objects: ObjectStore,
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
        runs: Repository[Run] | None = None,
        declared: Repository[DeclaredChain] | None = None,
        chain_runs: Repository[ChainRun] | None = None,
        channels: ChannelOf | None = None,
        raising: RaiseReportHandler | None = None,
    ) -> None:
        """Without `declared` and `chain_runs`, nothing is stored: a chain is handed to `run`.
        Without `channels` and `raising`, a halted handover's package is recorded only."""
        self._engine = engine
        self._versions = versions
        self._objects = objects
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._runs = runs
        self._declared = declared
        self._chain_runs = chain_runs
        self._channels = channels
        self._raising = raising

    # --- the declaration ------------------------------------------------------------------

    async def declare(self, tenant: Tenant, chain: Chain) -> DeclaredChain:
        """The chain held to the versions it links and stored; `InvalidProcess` where it is
        refused. A new declaration replaces the one before; a run keeps its own."""
        await self._held(tenant, chain)
        declared = DeclaredChain(id=chain.id, chain=chain, declared_at=self._clock.now())
        digest = await self._objects.put(_canonical(chain.model_dump(mode="json")))
        async with self._work.transaction(tenant):
            await self._stored(self._declared).put(tenant, declared)
            await self._ledger.record(
                tenant,
                Fact(
                    kind=DECLARED,
                    refs=LedgerRefs(tenant=tenant, plan_id=link_plan(chain.id, 0)),
                    outcome="declared",
                    content_digest=digest,
                ),
            )
        return declared

    async def chains(self, tenant: Tenant) -> list[DeclaredChain]:
        async with self._work.transaction(tenant):
            return list(await self._stored(self._declared).list(tenant))

    async def chain(self, tenant: Tenant, chain_id: str) -> DeclaredChain | None:
        async with self._work.transaction(tenant):
            return await self._stored(self._declared).get(tenant, chain_id)

    async def runs_of(self, tenant: Tenant, chain_id: str | None = None) -> list[ChainRun]:
        """The chain runs of the tenant, or of one chain, newest first."""
        async with self._work.transaction(tenant):
            found = await self._stored(self._chain_runs).list(tenant)
        mine = [r for r in found if chain_id is None or r.chain.id == chain_id]
        return sorted(mine, key=lambda r: (r.started_at, r.id), reverse=True)

    async def chain_run(self, tenant: Tenant, chain_run_id: str) -> ChainRun | None:
        async with self._work.transaction(tenant):
            return await self._stored(self._chain_runs).get(tenant, chain_run_id)

    # --- running --------------------------------------------------------------------------

    async def start(
        self, tenant: Tenant, chain_id: str, inputs: Mapping[str, Any], actor: str
    ) -> ChainOutcome:
        """A declared chain started with its inputs; `LookupError` where none is declared."""
        declared = await self.chain(tenant, chain_id)
        if declared is None:
            raise LookupError(f"the tenant declared no chain {chain_id!r}")
        return await self.run(tenant, declared.chain, inputs, actor)

    async def run(
        self, tenant: Tenant, chain: Chain, inputs: Mapping[str, Any], actor: str
    ) -> ChainOutcome:
        linked = await self._held(tenant, chain)
        now = self._clock.now()
        chain_run = ChainRun(
            id=await self._new_id(tenant, chain.id),
            chain=chain,
            state=ChainState.RUNNING,
            started_at=now,
            updated_at=now,
        )
        await self._keep(tenant, chain_run)
        return await self._go(tenant, chain_run, linked, inputs, actor)

    async def advance(self, tenant: Tenant, actor: str = "taktus") -> tuple[str, ...]:
        """Every waiting chain whose link has since finished goes on at its boundary; one whose
        link can no longer finish is stopped. The chain runs that moved, by identifier."""
        if self._chain_runs is None or self._runs is None:
            return ()
        moved: list[str] = []
        for chain_run in await self.runs_of(tenant):
            if chain_run.state is not ChainState.WAITING or not chain_run.runs:
                continue
            async with self._work.transaction(tenant):
                run = await self._runs.get(tenant, chain_run.runs[-1])
            if run is None or run.state is not RunState.FINISHED:
                continue
            linked = await self._held(tenant, chain_run.chain)
            await self._after(tenant, chain_run, linked, run, actor)
            moved.append(chain_run.id)
        return tuple(moved)

    async def decide(
        self,
        tenant: Tenant,
        chain_run_id: str,
        actor: str,
        *,
        given: Mapping[str, Any] | None = None,
        stop: bool = False,
    ) -> ChainOutcome:
        """A person's decision on a halted chain (ADR-0302 §3): `given` holds a value for every
        item the handover lacked, and the chain goes on with them; `stop` ends it. A waiting
        chain may be stopped too. `ChainRefused` where the decision does not fit its state."""
        chain_run = await self.chain_run(tenant, chain_run_id)
        if chain_run is None:
            raise LookupError(f"no chain run {chain_run_id!r}")
        if stop:
            if chain_run.ended:
                raise ChainRefused(f"the chain run {chain_run_id} has ended already")
            ended = await self._end(tenant, chain_run, ChainState.STOPPED, "stopped by a person")
            return ChainOutcome((), chain_run=ended)
        if chain_run.state is not ChainState.HALTED:
            raise ChainRefused(
                f"the chain run {chain_run_id} is {chain_run.state}: only a halted handover is "
                "given by a person"
            )
        lacking = set(chain_run.missing)
        offered = dict(given or {})
        if set(offered) != lacking:
            raise ChainRefused(
                "a person gives exactly the items the handover lacked: "
                + ", ".join(sorted(lacking))
            )
        linked = await self._held(tenant, chain_run.chain)
        async with self._work.transaction(tenant):
            sending = await self._stored(self._runs).get(tenant, chain_run.runs[-1])
        if sending is None:
            raise LookupError(f"the run {chain_run.runs[-1]} of the chain is not found")
        return await self._after(tenant, chain_run, linked, sending, actor, given=offered)

    async def started(
        self, tenant: Tenant, chain_id: str, inputs: Mapping[str, Any], actor: str
    ) -> ChainRun:
        """`start`, answered with the chain run as it stands: what the HTTP surface shows."""
        outcome = await self.start(tenant, chain_id, inputs, actor)
        return _kept(outcome)

    async def decided(
        self,
        tenant: Tenant,
        chain_run_id: str,
        actor: str,
        *,
        given: Mapping[str, Any] | None = None,
        stop: bool = False,
    ) -> ChainRun:
        """`decide`, answered with the chain run as it stands."""
        outcome = await self.decide(tenant, chain_run_id, actor, given=given, stop=stop)
        return _kept(outcome)

    # --- the loop -------------------------------------------------------------------------

    async def _go(
        self,
        tenant: Tenant,
        chain_run: ChainRun,
        linked: Sequence[ProcessVersion],
        inputs: Mapping[str, Any],
        actor: str,
    ) -> ChainOutcome:
        """From the link the chain run stands at, with its inputs, until a link does not finish,
        a handover halts, or the last link ended."""
        chain = chain_run.chain
        runs: list[Run] = []
        handed: list[dict[str, Any]] = []
        given: Mapping[str, Any] = inputs
        index = chain_run.link
        while True:
            link = chain.links[index]
            run = await self._start(tenant, chain, index, linked[index], given, actor)
            runs.append(run)
            chain_run = await self._keep(
                tenant,
                chain_run.model_copy(
                    update={
                        "link": index,
                        "runs": (*chain_run.runs, run.id),
                        "state": ChainState.RUNNING,
                        "reason": None,
                        "missing": (),
                        "updated_at": self._clock.now(),
                    }
                ),
            )
            if run.state is not RunState.FINISHED:
                why = (
                    f"link {index + 1}, {link.process_version}, is {run.state}: the chain waits "
                    "at its boundary"
                )
                chain_run = await self._keep(
                    tenant,
                    chain_run.model_copy(update={"state": ChainState.WAITING, "reason": why}),
                )
                return ChainOutcome(tuple(runs), tuple(handed), why, chain_run)
            if index + 1 == len(chain.links):
                chain_run = await self._end(tenant, chain_run, ChainState.FINISHED, None)
                return ChainOutcome(tuple(runs), tuple(handed), None, chain_run)
            step = await self._handover(tenant, chain_run, linked, run, None)
            if isinstance(step, ChainOutcome):
                return ChainOutcome(
                    (*runs, *step.runs),
                    (*handed, *step.handovers),
                    step.halted,
                    step.chain_run,
                    step.package,
                )
            document, given, chain_run = step
            handed.append(document)
            index += 1

    async def _after(
        self,
        tenant: Tenant,
        chain_run: ChainRun,
        linked: Sequence[ProcessVersion],
        sending: Run,
        actor: str,
        *,
        given: Mapping[str, Any] | None = None,
    ) -> ChainOutcome:
        """The chain goes on after its link `sending` finished: the handover, then the next
        link; or the end, where it was the last."""
        if chain_run.link + 1 == len(chain_run.chain.links):
            ended = await self._end(tenant, chain_run, ChainState.FINISHED, None)
            return ChainOutcome((), chain_run=ended)
        step = await self._handover(tenant, chain_run, linked, sending, given)
        if isinstance(step, ChainOutcome):
            return step
        document, inputs, chain_run = step
        moved = chain_run.model_copy(update={"link": chain_run.link + 1})
        outcome = await self._go(tenant, moved, linked, inputs, actor)
        return ChainOutcome(
            outcome.runs,
            (document, *outcome.handovers),
            outcome.halted,
            outcome.chain_run,
            outcome.package,
        )

    async def _handover(
        self,
        tenant: Tenant,
        chain_run: ChainRun,
        linked: Sequence[ProcessVersion],
        run: Run,
        by_person: Mapping[str, Any] | None,
    ) -> tuple[dict[str, Any], Mapping[str, Any], ChainRun] | ChainOutcome:
        chain = chain_run.chain
        index = chain_run.link
        following = chain.links[index + 1]
        results = await self._results(run)
        passing = chains.handover(following.handover, results)
        given: dict[str, Any]
        if passing.missing and by_person is None:
            return await self._halt(tenant, chain_run, linked, run, passing)
        if by_person is not None:
            held = chains.handover(
                [i for i in following.handover if i.input not in by_person], results
            )
            given = {**held.given, **by_person}
        else:
            given = dict(passing.given)
        person = set(by_person or {})
        document = {
            "chain": chain.id,
            "chain_run": chain_run.id,
            "from": run.id,
            "to": following.process_version,
            "items": [
                {
                    "input": item.input,
                    "step": item.step,
                    "select": item.select,
                    "clause": item.clause,
                    "digest": _digest(given[item.input]),
                    **({"given_by": "a person"} if item.input in person else {}),
                }
                for item in following.handover
            ],
        }
        digest = await self._objects.put(_canonical(document))
        await self._record(
            tenant,
            HANDOVER,
            chain,
            index,
            run,
            "given_by_a_person" if person else "handed_over",
            digest,
        )
        chain_run = await self._keep(
            tenant,
            chain_run.model_copy(
                update={
                    "handovers": (*chain_run.handovers, digest),
                    "updated_at": self._clock.now(),
                }
            ),
        )
        return document, given, chain_run

    async def _halt(
        self,
        tenant: Tenant,
        chain_run: ChainRun,
        linked: Sequence[ProcessVersion],
        run: Run,
        passing: Handed,
    ) -> ChainOutcome:
        chain = chain_run.chain
        index = chain_run.link
        following = chain.links[index + 1]
        names = ", ".join(f"{i.input} ({i.clause})" for i in passing.missing)
        why = (
            f"the handover to {following.process_version} lacks {names}: nothing was handed "
            "over, and the chain goes to a person (UC-4.5)"
        )
        halted = HandoverHalted(
            chain=chain.id,
            chain_run=chain_run.id,
            sending=chain.links[index].process_version,
            sending_run=run.id,
            receiving=following.process_version,
            lacking=tuple(
                Lacking(input=i.input, step=i.step, clause=i.clause) for i in passing.missing
            ),
            handed=tuple(i.input for i in following.handover if i not in passing.missing),
            finished=tuple(link.process_version for link in chain.links[: index + 1]),
            left=await self._left(tenant, chain_run),
            after=tuple(link.process_version for link in chain.links[index + 2 :]),
        )
        package = escalation_rule.handover_package(halted)
        digest = await self._objects.put(_canonical(package.model_dump(mode="json")))
        await self._record(tenant, HALTED, chain, index, run, "missing", digest)
        chain_run = await self._keep(
            tenant,
            chain_run.model_copy(
                update={
                    "state": ChainState.HALTED,
                    "reason": why,
                    "missing": tuple(i.input for i in passing.missing),
                    "updated_at": self._clock.now(),
                }
            ),
        )
        path = await self._escalate(tenant, chain, chain_run, index + 1, package)
        await self._record(
            tenant,
            ESCALATED,
            chain,
            index,
            run,
            escalation_rule.outcome(package) + ("" if path == "channel" else "_ledger"),
            digest,
        )
        return ChainOutcome((), (), why, chain_run, package)

    async def _escalate(
        self,
        tenant: Tenant,
        chain: Chain,
        chain_run: ChainRun,
        boundary: int,
        package: SituationPackage,
    ) -> str:
        """The package delivered to the chain's role in the owner-facing channel; the path it
        took, `ledger` where no channel reached the role."""
        declared = chain.escalation
        role = OWNER if declared is None else declared.role
        if declared is not None and declared.path == "ledger":
            return "ledger"
        if self._channels is None or self._raising is None:
            return "ledger"
        channel = await self._channels.of(tenant)
        if channel is None or role not in channel.roles:
            return "ledger"
        react = timedelta(0) if declared is None else declared.react_within
        try:
            await self._raising.execute(
                RaiseReport(
                    tenant=tenant,
                    id=report_id(chain_run.id, boundary),
                    kind=ReportKind.FAILURE,
                    title=package.happened,
                    needed=package.needed,
                    steps=package.options,
                    standing_still=tuple(p for p in (package.tried, package.affected) if p),
                    due=(self._clock.now() + react).date(),
                    links=((f"chain {chain.id}", f"/chains/{chain.id}"),),
                )
            )
        except (NotSent, NoChannel) as error:
            log.warning("a halted chain's report was not sent", chain=chain.id, why=str(error))
            return "ledger"
        return "channel"

    async def _end(
        self, tenant: Tenant, chain_run: ChainRun, state: ChainState, reason: str | None
    ) -> ChainRun:
        """The chain run ended, and measured once against the chain's own objectives."""
        now = self._clock.now()
        ended = chain_run.model_copy(
            update={"state": state, "reason": reason, "ended_at": now, "updated_at": now}
        )
        if state is ChainState.STOPPED and chain_run.runs:
            await self._record(
                tenant,
                STOPPED,
                chain_run.chain,
                chain_run.link,
                None,
                "stopped",
                None,
                run_id=chain_run.runs[-1],
            )
        slo = chain_run.chain.slo
        if slo is not None:
            earlier = [
                r
                for r in await self.runs_of(tenant, chain_run.chain.id)
                if r.ended and r.id != chain_run.id and r.ended_at is not None
            ]
            earlier.sort(key=lambda r: r.ended_at or now)
            recent = [r.state is ChainState.FINISHED for r in earlier][-(COMPLETION_WINDOW - 1) :]
            recent.append(state is ChainState.FINISHED)
            duration = now - chain_run.started_at
            missed = objective_rule.missed(
                duration, tuple(recent), latency=slo.latency, completion=slo.completion
            )
            measured = objective_rule.outcome(missed)
            ended = ended.model_copy(update={"measured": measured})
            await self._record(
                tenant,
                MEASURED,
                chain_run.chain,
                chain_run.link,
                None,
                measured,
                None,
                run_id=chain_run.runs[-1] if chain_run.runs else None,
                duration=duration,
            )
        return await self._keep(tenant, ended)

    # --- helpers ----------------------------------------------------------------------------

    async def _held(self, tenant: Tenant, chain: Chain) -> list[ProcessVersion]:
        async with self._work.transaction(tenant):
            versions = [await self._versions.get(tenant, k.process_version) for k in chain.links]
        linked = [v for v in versions if v is not None]
        found = chains.findings(chain, linked)
        if found:
            raise InvalidProcess(tuple(found))
        return linked

    async def _new_id(self, tenant: Tenant, chain_id: str) -> str:
        """`chr_<chain>_<n>`, counted per chain; without a store, the first."""
        if self._chain_runs is None:
            return f"chr_{chain_id}_1"
        return f"chr_{chain_id}_{len(await self.runs_of(tenant, chain_id)) + 1}"

    async def _keep(self, tenant: Tenant, chain_run: ChainRun) -> ChainRun:
        if self._chain_runs is not None:
            async with self._work.transaction(tenant):
                await self._chain_runs.put(tenant, chain_run)
        return chain_run

    def _stored[T: Stored](self, repository: Repository[T] | None) -> Repository[T]:
        if repository is None:
            raise LookupError("this instance stores no chains")
        return repository

    async def _left(self, tenant: Tenant, chain_run: ChainRun) -> int:
        left = 0
        async with self._work.transaction(tenant):
            for run_id in chain_run.runs:
                entries = await self._ledger.entries(tenant, run_id)
                left += sum(1 for e in entries if e.kind.startswith("egress."))
        return left

    async def _start(
        self,
        tenant: Tenant,
        chain: Chain,
        index: int,
        version: ProcessVersion,
        inputs: Mapping[str, Any],
        actor: str,
    ) -> Run:
        plan = Plan(
            id=link_plan(chain.id, index),
            command_id=f"cmd_{chain.id}_{index + 1}",
            goal=f"link {index + 1} of the chain {chain.name}: {version.ref}",
            autonomy_level=version.autonomy_level,
            steps=version.ordered(),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=actor, at=self._clock.now()),
        )
        return await self._engine.start(
            StartRun(
                plan=plan,
                work=version.work,
                budget=Limits.model_validate(dict(version.limits or {})),
                process_version=version.ref,
                actor=actor,
                tenant=tenant,
                inputs=dict(inputs),
                actions=version.autonomy.action_levels,
            )
        )

    async def _results(self, run: Run) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for step_run in run.step_runs:
            checkpoint = step_run.checkpoint
            if checkpoint is None or checkpoint.result_digest is None:
                continue
            content = await self._objects.get(checkpoint.result_digest)
            if content is not None:
                results[step_run.step_id] = json.loads(content)
        return results

    async def _record(
        self,
        tenant: Tenant,
        kind: str,
        chain: Chain,
        index: int,
        run: Run | None,
        outcome: str,
        digest: str | None,
        *,
        run_id: str | None = None,
        duration: timedelta | None = None,
    ) -> None:
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=kind,
                    refs=LedgerRefs(
                        tenant=tenant,
                        plan_id=link_plan(chain.id, index),
                        run_id=run.id if run is not None else run_id,
                        process_version=None if run is None else run.process_version,
                    ),
                    outcome=outcome,
                    content_digest=digest,
                    duration_seconds=None if duration is None else duration.total_seconds(),
                ),
            )


INTERVAL_SECONDS = 60
"""How often the scheduler looks for a waiting chain whose link finished."""


def chains_tick(
    runs: ChainRuns,
    tenants: ServedTenants,
    clock: Clock,
    *,
    interval_seconds: int = INTERVAL_SECONDS,
) -> Callable[[], Awaitable[None]]:
    """What the scheduler calls on every tick: every tenant's waiting chains are looked at once
    the interval has passed. A look that fails is logged and made again at the next one."""
    last: list[datetime] = []

    async def tick() -> None:
        now = clock.now()
        if last and now - last[0] < timedelta(seconds=interval_seconds):
            return
        last[:] = [now]
        for tenant in await this_round(tenants, "scheduler"):
            try:
                moved = await runs.advance(tenant)
            except Exception as error:  # a look must never take the scheduler down
                log.error(
                    "chains not advanced; the next look tries again",
                    tenant=tenant,
                    error=f"{type(error).__name__}: {error}",
                )
                continue
            for chain_run in moved:
                log.info("a chain went on at its boundary", tenant=tenant, chain_run=chain_run)

    return tick


def _kept(outcome: ChainOutcome) -> ChainRun:
    if outcome.chain_run is None:
        raise LookupError("the chain run was not kept")
    return outcome.chain_run


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()
