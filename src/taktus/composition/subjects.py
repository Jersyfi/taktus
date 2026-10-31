"""Data-protection requests and the processing evidence, wired (ADR-0176, UC-11.2).

The governance component keeps the request and its rules. What a request finds, erases and
exports lives in other components and ports — the runs, the provenance store, the ledger, the
traces and the object store — and is answered here, because components never import each
other.

`RunHoldings` finds a subject through what references it: the provenance records whose case
scope names it, and the runs whose scoped steps resolve it from their intake (ADR-0176 §2). It
erases an ended run's content and verifies the ledger and the run's provenance chain after it
(§3), keeping every object another run of the instance still references (§4), and generates an
export, which it never stores (§5).

`ProcessingEvidence` gathers the evidence's facts from the register of what acts for the
tenant, the active versions, the tenant's declarations, its trace retention and the ledger,
and hands them to the reporting component, which draws the document (§8).
"""

from __future__ import annotations

import base64
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Literal

from taktus.components.governance.application.service import (
    TenantResidency,
    TenantSources,
)
from taktus.components.governance.application.service.subjects import KINDS as REQUEST_KINDS
from taktus.components.governance.domain.model.subjects import (
    ERASED,
    KEPT_SHARED,
    Erased,
    HeldObject,
    HeldStep,
    Holding,
)
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.reporting.domain.model.acting import Register
from taktus.components.reporting.domain.service import evidence
from taktus.components.run.domain.model import Run, RunError, RunState, control_of
from taktus.components.run.domain.service.provenance import verify as verify_provenance
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import (
    ProvenanceStore,
    Repository,
    Tenant,
    TenantStore,
    UnitOfWork,
)
from taktus.ports.traces import Traces
from taktus.shared.v1 import EGRESS_KINDS, LedgerEntry, LedgerRefs, Step

CONTENT_ERASED = "run.content_erased"
"""On an erased run's own chain: its content was erased for the request it names."""
ENDED = frozenset({RunState.FINISHED, RunState.ESCALATED})
"""A run in these states moves no more: its inputs are read by no step again."""
ALL_LINES = 1_000_000
"""More trace lines than any step keeps: a request reads a step's whole trace."""

type Locations = Callable[[Tenant], Awaitable[Mapping[str, str | None]]]
"""Where each configured adapter declares it processes, by adapter."""


def subjects_of(run: Run) -> dict[str, str]:
    """The subject each scoped step of the run serves, by step, resolved from its intake as
    the run resolves it (ADR-0130 §2). A step whose work cannot be read serves none."""
    found: dict[str, str] = {}
    for step in run.steps:
        subject = _subject(run, step)
        if subject is not None:
            found[step.id] = subject
    return found


def _subject(run: Run, step: Step) -> str | None:
    try:
        scope = control_of(step, run.work.get(step.id), run.inputs).scope
    except RunError:  # work that cannot be read, an erased input among it, names no subject
        return None
    return None if scope is None else str(scope.subject)


def _referenced(run: Run) -> set[str]:
    """The objects a run's step runs reference: results, artifacts and messages."""
    digests: set[str] = set()
    for step_run in run.step_runs:
        if step_run.checkpoint is not None and step_run.checkpoint.result_digest is not None:
            digests.add(step_run.checkpoint.result_digest)
        digests.update(a.digest for a in step_run.artifacts)
        digests.update(m.digest for m in step_run.messages)
    return digests


def _decoded(content: bytes | None, media_type: str | None = None) -> Any:
    """JSON content as JSON, other bytes as base64 with their media type; None where the
    object is gone."""
    if content is None:
        return None
    try:
        return {"json": json.loads(content.decode("utf-8"))}
    except (UnicodeDecodeError, ValueError):
        return {
            "base64": base64.b64encode(content).decode("ascii"),
            "media_type": media_type or "application/octet-stream",
        }


