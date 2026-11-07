"""A chain of processes run link by link, every handover recorded (UC-15.4, ADR-0274).

`ChainRuns.run` holds the chain to the versions it links (`process/domain/service/chains.py`),
starts the first link with the chain's inputs, and after each link that finished builds the
handover from its recorded results — read from the object store by each step run's checkpoint.
A handover that lacks a declared item does not happen: `chain.halted` names the boundary and the
items, and the chain stops there. Otherwise `chain.handover` records the handover's document by
digest — every item with its value's digest, its step and its clause — and the next link starts
with exactly those inputs. A link that did not finish — one waiting at an anchor among them —
stops the chain at that link; the links before it keep their results.

This is wiring, because the chain is the process component's and its links are runs of the run
component.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from taktus.components.process.domain.model import InvalidProcess, ProcessVersion
from taktus.components.process.domain.model.chain import Chain
from taktus.components.process.domain.service import chains
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.ports.worker import Limits
from taktus.shared.v1 import Commissioned, LedgerRefs, Plan, PlanResult, PlanStatus

HANDOVER = "chain.handover"
HALTED = "chain.halted"
_LINK_PLAN = re.compile(r"^pln_([a-z][a-z0-9-]*)_[1-9][0-9]*$")


def link_plan(chain: str, index: int) -> str:
    """The identifier of the plan of the chain's link at `index`, counted from zero."""
    return f"pln_{chain}_{index + 1}"


def chain_of(plan_id: str) -> str | None:
    """The chain whose link the plan is, read back from `link_plan`; None for any other plan.
    What sums the value balance per chain reads a chain's processes by it (ADR-0288)."""
    found = _LINK_PLAN.match(plan_id)
    return None if found is None else found.group(1)


@dataclass(frozen=True)
class ChainOutcome:
    runs: tuple[Run, ...]
    """The run of every link that started, in order."""
    handovers: tuple[dict[str, Any], ...] = field(default=())
    """The document of every handover recorded."""
    halted: str | None = None
    """Why the chain stopped before its last link ended; None where every link finished."""


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
    ) -> None:
        self._engine = engine
        self._versions = versions
        self._objects = objects
        self._ledger = ledger
        self._work = work
        self._clock = clock

    async def run(
        self, tenant: Tenant, chain: Chain, inputs: Mapping[str, Any], actor: str
    ) -> ChainOutcome:
        async with self._work.transaction(tenant):
            versions = [await self._versions.get(tenant, k.process_version) for k in chain.links]
        linked = [v for v in versions if v is not None]
        found = chains.findings(chain, linked)
        if found:
            raise InvalidProcess(tuple(found))
        runs: list[Run] = []
        handed: list[dict[str, Any]] = []
        given: Mapping[str, Any] = inputs
        for index, (link, version) in enumerate(zip(chain.links, linked, strict=True)):
            run = await self._start(tenant, chain, index, version, given, actor)
            runs.append(run)
            if run.state is not RunState.FINISHED:
                return ChainOutcome(
                    tuple(runs),
                    tuple(handed),
                    f"link {index + 1}, {link.process_version}, is {run.state}: the chain waits "
                    "at its boundary",
                )
            if index + 1 == len(chain.links):
                break
            following = chain.links[index + 1]
            results = await self._results(run)
            passing = chains.handover(following.handover, results)
            if passing.missing:
                names = ", ".join(f"{i.input} ({i.clause})" for i in passing.missing)
                await self._record(tenant, HALTED, run, "missing", None)
                return ChainOutcome(
                    tuple(runs),
                    tuple(handed),
                    f"the handover to {following.process_version} lacks {names}: nothing was "
                    "handed over, and the chain goes to a person (UC-4.5)",
                )
            document = {
                "chain": chain.id,
                "from": run.id,
                "to": following.process_version,
                "items": [
                    {
                        "input": item.input,
                        "step": item.step,
                        "select": item.select,
                        "clause": item.clause,
                        "digest": _digest(passing.given[item.input]),
                    }
                    for item in following.handover
                ],
            }
            digest = await self._objects.put(_canonical(document))
            await self._record(tenant, HANDOVER, run, "handed_over", digest)
            handed.append(document)
            given = passing.given
        return ChainOutcome(tuple(runs), tuple(handed))

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
        self, tenant: Tenant, kind: str, run: Run, outcome: str, digest: str | None
    ) -> None:
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=kind,
                    refs=LedgerRefs(
                        tenant=tenant, run_id=run.id, process_version=run.process_version
                    ),
                    outcome=outcome,
                    content_digest=digest,
                ),
            )


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()
