"""Use case: a person records what a step's result should have been (ADR-0084).

A correction is a record, not a repair. It changes nothing of the run: the step run, its result
and its provenance record stay as they were written (ADR-0021). It changes nothing outside
either: correcting a result that has left the system is the correction anchor's (ADR-0022), and
nothing here acts. What it does is say, for the step's measures and for maturation, which result
was the right one. A step's correction rate is read from these records, and a corrected result
is the label a training learns from.

The correction is the ledger entry `step.corrected`, which names the run, the step and the person
who corrected, and the corrected value by the digest of its content in the object store. A newer
correction of the same step run takes the place of an older one. The measures count corrections
and never say whose they are (principle 14, ADR-0015).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from taktus.components.run.domain.model import Run, RunError, StepState
from taktus.components.run.domain.service.maturation import CORRECTED
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Digest, LedgerRefs


@dataclass(frozen=True)
class CorrectResult:
    tenant: Tenant
    run_id: str
    step_id: str
    value: Any
    """What the result should have been: for a step on a language model, the right answer's
    text."""
    actor: str
    """The person who corrects. Any identity the tenant knows may, until rights per role exist
    (UC-7.3)."""


class CorrectResultHandler:
    def __init__(
        self, runs: Repository[Run], work: UnitOfWork, objects: ObjectStore, ledger: Ledger
    ) -> None:
        self._runs = runs
        self._work = work
        self._objects = objects
        self._ledger = ledger

    async def execute(self, command: CorrectResult) -> Digest:
        """The digest of the corrected value, once it is recorded. `RunError` when there is no
        result to correct."""
        if command.value is None or (isinstance(command.value, str) and not command.value.strip()):
            raise RunError("a correction names what the result should have been")
        content = json.dumps(command.value, ensure_ascii=False, sort_keys=True).encode("utf-8")
        async with self._work.transaction(command.tenant):
            run = await self._runs.get(command.tenant, command.run_id)
            if run is None:
                raise RunError(f"no run {command.run_id!r}")
            try:
                step_run = run.step_run(command.step_id)
            except KeyError:
                raise RunError(f"run {run.id!r} has no step {command.step_id!r}") from None
            checkpoint = step_run.checkpoint
            if (
                step_run.state is not StepState.SUCCEEDED
                or checkpoint is None
                or checkpoint.result_digest is None
            ):
                raise RunError(
                    f"step {command.step_id!r} of run {run.id!r} has no result to correct"
                )
            digest = await self._objects.put(content)
            await self._ledger.record(
                command.tenant,
                Fact(
                    kind=CORRECTED,
                    refs=LedgerRefs(
                        tenant=command.tenant,
                        plan_id=run.plan_id,
                        process_version=run.process_version,
                        run_id=run.id,
                        step_id=step_run.step_id,
                        actor=command.actor,
                    ),
                    method=step_run.method,
                    content_digest=digest,
                ),
            )
        return digest
