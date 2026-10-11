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
original engine is the restored state — nothing was ever changed.

**Rehearsing is not acting** (ADR-0030). Both runs of a process — with the integration and
without it — are rehearsal runs: every outward connector operation answers with the recorded
response of the most recent real call of that operation through that adapter, and nothing
leaves the system. A process can be rehearsed only when every outward operation it would call,
in either configuration, has such a recording, and no worker step may reach hosts; otherwise
its verdict rests on resolution alone, and the finding says why. Every rehearsal run is in the
ledger, attributed to the removal test's identity and marked as a rehearsal on every entry, so
that "what did the removal test do" is answerable from the ledger like everything else.

**A verdict names its configuration** (issue #36): the result records which adapter stood
behind the identifier, what it declared and its version, because the same identifier can name
a different adapter next week.

**The conformance suite** of an integration's contract is run by the instance through the
catalog's one writer, when a process asks for it with the integration's identifier (ADR-0044,
NTC-0091).

**Which steps an integration serves** is decided the way the run decides it: the step's work
is parsed, and the pool that would serve it — a worker for the capabilities it requires, a
connector for the capability of its operation, a model for its purpose — is asked with and
without the integration. "With" means with the integration first in its pool: an adapter the
configuration places behind another that serves the same capabilities is exercised on the
steps it can serve, and its alternative is the adapter in front of it (ADR-0078). The verdicts
are the catalog component's rules (`domain.service.removal`); this module only observes.
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
    RunConformance,
    RunConformanceHandler,
)
from taktus.components.catalog.domain.model import (
    Configuration,
    ProcessFinding,
    RemovalResult,
    RunSummary,
    StepFinding,
    Verdict,
)
from taktus.components.catalog.domain.service import removal
from taktus.components.catalog.ports import NotConfigured, NotRunnable
from taktus.components.command.application.service import CommissionPlan, CommissionPlanHandler
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.run.application.query import RecordedResponses
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import (
    ConnectorRule,
    Run,
    RunError,
    RunState,
    StepState,
    WorkerWork,
    parse_work,
)
from taktus.composition.pools import Pools
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.ports.worker import Limits
from taktus.shared.v1 import Command, Intent, ReplyTo

DATABASE = "persistence.database"
CHANNEL = "channel.loopback"

type EngineFactory = Callable[[StaticWorkerPool, StaticConnectorPool, StaticModelPool], RunEngine]

