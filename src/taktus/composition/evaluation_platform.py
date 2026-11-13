"""An evaluation platform an organisation already uses, connected by capability, each of its
capabilities switched on by being configured (UC-5.8, ADR-0305).

- **Evaluation backend** (`evaluations.records`). A scored evaluation is copied: its cases as a
  data set's items, each case run's result with its scores on the run's trace. The evaluation
  stays whole in Taktus; the copy adds nothing to it. What the platform scored on its own is
  read back beside Taktus's verdict, never in place of it.
- **Prompt mirroring** (`prompts.versions`). The prompt of every step on a language model of a
  process version is mirrored as a version of a prompt in the platform, named
  `<process>.<step>`, its configuration naming the version and step it comes from. The bundle is
  the truth (ADR-0011): a version in the platform never becomes a process version by itself.
- **Cost reconciliation** (`observability.costs`). The cost the platform computed for a run's
  traces is compared with the run's own consumption in US dollars. A difference beyond the
  tolerance is reported, as a ledger entry `platform.cost.differed`; Taktus keeps its own
  figure (UC-8.5).

Trace export is the telemetry port's (`TAKTUS_OTLP_*`), not this module's. A capability nobody
configured is off: its act does nothing and calls nothing. A platform that fails or refuses is
logged and recorded, and changes nothing in Taktus: removing it breaks no process.

This is wiring, because each act crosses components — process, run and the connector pool —
and only the composition root may hold them all.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog

from taktus.adapters.driven.telemetry.masking import MaskingPolicy
from taktus.components.process.domain.model import Evaluation, Process, ProcessVersion
from taktus.components.run.domain.model import Run
from taktus.components.run.ports.connectors import ConnectorPool
from taktus.ports.clock import Clock
from taktus.ports.connector import CallContext, CallFailed, ConnectorError
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.ports.worker import CredentialReference
from taktus.shared.v1 import LedgerRefs, Method

log = structlog.get_logger(__name__)

EVALUATIONS = "evaluations.records"
PROMPTS = "prompts.versions"
COSTS = "observability.costs"
COPIED = "platform.evaluation.copied"
MIRRORED = "platform.prompt.mirrored"
RECONCILED = "platform.cost.reconciled"
DIFFERED = "platform.cost.differed"
TAKTUS = "taktus"
TOLERANCE = Decimal("0.01")
"""How far, in US dollars, the platform's cost of a run may lie from Taktus's own before the
difference is reported."""
ENDED = ("run.finished", "run.escalated", "run.halted")
"""The run component's kinds of a run's end, as the ledger records them."""
DAY = timedelta(days=1)
CURRENCY = "usd"
"""The currency the platform computes its costs in, as Taktus's consumption names it."""


@dataclass(frozen=True)
class Reconciled:
    run: str
    own: Decimal | None
    """The run's own consumption in US dollars; None where it consumed none in that currency."""
    platform: Decimal | None
    """The platform's cost of the run's traces; None where it holds none of them."""
    traces: tuple[str, ...]

    @property
    def difference(self) -> Decimal | None:
        if self.own is None or self.platform is None:
            return None
        return self.platform - self.own

    @property
    def differs(self) -> bool:
        difference = self.difference
        return difference is not None and abs(difference) > TOLERANCE


@dataclass(frozen=True)
class PlatformScores:
    """What the platform holds for an evaluation's copy: per case, the scores on its trace. It
    stands beside Taktus's verdict and is never read as one."""

    evaluation: str
    verdict: str | None
    """Taktus's own verdict, unchanged."""
    cases: Mapping[str, Mapping[str, float]]


