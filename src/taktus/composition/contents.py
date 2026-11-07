"""What the recorded results of a step hold, for the window of a result defect (UC-4.11,
ADR-0271 §4, §5): the governance component's port `RecordedContents`.

`shapes` reads, for every record of a step's series, the content the step read — its own result
where it read a source, otherwise the results of the steps it read — from the object store, and
gives its shape by the governance component's rule (`defects.shape_of`). `marked` finds the
check that marked a result suspect (`check.suspect`, its place as outcome) and, where it judges
the value alone — a distribution, bounds, the shape of the source — runs it again over the
recorded results of the series, each against what was recorded before it, by the run
component's own check functions. A check that reads a source is not run again: the source
cannot be read as it was.

This is wiring, because the results are the run component's, the rule the governance
component's, and the content the object store's.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping, Sequence
from typing import Any

from taktus.components.governance.domain.service.defects import shape_of
from taktus.components.run.domain.model import Run
from taktus.components.run.domain.model.work import control_of, select
from taktus.components.run.domain.service import checking
from taktus.ports.ledger import Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import ProvenanceStore, Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Check, CheckKind, InputKind, Provenance

SUSPECT = "check.suspect"
AGAIN = frozenset({CheckKind.DISTRIBUTION, CheckKind.BOUNDS, CheckKind.SOURCE_SHAPE})
"""The checks that judge the value alone, and so can be run again over recorded results."""
_ABSENT = object()


class StepContents:
    def __init__(
        self,
        *,
        objects: ObjectStore,
        runs: Repository[Run],
        provenance: ProvenanceStore,
        ledger: Ledger,
        work: UnitOfWork,
    ) -> None:
        self._objects = objects
        self._runs = runs
        self._provenance = provenance
        self._ledger = ledger
        self._work = work

    async def shapes(
        self, tenant: Tenant, series: Sequence[Provenance]
    ) -> Mapping[tuple[str, str], str]:
        found: dict[tuple[str, str], str] = {}
        for record in series:
            read = await self._read(tenant, record)
            if read:
                found[(record.run_id, record.step_id)] = " + ".join(shape_of(c) for c in read)
        return found

    async def marked(
        self, tenant: Tenant, run_id: str, step_id: str, series: Sequence[Provenance]
    ) -> Collection[str]:
        check, part = await self._marking(tenant, run_id, step_id)
        if check is None:
            return frozenset()
        marked: set[str] = set()
        earlier: list[Any] = []
        for position, record in enumerate(series, start=1):
            value = await self._value(record.result_digest, part)
            if value is _ABSENT:
                continue
            if check.kind is CheckKind.DISTRIBUTION:
                finding = checking.distribution(position, check, value, earlier)
            elif check.kind is CheckKind.BOUNDS:
                finding = checking.bounds(position, check, value)
            else:
                finding = checking.source_shape(position, check, value)
            if not finding.passed:
                marked.add(record.run_id)
            earlier.append(value)
        return frozenset(marked)

    async def _marking(
        self, tenant: Tenant, run_id: str, step_id: str
    ) -> tuple[Check | None, str | None]:
        """The check that marked the step's result suspect, where it can be run again, and the
        part of the result it judges."""
        async with self._work.transaction(tenant):
            entries = await self._ledger.of_kinds(tenant, (SUSPECT,))
            run = await self._runs.get(tenant, run_id)
        places = [
            e.outcome
            for e in entries
            if e.refs.run_id == run_id and e.refs.step_id == step_id and e.outcome
        ]
        if run is None or not places:
            return None, None
        step = run.step(step_id)
        position = int(places[-1].removeprefix("check_"))
        checks = step.checks or ()
        if not 1 <= position <= len(checks) or checks[position - 1].kind not in AGAIN:
            return None, None
        given = control_of(step, run.work.get(step_id), run.inputs).checking
        return checks[position - 1], None if given is None else given.select

    async def _read(self, tenant: Tenant, record: Provenance) -> list[Any]:
        """What the record's step read: its own result where it read a source, otherwise the
        results of the steps it read."""
        if any(i.kind is InputKind.SOURCE for i in record.inputs):
            value = await self._value(record.result_digest, None)
            return [] if value is _ABSENT else [value]
        read: list[Any] = []
        for given in record.inputs:
            if given.kind is not InputKind.RESULT or given.run_id is None:
                continue
            async with self._work.transaction(tenant):
                upstream = await self._provenance.of_run(tenant, given.run_id)
            for other in upstream:
                if other.step_id == given.step_id:
                    value = await self._value(other.result_digest, None)
                    if value is not _ABSENT:
                        read.append(value)
        return read

    async def _value(self, digest: str | None, part: str | None) -> Any:
        if digest is None:
            return _ABSENT
        content = await self._objects.get(digest)
        if content is None:
            return _ABSENT
        try:
            return select(json.loads(content), part)
        except (KeyError, ValueError):
            return _ABSENT