__all__ = ["CHANNEL", "DATABASE", "EngineFactory", "Loopback", "Pools", "summary"]


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
        recordings: RecordedResponses,
        clock: Clock,
        ids: Identifiers,
        conformance: RunConformanceHandler | None = None,
    ) -> None:
        self._pools = pools
        self._conformance = conformance
        self._recordings = recordings
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
        for adapter, capabilities, version in await self._pools.workers.members():
            found.append(
                _present(
                    {
                        "integration": adapter,
                        "family": "worker",
                        "serves": sorted(capabilities),
                        "version": version,
                    }
                )
            )
        for adapter, declaration in await self._pools.connectors.members():
            if adapter == LOOPBACK:
                continue  # Taktus itself is not an integration of Taktus
            found.append(
                _present(
                    {
                        "integration": adapter,
                        "family": "connector",
                        "serves": list(declaration.capabilities),
                        "operations": [operation.name for operation in declaration.operations],
                        "version": declaration.version,
                    }
                )
            )
        for adapter, purposes, version in self._pools.models.members():
            found.append(
                _present(
                    {
                        "integration": adapter,
                        "family": "model",
                        "serves": list(purposes),
                        "version": version,
                    }
                )
            )
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
        configuration = await self._pools.configuration(integration) or Configuration(
            adapter=integration, serves=tuple(entry["serves"])
        )
        if integration in removal.EXCEPTIONS:
            return RemovalResult(
                integration=integration,
                family="persistence",
                verdict=Verdict.EXCEPTION,
                tested_at=self._clock.now(),
                run_id=run_id,
                reason=removal.EXCEPTIONS[integration],
                configuration=configuration,
            ).document()
        withheld = self._pools.without(integration)
        processes: list[ProcessFinding] = []
        for version in await self._registered(tenant):
            uses = await self._uses(version, integration)
            if not uses:
                continue
            findings, hosts, calls, unparsed = uses
            missing = [name for name, given in version.inputs.items() if given.example is None]
            unrecorded = [
                f"{operation} through {adapter}"
                for operation, adapter in calls
                if await self._recordings.find(tenant, adapter, operation) is None
            ]
            why_not = removal.safe_to_run(hosts, unrecorded, missing)
            if unparsed:
                why_not = f"not run: {unparsed}"
            if why_not is not None:
                processes.append(removal.resolved_only(version.ref, findings, why_not))
                continue
            # The baseline runs with the integration first in its pool, so that one standing
            # behind another adapter is exercised where it can serve (ADR-0078).
            baseline = await self._rehearse(
                tenant, version, self._pools.first(integration), identity, integration
            )
            rehearsed = await self._rehearse(tenant, version, withheld, identity, integration)
            processes.append(removal.exercised(version.ref, findings, baseline, rehearsed))
        return RemovalResult(
            integration=integration,
            family=entry["family"],
            verdict=removal.overall(processes),
            tested_at=self._clock.now(),
            run_id=run_id,
            processes=tuple(processes),
            reason=None if processes else removal.UNUSED,
            configuration=configuration,
        ).document()

    async def record(self, tenant: Tenant, result: dict[str, Any]) -> dict[str, Any]:
        parsed = RemovalResult.model_validate(result)
        maturity, entry = await self._record.execute(RecordRemovalResult(parsed, tenant))
        current = await self._pools.configuration(maturity.id)
        return {
            "integration": maturity.id,
            "maturity": str(maturity.maturity(current)),
            "missing": list(maturity.missing(current)),
            "ledger_seq": entry.seq,
            "content_digest": entry.content_digest,
        }

    async def conformance(
        self, tenant: Tenant, integration: str, *, run_id: str, identity: str
    ) -> dict[str, Any]:
        """Run the conformance suite of the integration's contract against the endpoint this
        instance's configuration resolves for it, and record what it found (ADR-0044). The
        input is the identifier alone: no report, no verdict and no date can be handed in."""
        if self._conformance is None:
            raise UnknownIntegration("this instance runs no conformance suite")
        try:
            maturity, entry = await self._conformance.execute(
                RunConformance(integration, tenant, actor=identity, run_id=run_id)
            )
        except NotConfigured as error:
            raise UnknownIntegration(str(error)) from error
        except NotRunnable as error:
            raise ValueError(str(error)) from error
        current = await self._pools.configuration(maturity.id)
        result = maturity.conformance
        if result is None:  # unreachable: the handler has just written it
            raise ValueError(f"no conformance run was recorded for {integration}")
        return {
            "integration": maturity.id,
            "contract": result.contract,
            "outcome": result.outcome,
            "failed": list(result.failed),
            "inconclusive": list(result.inconclusive),
            "maturity": str(maturity.maturity(current)),
            "missing": list(maturity.missing(current)),
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
    ) -> tuple[list[StepFinding], list[str], list[tuple[str, str]], str | None] | None:
        """The steps of the version the integration serves, with their findings when it is
        withheld; the worker steps whose frame allows hosts; every outward connector call a
        rehearsal must answer from a recording, as (operation, adapter), in either
        configuration; and why the work could not be read, if it could not. None when the
        version does not use the integration — or is the removal test itself, which reaches
        Taktus through the loopback."""
        # With the integration first: a worker configured behind another that serves the same
        # capabilities is found serving the steps it can serve, so that withholding it is
        # measured and not only declared unused (ADR-0078).
        pools = self._pools.first(integration)
        withheld = self._pools.without(integration)
        examples = {name: given.example for name, given in version.inputs.items()}
        findings: list[StepFinding] = []
        hosts: list[str] = []
        calls: list[tuple[str, str]] = []
        unparsed: str | None = None
        for step in version.ordered():
            try:
                work = parse_work(step, version.work.get(step.id), examples)
            except RunError as error:
                unparsed = unparsed or str(error)
                continue
            served = await pools.serving(step, work)
            if served is None:
                continue
            what, adapter = served
            if adapter == LOOPBACK:
                return None
            alternative = await withheld.serving(step, work)
            if isinstance(work, WorkerWork) and work.allowed_hosts:
                hosts.append(step.id)
            elif isinstance(work, ConnectorRule) and await pools.outward(work):
                instead = None if alternative is None else alternative[1]
                for serving in dict.fromkeys((adapter, instead)):
                    if serving is not None:
                        calls.append((work.operation, serving))
            if adapter != integration:
                continue
            findings.append(
                removal.step_finding(step, what, None if alternative is None else alternative[1])
            )
        return (findings, hosts, calls, unparsed) if findings else None

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
                    rehearsal=True,
                    actions=version.autonomy.action_levels,
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


def _present(entry: dict[str, Any]) -> dict[str, Any]:
    """The entry without the fields the adapter did not declare."""
    return {key: value for key, value in entry.items() if value is not None}


async def _alternatives(pools: Pools, family: str, served: str) -> list[str]:
    if family == "worker":
        worker = await pools.workers.resolve((served,))
        return [] if worker is None else [worker.adapter]
    if family == "connector":
        connector = await pools.connectors.resolve(served)
        return [] if connector is None else [connector.adapter]
    model = await pools.models.resolve(served)
    return [] if model is None else [model.adapter]
