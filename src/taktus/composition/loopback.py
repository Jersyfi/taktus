"""Taktus as its own connector: the instance behind the loopback connector's `Orchestrator`.

The removal test (`blueprints/self-operation/`) asks four things of the instance it runs in:
what is configured, what one integration serves and who uses it, what happens to those
processes when the integration is withheld, and to record the result. This module answers
them over the instance's own services — the pools the run engine resolves adapters from, the
registered process versions, the engine itself, and the catalog's recording use case. It is
wiring, and it is here because only the composition root may hold all of that at once
(`composition/README.md`).

**Withholding is not mutation.** An instance's configuration is its environment and does not
change while it runs. The removal test therefore rehearses: it builds the same engine over the
same stores with one adapter left out of the pools, runs the process through it, and the
original engine is the restored state — nothing was ever changed. Every rehearsal run is a
real run in the ledger, attributed to the removal test's identity, so that "what did the
removal test do" is answerable from the ledger like everything else.

**Which steps an integration serves** is decided the way the run decides it: the step's work
is parsed, and the pool that would serve it — a worker for the capabilities it requires, a
connector for the capability of its operation, a model for its purpose — is asked with and
without the integration. The verdicts are the catalog component's rules (`domain.service.
removal`); this module only observes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from taktus.adapters.driven.connectors.loopback import ADAPTER as LOOPBACK
from taktus.adapters.driven.connectors.loopback import UnknownIntegration
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.models.pool import StaticModelPool
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.catalog.application.service import (
    RecordRemovalResult,
    RecordRemovalResultHandler,
)
from taktus.components.catalog.domain.model import (
    ProcessFinding,
    RemovalResult,
    RunSummary,
    StepFinding,
    Verdict,
)
from taktus.components.catalog.domain.service import removal
from taktus.components.command.application.service import CommissionPlan, CommissionPlanHandler
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import (
    ConnectorRule,
    LlmWork,
    Run,
    RunError,
    RunState,
    StepState,
    WaitWork,
    WorkerWork,
    parse_work,
)
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.ports.worker import Limits
from taktus.shared.v1 import Command, Intent, ReplyTo, Step

DATABASE = "persistence.database"
CHANNEL = "channel.loopback"

type EngineFactory = Callable[[StaticWorkerPool, StaticConnectorPool, StaticModelPool], RunEngine]


class Pools:
    """The three pools the run engine resolves adapters from, as one configuration."""

    def __init__(
        self, workers: StaticWorkerPool, connectors: StaticConnectorPool, models: StaticModelPool
    ) -> None:
        self.workers = workers
        self.connectors = connectors
        self.models = models

    def without(self, integration: str) -> Pools:
        return Pools(
            self.workers.without(integration),
            self.connectors.without(integration),
            self.models.without(integration),
        )

    async def serving(self, step: Step, work: Any) -> tuple[str, str | None] | None:
        """What the step needs and which adapter serves it, or None when the step needs no
        adapter: (`served`, adapter identifier or None when nothing serves it)."""
        if isinstance(work, WorkerWork):
            needed = ", ".join(step.required_capabilities)
            worker = await self.workers.resolve(step.required_capabilities)
            return needed, None if worker is None else worker.adapter
        if isinstance(work, ConnectorRule):
            connector = await self.connectors.resolve(work.capability)
            return work.capability, None if connector is None else connector.adapter
        if isinstance(work, WaitWork) and work.until is not None:
            connector = await self.connectors.resolve(work.until.capability)
            return work.until.capability, None if connector is None else connector.adapter
        if isinstance(work, LlmWork):
            model = await self.models.resolve(work.purpose)
            return f"purpose {work.purpose}", None if model is None else model.adapter
        return None

    async def outward(self, work: Any) -> bool:
        """Whether running the step could leave the system: a connector operation declared
        outward, or a worker with hosts it may reach."""
        if isinstance(work, WorkerWork):
            return bool(work.allowed_hosts)
        if isinstance(work, ConnectorRule):
            connector = await self.connectors.resolve(work.capability)
            if connector is None:
                return False
            operation = connector.declaration.operation(work.operation)
            return operation is not None and operation.outward
        return False


class Loopback:
    """The `Orchestrator` of the loopback connector, over one instance's services."""

    def __init__(
        self,
        *,
        pools: Pools,
        versions: Repository[ProcessVersion],
        work: UnitOfWork,
        commission: CommissionPlanHandler,
        engine_for: EngineFactory,
        record: RecordRemovalResultHandler,
        clock: Clock,
        ids: Identifiers,
    ) -> None:
        self._pools = pools
        self._versions = versions
        self._work = work
        self._commission = commission
        self._engine_for = engine_for
        self._record = record
        self._clock = clock
        self._ids = ids

    # --- what is configured -----------------------------------------------------------------

    async def list_integrations(self, tenant: Tenant) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        for adapter, capabilities in await self._pools.workers.members():
            found.append(
                {"integration": adapter, "family": "worker", "serves": sorted(capabilities)}
            )
        for adapter, declaration in await self._pools.connectors.members():
            if adapter == LOOPBACK:
                continue  # Taktus itself is not an integration of Taktus
            found.append(
                {
                    "integration": adapter,
                    "family": "connector",
                    "serves": list(declaration.capabilities),
                }
            )
        for adapter, purposes in self._pools.models.members():
            found.append({"integration": adapter, "family": "model", "serves": list(purposes)})
        found.append(
            {
                "integration": DATABASE,
                "family": "persistence",
                "serves": ["state", "queue", "ledger", "provenance"],
                "exception": removal.EXCEPTIONS[DATABASE],
            }
        )
        return found

    async def describe(self, tenant: Tenant, integration: str) -> dict[str, Any]:
        entry = await self._entry(tenant, integration)
        if entry["family"] == "persistence":
            return {**entry, "alternatives": {}, "processes": []}
        rest = self._pools.without(integration)
        alternatives: dict[str, list[str]] = {}
        for served in entry["serves"]:
            alternatives[served] = await _alternatives(rest, entry["family"], served)
        processes = []
        for version in await self._registered(tenant):
            uses = await self._uses(version, integration)
            if uses:
                processes.append({"process": version.ref, "steps": [f.step for f in uses[0]]})
        return {**entry, "alternatives": alternatives, "processes": processes}

    # --- the exercise --------------------------------------------------------------------------

    async def exercise(
        self, tenant: Tenant, integration: str, *, run_id: str, identity: str
    ) -> dict[str, Any]:
        entry = await self._entry(tenant, integration)
        if integration in removal.EXCEPTIONS:
            return RemovalResult(
                integration=integration,
                family="persistence",
                verdict=Verdict.EXCEPTION,
                tested_at=self._clock.now(),
                run_id=run_id,
                reason=removal.EXCEPTIONS[integration],
            ).document()
        withheld = self._pools.without(integration)
        processes: list[ProcessFinding] = []
        for version in await self._registered(tenant):
            uses = await self._uses(version, integration)
            if not uses:
                continue
            findings, outward, unparsed = uses
            missing = [name for name, given in version.inputs.items() if given.example is None]
            why_not = removal.safe_to_run(outward, missing)
            if unparsed:
                why_not = f"not run: {unparsed}"
            if why_not is not None:
                processes.append(removal.resolved_only(version.ref, findings, why_not))
                continue
            baseline = await self._rehearse(tenant, version, self._pools, identity, integration)
            rehearsed = await self._rehearse(tenant, version, withheld, identity, integration)
            processes.append(removal.exercised(version.ref, findings, baseline, rehearsed))
        return RemovalResult(
            integration=integration,
            family=entry["family"],
            verdict=removal.overall(processes),
            tested_at=self._clock.now(),
            run_id=run_id,
            processes=tuple(processes),
            reason=None if processes else "no registered process uses this integration",
        ).document()

    async def record(self, tenant: Tenant, result: dict[str, Any]) -> dict[str, Any]:
        parsed = RemovalResult.model_validate(result)
        maturity, entry = await self._record.execute(RecordRemovalResult(parsed, tenant))
        return {
            "integration": maturity.id,
            "maturity": str(maturity.maturity),
            "missing": list(maturity.missing),
            "ledger_seq": entry.seq,
            "content_digest": entry.content_digest,
        }

    # --- helpers -------------------------------------------------------------------------------

    async def _entry(self, tenant: Tenant, integration: str) -> dict[str, Any]:
        for entry in await self.list_integrations(tenant):
            if entry["integration"] == integration:
                return entry
        raise UnknownIntegration(f"no configured integration {integration!r}")

    async def _registered(self, tenant: Tenant) -> list[ProcessVersion]:
        async with self._work.transaction(tenant):
            return sorted(await self._versions.list(tenant), key=lambda v: v.ref)

    async def _uses(
        self, version: ProcessVersion, integration: str
    ) -> tuple[list[StepFinding], list[str], str | None] | None:
        """The steps of the version the integration serves, with their findings when it is
        withheld; the steps whose effect would leave the system; and why the work could not
        be read, if it could not. None when the version does not use the integration — or is
        the removal test itself, which reaches Taktus through the loopback."""
        withheld = self._pools.without(integration)
        examples = {name: given.example for name, given in version.inputs.items()}
        findings: list[StepFinding] = []
        outward: list[str] = []
        unparsed: str | None = None
        for step in version.ordered():
            try:
                work = parse_work(step, version.work.get(step.id), examples)
            except RunError as error:
                unparsed = unparsed or str(error)
                continue
            served = await self._pools.serving(step, work)
            if served is None:
                continue
            what, adapter = served
            if adapter == LOOPBACK:
                return None
            if await self._pools.outward(work):
                outward.append(step.id)
            if adapter != integration:
                continue
            alternative = await withheld.serving(step, work)
            findings.append(
                removal.step_finding(step, what, None if alternative is None else alternative[1])
            )
        return (findings, outward, unparsed) if findings else None

    async def _rehearse(
        self, tenant: Tenant, version: ProcessVersion, pools: Pools, identity: str, of: str
    ) -> RunSummary:
        """One run of the version through an engine over the given pools, and where it came
        to. A run that cannot start — the bundle names no limits — is a run that broke."""
        inputs = {name: given.example for name, given in version.inputs.items()}
        command = Command(
            id=self._ids.new("cmd"),
            channel=CHANNEL,
            identity=identity,
            org_path=(tenant,),
            intent=Intent(
                raw=f"rehearse {version.ref} for the removal test of {of}", recognised="process.run"
            ),
            context={"inputs": inputs, "removal_test": of},
            reply_to=ReplyTo(channel=CHANNEL, address="ledger"),
            received_at=self._clock.now(),
        )
        plan = await self._commission.execute(
            CommissionPlan(
                command=command,
                tenant=tenant,
                goal=f"removal test of {of}: run {version.name} ({version.ref})",
                autonomy_level=version.autonomy_level,
                steps=version.ordered(),
            )
        )
        engine = self._engine_for(pools.workers, pools.connectors, pools.models)
        try:
            run = await engine.start(
                StartRun(
                    plan=plan,
                    work=version.work,
                    budget=Limits.model_validate(dict(version.limits or {})),
                    process_version=version.ref,
                    actor=identity,
                    tenant=tenant,
                    inputs=inputs,
                )
            )
        except (RunError, ValueError) as error:
            return RunSummary(run_id=plan.id, state="not_started", cause=str(error)[:200])
        return summary(run)


def summary(run: Run) -> RunSummary:
    ended = None
    if run.state is not RunState.FINISHED:
        for step_run in run.step_runs:
            if step_run.state in (StepState.FAILED, StepState.REJECTED, StepState.STOPPED):
                ended = step_run.step_id
    return RunSummary(
        run_id=run.id,
        state=str(run.state),
        cause=None if run.cause is None else str(run.cause),
        at_step=ended,
        consumption=run.consumed(),
    )


async def _alternatives(pools: Pools, family: str, served: str) -> list[str]:
    if family == "worker":
        worker = await pools.workers.resolve((served,))
        return [] if worker is None else [worker.adapter]
    if family == "connector":
        connector = await pools.connectors.resolve(served)
        return [] if connector is None else [connector.adapter]
    model = await pools.models.resolve(served)
    return [] if model is None else [model.adapter]