class EvaluationPlatform:
    def __init__(
        self,
        connectors: ConnectorPool,
        ledger: Ledger,
        work: UnitOfWork,
        *,
        credential: str = "EVALUATION_PLATFORM_KEYS",
        processes: Repository[Process] | None = None,
        versions: Repository[ProcessVersion] | None = None,
        runs: Repository[Run] | None = None,
        masking: MaskingPolicy | None = None,
    ) -> None:
        """`credential`: the parameter the platform's calls name; the instance's own, since
        what goes there is the organisation's and no person's. `processes`, `versions` and
        `runs`: what the scheduler's look reads to mirror and to reconcile; without them it
        does neither."""
        self._masking = masking or MaskingPolicy()
        """The organisation's policy, as for spans (ADR-0286): what leaves is masked first."""
        self._processes = processes
        self._versions = versions
        self._runs = runs
        self._connectors = connectors
        self._ledger = ledger
        self._work = work
        self._credential = credential

    # --- the evaluation backend ------------------------------------------------------------

    async def copy(
        self, tenant: Tenant, evaluation: Evaluation, traces: Mapping[str, str] | None = None
    ) -> bool:
        """Copy a scored evaluation; False where the capability is off, or the platform did not
        take it. `traces`: each case run's trace, where the ledger knows it; its run otherwise."""
        if evaluation.verdict is None or not evaluation.results:
            return False
        cases = {c.id: c for c in evaluation.cases}
        results = [r for r in evaluation.results if r.case in cases and r.run_id is not None]
        scored = [r for r in results if any(s.score is not None for s in r.scores)]
        if not scored:
            return False
        kept = list(dict.fromkeys(r.case for r in scored))[:50]
        scored = [r for r in scored if r.case in kept][:50]
        input = {
            "dataset": evaluation.process_id,
            "run": f"{evaluation.id} {evaluation.version}",
            "description": f"Taktus evaluation {evaluation.id}, {evaluation.purpose}, "
            f"verdict {evaluation.verdict}",
            "items": [
                {"id": c.id, "input": dict(c.inputs), "expected": dict(c.targets)}
                for c in evaluation.cases
                if c.id in kept
            ],
            "results": [
                {
                    "item": r.case,
                    "trace": (traces or {}).get(r.run_id or "", r.run_id),
                    "scores": [
                        {
                            "name": _score_name(s.scorer, s.dimension, str(r.side)),
                            "value": s.score,
                            "comment": f"{s.how}, {s.method}",
                        }
                        for s in r.scores
                        if s.score is not None
                    ][:10],
                }
                for r in scored
            ],
        }
        output = await self._call(
            tenant, EVALUATIONS, "write", input, _key("evaluation", tenant, evaluation.id)
        )
        await self._record(
            tenant,
            COPIED,
            LedgerRefs(tenant=tenant, process_version=evaluation.candidate or evaluation.version),
            "copied" if output is not None else "failed",
            input if output is not None else None,
        )
        return output is not None

    async def scored(self, tenant: Tenant, evaluation: Evaluation) -> bool:
        """The hook a scored evaluation calls: its copy, with each case run's trace."""
        runs = [r.run_id for r in evaluation.results if r.run_id is not None]
        return await self.copy(tenant, evaluation, await self.traces_of(tenant, runs))

    async def scores(self, tenant: Tenant, evaluation: Evaluation) -> PlatformScores | None:
        """What the platform holds for the evaluation's copy, beside Taktus's verdict; None
        where the capability is off or the platform holds no copy."""
        output = await self._call(
            tenant,
            EVALUATIONS,
            "read",
            {"dataset": evaluation.process_id, "run": f"{evaluation.id} {evaluation.version}"},
            _key("scores", tenant, evaluation.id),
        )
        if output is None:
            return None
        cases: dict[str, dict[str, float]] = {}
        for item in output.get("items") or []:
            for score in item.get("scores") or []:
                value = score.get("value")
                if isinstance(value, int | float) and not isinstance(value, bool):
                    cases.setdefault(str(item.get("trace")), {})[str(score.get("name"))] = value
        return PlatformScores(
            evaluation=evaluation.id,
            verdict=None if evaluation.verdict is None else str(evaluation.verdict),
            cases=cases,
        )

    # --- prompt mirroring ------------------------------------------------------------------

    async def mirror(self, tenant: Tenant, version: ProcessVersion) -> dict[str, int]:
        """Mirror the prompt of every step on a language model; the platform's version of each,
        by step. Empty where the capability is off or no step has a prompt."""
        mirrored: dict[str, int] = {}
        for step in version.steps:
            work = version.work.get(step.id)
            if step.method is not Method.LLM or not isinstance(work, Mapping):
                continue
            prompt = work.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip():
                continue
            system = work.get("system")
            text = f"{system}\n\n{prompt}" if isinstance(system, str) and system else prompt
            output = await self._call(
                tenant,
                PROMPTS,
                "mirror",
                {
                    "name": f"{version.process_id}.{step.id}",
                    "text": text,
                    "source": f"{version.ref}/{step.id}",
                },
                _key("prompt", tenant, version.ref, step.id, text),
            )
            if output is None:
                if await self._connectors.resolve(PROMPTS) is None:
                    return {}
                continue
            mirrored[step.id] = int(output["version"])
            await self._record(
                tenant,
                MIRRORED,
                LedgerRefs(tenant=tenant, process_version=version.ref, step_id=step.id),
                "mirrored",
                {"step": step.id, "platform_version": output["version"]},
            )
        return mirrored

    # --- cost reconciliation ---------------------------------------------------------------

    async def reconcile(self, tenant: Tenant, run: Run) -> Reconciled | None:
        """The platform's cost of the run's traces against the run's own; a difference beyond
        the tolerance is recorded `platform.cost.differed`. None where the capability is off
        or the run has no trace."""
        traces = await self._traces(tenant, run.id)
        if not traces:
            return None
        output = await self._call(
            tenant, COSTS, "read", {"traces": list(traces[:20])}, _key("costs", tenant, run.id)
        )
        if output is None:
            return None
        platform: Decimal | None = None
        for read in output.get("traces") or []:
            cost = read.get("cost")
            if read.get("absent") or cost is None:
                continue
            try:
                platform = (platform or Decimal(0)) + Decimal(str(cost))
            except InvalidOperation:
                continue
        spent = run.consumed().currency
        own = None if spent is None else spent.get(CURRENCY)
        reconciled = Reconciled(
            run=run.id,
            own=None if own is None else Decimal(str(own)),
            platform=platform,
            traces=traces,
        )
        refs = LedgerRefs(tenant=tenant, run_id=run.id, process_version=run.process_version)
        document = {
            "own": None if reconciled.own is None else str(reconciled.own),
            "platform": None if platform is None else str(platform),
            "currency": "USD",
            "traces": list(traces),
        }
        outcome = (
            "differs"
            if reconciled.differs
            else ("unknown" if reconciled.difference is None else "agrees")
        )
        await self._record(tenant, RECONCILED, refs, outcome, document)
        if reconciled.differs:
            await self._record(tenant, DIFFERED, refs, "differs", document)
            log.warning(
                "platform.cost_differs",
                run=run.id,
                own=document["own"],
                platform=document["platform"],
            )
        return reconciled

    # --- the scheduler's look --------------------------------------------------------------

    async def look(self, tenant: Tenant, now: datetime) -> None:
        """Mirror the prompts of every active version not mirrored yet, and reconcile every run
        that ended in the last day and was not reconciled; each only where its capability is
        configured."""
        if (
            self._processes is not None
            and self._versions is not None
            and await self._connectors.resolve(PROMPTS) is not None
        ):
            async with self._work.transaction(tenant):
                mirrored = {
                    e.refs.process_version for e in await self._ledger.of_kinds(tenant, [MIRRORED])
                }
                active = [
                    f"{p.id}@{p.active_version}"
                    for p in await self._processes.list(tenant)
                    if p.active_version is not None
                ]
                found = [
                    await self._versions.get(tenant, ref) for ref in active if ref not in mirrored
                ]
            for version in found:
                if version is not None:
                    await self.mirror(tenant, version)
        if self._runs is not None and await self._connectors.resolve(COSTS) is not None:
            async with self._work.transaction(tenant):
                ended = {
                    e.refs.run_id
                    for e in await self._ledger.of_kinds(tenant, ENDED, since=now - DAY)
                    if e.refs.run_id is not None
                }
                reconciled = {
                    e.refs.run_id
                    for e in await self._ledger.of_kinds(tenant, [RECONCILED], since=now - 2 * DAY)
                }
                runs = [await self._runs.get(tenant, r) for r in sorted(ended - reconciled)]
            for run in runs:
                if run is not None and not run.rehearsal:
                    await self.reconcile(tenant, run)

    # --- the platform's calls --------------------------------------------------------------

    async def _traces(self, tenant: Tenant, run_id: str) -> tuple[str, ...]:
        async with self._work.transaction(tenant):
            entries = await self._ledger.entries(tenant, run_id)
        seen: dict[str, None] = {}
        for entry in entries:
            if entry.refs.trace_id is not None:
                seen.setdefault(entry.refs.trace_id, None)
        return tuple(seen)

    async def traces_of(self, tenant: Tenant, run_ids: Sequence[str]) -> dict[str, str]:
        """The first trace of each run, as the ledger records it."""
        found: dict[str, str] = {}
        for run_id in run_ids:
            traces = await self._traces(tenant, run_id)
            if traces:
                found[run_id] = traces[0]
        return found

    async def _call(
        self, tenant: Tenant, capability: str, verb: str, input: Mapping[str, Any], key: str
    ) -> dict[str, Any] | None:
        resolved = await self._connectors.resolve(capability)
        if resolved is None:
            return None  # switched off: nothing is called
        context = CallContext(
            tenant=tenant,
            identity=TAKTUS,
            run_id="platform",
            step_id=capability.replace(".", "-"),
            attempt=1,
            idempotency_key=key,
            credentials=(CredentialReference(name=self._credential, injected_as="env"),),
        )
        try:
            result = await resolved.connector.call(
                f"{capability}.{verb}", context, _masked(self._masking, "", input)
            )
        except CallFailed as failed:
            log.info("platform.refused", capability=capability, cause=str(failed.error.cause))
            return None
        except ConnectorError as error:
            log.info("platform.unreachable", capability=capability, error=type(error).__name__)
            return None
        return dict(result.output)

    async def _record(
        self,
        tenant: Tenant,
        kind: str,
        refs: LedgerRefs,
        outcome: str,
        document: Mapping[str, Any] | None,
    ) -> None:
        digest = (
            None
            if document is None
            else "sha256:"
            + hashlib.sha256(
                json.dumps(document, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
        )
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant, Fact(kind=kind, refs=refs, outcome=outcome, content_digest=digest)
            )


def platform_tick(
    platform: EvaluationPlatform,
    tenants: Callable[[], Awaitable[Sequence[Tenant]]],
    clock: Clock,
    *,
    interval_seconds: int = 3600,
) -> Callable[[], Awaitable[None]]:
    """What the scheduler calls on every tick: every tenant is looked at once an hour. A look
    that fails is logged and made again at the next interval: a platform never stops the
    scheduler."""
    last: list[datetime] = []

    async def tick() -> None:
        now = clock.now()
        if last and now - last[0] < timedelta(seconds=interval_seconds):
            return
        last[:] = [now]
        for tenant in await tenants():
            try:
                await platform.look(tenant, now)
            except Exception as error:  # a platform never takes the scheduler down
                log.warning("platform.look_failed", tenant=tenant, error=type(error).__name__)

    return tick


def _masked(policy: MaskingPolicy, name: str, value: Any) -> Any:
    """What leaves, masked by the organisation's policy: an entry whose name the policy names is
    replaced whole, and every text is searched for the kinds it names (ADR-0286)."""
    if isinstance(value, Mapping):
        return {k: _masked(policy, str(k), v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_masked(policy, name, v) for v in value]
    return policy.value(name, value) if name else value


def _score_name(scorer: str, dimension: str | None, side: str) -> str:
    name = scorer.replace("#", "-")
    if dimension:
        name = f"{name}-{dimension}"
    return f"{side}-{name}"


def _key(*parts: str) -> str:
    return "taktus:platform:" + hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:40]