class RunHoldings:
    """The governance component's port `SubjectHoldings`, over the runs and their stores."""

    def __init__(
        self,
        *,
        runs: Repository[Run],
        provenance: ProvenanceStore,
        ledger: Ledger,
        objects: ObjectStore,
        work: UnitOfWork,
        tenants: TenantStore,
        traces: Traces | None = None,
        locations: Locations | None = None,
    ) -> None:
        self._runs = runs
        self._provenance = provenance
        self._ledger = ledger
        self._objects = objects
        self._work = work
        self._tenants = tenants
        self._traces = traces
        self._locations = locations

    # --- finding -------------------------------------------------------------------------

    async def holdings(self, tenant: Tenant, subject: str) -> Sequence[Holding]:
        async with self._work.transaction(tenant):
            recorded = await self._provenance.of_subject(tenant, subject)
            every = await self._runs.list(tenant)
        by_provenance = {r.run_id for r in recorded}
        found: list[tuple[Run, tuple[Literal["provenance", "intake"], ...]]] = []
        for run in every:
            ways: list[Literal["provenance", "intake"]] = []
            if run.id in by_provenance:
                ways.append("provenance")
            if subject in subjects_of(run).values():
                ways.append("intake")
            if ways:
                found.append((run, tuple(ways)))
        ours = {run.id for run, _ in found}
        elsewhere = await self._elsewhere(tenant, ours)
        held = [await self._holding(tenant, run, ways, subject, elsewhere) for run, ways in found]
        return sorted(held, key=lambda h: (h.created_at, h.run_id))

    async def _elsewhere(self, tenant: Tenant, ours: set[str]) -> set[str]:
        """Every object a run of the instance references that is not one of `ours`: the
        object store is one for the instance (ADR-0176 §4). Only digests cross tenants."""
        digests: set[str] = set()
        served = {entry.id for entry in await self._tenants.every()} | {tenant}
        for other in sorted(served):
            async with self._work.transaction(other):
                runs = await self._runs.list(other)
            for run in runs:
                if other == tenant and run.id in ours:
                    continue
                digests |= _referenced(run)
        return digests

    async def _holding(
        self,
        tenant: Tenant,
        run: Run,
        ways: tuple[Literal["provenance", "intake"], ...],
        subject: str,
        elsewhere: set[str],
    ) -> Holding:
        async with self._work.transaction(tenant):
            records = {r.step_id: r for r in await self._provenance.of_run(tenant, run.id)}
            entries = await self._ledger.entries(tenant, run.id)
            built_on: set[str] = set()
            for step_id in records:
                for later in await self._provenance.derived(tenant, run.id, step_id):
                    if later.run_id != run.id:
                        built_on.add(f"{later.run_id}/{later.step_id}")
            lines: dict[str, int] = {}
            if self._traces is not None:
                for step_run in run.step_runs:
                    lines[step_run.step_id] = len(
                        await self._traces.lines(tenant, run.id, step_run.step_id, limit=ALL_LINES)
                    )
        served = subjects_of(run)
        objects: dict[str, HeldObject] = {}

        def hold(
            digest: str, kind: Any, step_id: str | None, artifact_id: str | None = None
        ) -> None:
            if digest in objects:
                return
            objects[digest] = HeldObject(
                digest=digest,
                kind=kind,
                step_id=step_id,
                artifact_id=artifact_id,
                kept=KEPT_SHARED if digest in elsewhere else None,
            )

        for step_run in run.step_runs:
            if step_run.checkpoint is not None and step_run.checkpoint.result_digest is not None:
                hold(step_run.checkpoint.result_digest, "result", step_run.step_id)
            for artifact in step_run.artifacts:
                hold(artifact.digest, "artifact", step_run.step_id, artifact.id)
            for message in step_run.messages:
                hold(message.digest, "message", step_run.step_id)
        for entry in entries:
            if entry.content_digest is not None:
                hold(entry.content_digest, "record", entry.refs.step_id)
        erased_for = next(
            (e.refs.subject_request_id for e in entries if e.kind == CONTENT_ERASED), None
        )
        return Holding(
            run_id=run.id,
            process_version=run.process_version,
            state=run.state.value,
            ended=run.state in ENDED,
            created_at=run.created_at,
            found_through=ways,
            inputs=tuple(sorted(k for k, v in run.inputs.items() if v != ERASED)),
            steps=tuple(
                HeldStep(
                    step_id=sr.step_id,
                    method=sr.method.value,
                    adapter=sr.adapter,
                    state=sr.state.value,
                    recorded=sr.step_id in records,
                    scoped=served.get(sr.step_id) == subject,
                    trace_lines=lines.get(sr.step_id, 0),
                )
                for sr in run.step_runs
            ),
            objects=tuple(objects.values()),
            left_the_system=sum(1 for e in entries if e.kind in EGRESS_KINDS),
            built_on=tuple(sorted(built_on)),
            other_subjects=len({s for s in served.values() if s != subject}),
            erased_for=erased_for,
        )

    # --- erasing -------------------------------------------------------------------------

    async def erase(self, tenant: Tenant, request_id: str, holdings: Sequence[Holding]) -> Erased:
        ended = [h for h in holdings if h.ended]
        removed = kept = 0
        # Objects first: a removal is idempotent, so a store that fails half-way leaves the
        # request to be confirmed again on the same holdings (ADR-0176 §3).
        for holding in ended:
            for held in holding.objects:
                if held.kept is not None:
                    kept += 1
                elif await self._objects.remove(held.digest):
                    removed += 1
        inputs = lines = 0
        for holding in ended:
            async with self._work.transaction(tenant):
                run = await self._runs.get(tenant, holding.run_id)
                if run is None:
                    continue
                inputs += sum(1 for v in run.inputs.values() if v != ERASED)
                await self._runs.put(
                    tenant,
                    run.model_copy(update={"inputs": dict.fromkeys(run.inputs, ERASED)}),
                )
                if self._traces is not None:
                    lines += await self._traces.erase_run(tenant, run.id)
                await self._ledger.record(
                    tenant,
                    Fact(
                        kind=CONTENT_ERASED,
                        refs=LedgerRefs(
                            run_id=run.id,
                            process_version=run.process_version,
                            subject_request_id=request_id,
                        ),
                        outcome="erased",
                    ),
                )
        ledger_intact, provenance_intact, findings = await self.verify(
            tenant, [h.run_id for h in ended]
        )
        return Erased(
            runs=tuple(h.run_id for h in ended),
            pending=tuple(h.run_id for h in holdings if not h.ended),
            objects_removed=removed,
            objects_kept=kept,
            inputs_erased=inputs,
            trace_lines_erased=lines,
            ledger_intact=ledger_intact,
            provenance_intact=provenance_intact,
            findings=findings,
        )

    async def verify(
        self, tenant: Tenant, run_ids: Sequence[str]
    ) -> tuple[bool, bool, tuple[str, ...]]:
        """The ledger walked from its first entry, and the provenance chain of every run held
        against its ledger entries: whether each verifies, and what was found."""
        findings: list[str] = []
        async with self._work.transaction(tenant):
            chain = await self._ledger.verify(tenant, full=True)
            findings.extend(f"ledger: {f}" for f in chain.findings)
            provenance_intact = True
            for run_id in run_ids:
                run = await self._runs.get(tenant, run_id)
                if run is None:
                    continue
                checked = verify_provenance(
                    run,
                    await self._provenance.of_run(tenant, run_id),
                    await self._ledger.entries(tenant, run_id),
                )
                provenance_intact &= checked.intact
                findings.extend(f"{run_id}: {f}" for f in checked.findings)
        return chain.intact, provenance_intact, tuple(findings)

    # --- exporting -----------------------------------------------------------------------

    async def export(
        self, tenant: Tenant, holdings: Sequence[Holding], *, processing: bool
    ) -> Mapping[str, Any]:
        located = {} if self._locations is None or not processing else await self._locations(tenant)
        runs: list[dict[str, Any]] = []
        for holding in holdings:
            async with self._work.transaction(tenant):
                run = await self._runs.get(tenant, holding.run_id)
                trace: dict[str, list[dict[str, Any]]] = {}
                if run is not None and self._traces is not None:
                    for step_run in run.step_runs:
                        found = await self._traces.lines(
                            tenant, run.id, step_run.step_id, limit=ALL_LINES
                        )
                        if found:
                            trace[step_run.step_id] = [
                                {
                                    "ts": line.ts.isoformat(),
                                    "type": line.type,
                                    "detail": line.detail,
                                }
                                for line in found
                            ]
            if run is None:
                continue
            steps: list[dict[str, Any]] = []
            for step_run in run.step_runs:
                result = (
                    None
                    if step_run.checkpoint is None or step_run.checkpoint.result_digest is None
                    else _decoded(await self._objects.get(step_run.checkpoint.result_digest))
                )
                step: dict[str, Any] = {
                    "step": step_run.step_id,
                    "method": step_run.method.value,
                    "state": step_run.state.value,
                    "finished_at": None
                    if step_run.finished_at is None
                    else step_run.finished_at.isoformat(),
                    "result": result,
                    "artifacts": [
                        {
                            "id": a.id,
                            "kind": a.kind,
                            "title": a.title,
                            "content": _decoded(await self._objects.get(a.digest), a.media_type),
                        }
                        for a in step_run.artifacts
                    ],
                    "trace": trace.get(step_run.step_id, []),
                }
                if processing:
                    step["processing"] = {
                        "adapter": step_run.adapter,
                        "location": None
                        if step_run.adapter is None
                        else located.get(step_run.adapter) or "undeclared",
                    }
                steps.append(step)
            runs.append(
                {
                    "run": run.id,
                    "process_version": run.process_version,
                    "created_at": run.created_at.isoformat(),
                    "state": run.state.value,
                    "inputs": dict(run.inputs),
                    "steps": steps,
                }
            )
        document: dict[str, Any] = {"runs": runs}
        if processing:
            days = None if self._traces is None else await self._retention(tenant)
            document["keeping"] = evidence.keeping(days)
        return document

    async def _retention(self, tenant: Tenant) -> int | None:
        if self._traces is None:
            return None
        async with self._work.transaction(tenant):
            return (await self._traces.retention(tenant)).days


class ProcessingEvidence:
    """The evidence of what is processed for a tenant, where, by which adapter and kept how
    long, generated from configuration and the ledger (ADR-0176 §8)."""

    def __init__(
        self,
        *,
        register: Callable[[Tenant, frozenset[str]], Awaitable[Register]],
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
        sources: TenantSources,
        residency: TenantResidency,
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
        traces: Traces | None = None,
    ) -> None:
        self._register = register
        self._processes = processes
        self._versions = versions
        self._sources = sources
        self._residency = residency
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._traces = traces

    async def locations(self, tenant: Tenant) -> dict[str, str | None]:
        """Where each adapter that acts for the tenant declares it processes: what an access
        export states beside each step (ADR-0176 §5)."""
        async with self._work.transaction(tenant):
            processes = await self._processes.list(tenant)
        register = await self._register(tenant, frozenset(p.id for p in processes))
        return {row.adapter: row.location for row in register.rows}

    async def evidence(self, tenant: Tenant) -> dict[str, Any]:
        now = self._clock.now()
        async with self._work.transaction(tenant):
            processes = await self._processes.list(tenant)
            versions = [
                v
                for p in processes
                if p.active_version is not None
                if (v := await self._versions.get(tenant, f"{p.id}@{p.active_version}")) is not None
            ]
            requests = await self._ledger.of_kinds(tenant, REQUEST_KINDS)
            days = None if self._traces is None else (await self._traces.retention(tenant)).days
        register = await self._register(tenant, frozenset(p.id for p in processes))
        declaration = await self._sources.declaration(tenant)
        scoped = {
            (v.process_id, step.id)
            for v in versions
            for step in v.ordered()
            if isinstance(v.work.get(step.id), Mapping) and "scope" in v.work[step.id]
        }
        return evidence.processing(
            register,
            personal=declaration.personal,
            scoped=scoped,
            permitted=(await self._residency.rule(tenant)).location,
            retention_days=days,
            requests=_counted(requests),
            generated_at=now,
        )


def _counted(entries: Sequence[LedgerEntry]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry.kind] = counts.get(entry.kind, 0) + 1
    return counts


__all__ = ["CONTENT_ERASED", "ProcessingEvidence", "RunHoldings", "subjects_of"]
