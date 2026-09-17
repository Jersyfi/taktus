"""The provenance chain of a run: how a record is built, and how a chain is verified
(ADR-0021 §3). Pure functions, no I/O.

A record is written for every step run that finished with a result — every step that
succeeded, including a `wait` step, which produced nothing but did complete. It carries
identifiers, tokens and digests, never content. `verify` walks a run's records and says where
the chain is broken: a completed step without a record, a record that disagrees with its step
run, an input that names a step run without a record or an artifact that record does not
list, a record that disagrees with the ledger entry it belongs to.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime

from taktus.components.run.domain.model.run import Run, StepRun
from taktus.shared.v1 import (
    InputKind,
    LedgerEntry,
    Provenance,
    ProvenanceInput,
    StepId,
    Value,
)

FINISHED = "step.finished"
SUCCEEDED = "succeeded"

# The bound of ADR-0021 §4, with identifiers of at most 64 characters: the fixed part of a
# record, what each input adds, what each output adds — as a JSON document.
FIXED_BYTES = 1024
BYTES_PER_INPUT = 384
BYTES_PER_OUTPUT = 80


class ChainVerification(Value):
    """The result of walking a run's provenance."""

    records: int
    intact: bool
    findings: tuple[str, ...] = ()


def record(
    run: Run,
    step_run: StepRun,
    *,
    id: str,
    inputs: Sequence[ProvenanceInput],
    entry: LedgerEntry,
    adapter_version: str | None,
    at: datetime,
) -> Provenance:
    """The provenance of a step run that just finished, bound to the ledger entry that says
    so. Everything the ledger entry also carries is taken from the step run, so that the two
    can be checked against each other later."""
    step = run.step(step_run.step_id)
    checkpoint = step_run.checkpoint
    return Provenance(
        id=id,
        run_id=run.id,
        step_id=step_run.step_id,
        process_version=run.process_version,
        method=step.method,
        exactness=step.exactness,
        model=step.model,
        adapter=step_run.adapter,
        adapter_version=adapter_version if step_run.adapter is not None else None,
        inputs=tuple(inputs),
        outputs=tuple(artifact.id for artifact in step_run.artifacts),
        result_digest=None if checkpoint is None else checkpoint.result_digest,
        ledger_seq=entry.seq,
        recorded_at=at,
    )


def size_bytes(provenance: Provenance) -> int:
    """How large the record is as a JSON document, keys sorted, no whitespace."""
    document = provenance.document()
    return len(json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def size_bound(provenance: Provenance) -> int:
    """The most bytes ADR-0021 §4 allows this record: a fixed part plus its inputs and
    outputs."""
    return (
        FIXED_BYTES
        + BYTES_PER_INPUT * len(provenance.inputs)
        + BYTES_PER_OUTPUT * len(provenance.outputs)
    )


def verify(
    run: Run,
    records: Sequence[Provenance],
    entries: Sequence[LedgerEntry] | None = None,
) -> ChainVerification:
    """Walk the run's chain. Every finding names the step. With the run's ledger entries, every
    record is also held against the entry it names."""
    findings: list[str] = []
    by_step: dict[StepId, Provenance] = {}
    for provenance in records:
        if provenance.run_id != run.id:
            findings.append(f"{provenance.step_id}: record belongs to run {provenance.run_id!r}")
            continue
        if provenance.step_id in by_step:
            findings.append(f"{provenance.step_id}: recorded twice")
            continue
        by_step[provenance.step_id] = provenance
    ancestors = _ancestors(run)
    for step_run in run.step_runs:
        own = by_step.pop(step_run.step_id, None)
        if not step_run.done:
            if own is not None:
                findings.append(f"{step_run.step_id}: recorded although it is {step_run.state}")
            continue
        if own is None:
            findings.append(f"{step_run.step_id}: completed without a record")
            continue
        findings.extend(_against_step_run(run, step_run, own))
        findings.extend(_inputs(run, own, ancestors[step_run.step_id], records))
    for step_id in by_step:
        findings.append(f"{step_id}: record for a step the run does not have")
    if entries is not None:
        by_seq = {entry.seq: entry for entry in entries}
        for provenance in records:
            if provenance.run_id == run.id:
                findings.extend(_against_ledger(provenance, by_seq.get(provenance.ledger_seq)))
    return ChainVerification(records=len(records), intact=not findings, findings=tuple(findings))


def _ancestors(run: Run) -> Mapping[StepId, frozenset[StepId]]:
    ancestors: dict[StepId, frozenset[StepId]] = {}
    for step in run.steps:
        own: set[StepId] = set()
        for dependency in step.dependencies:
            own |= {dependency, *ancestors.get(dependency, ())}
        ancestors[step.id] = frozenset(own)
    return ancestors


def _against_step_run(run: Run, step_run: StepRun, provenance: Provenance) -> list[str]:
    step = run.step(step_run.step_id)
    where = step_run.step_id
    expected = {
        "process_version": (run.process_version, provenance.process_version),
        "method": (step.method, provenance.method),
        "exactness": (step.exactness, provenance.exactness),
        "model": (step.model, provenance.model),
        "adapter": (step_run.adapter, provenance.adapter),
        "outputs": (tuple(a.id for a in step_run.artifacts), provenance.outputs),
        "result_digest": (
            None if step_run.checkpoint is None else step_run.checkpoint.result_digest,
            provenance.result_digest,
        ),
    }
    return [
        f"{where}: {name} is {actual!r} in the record, {wanted!r} on the step run"
        for name, (wanted, actual) in expected.items()
        if wanted != actual
    ]


def _inputs(
    run: Run,
    provenance: Provenance,
    ancestors: frozenset[StepId],
    records: Sequence[Provenance],
) -> list[str]:
    findings: list[str] = []
    where = provenance.step_id
    for input in provenance.inputs:
        if input.kind is InputKind.SOURCE:
            continue  # an external source is verified against the connector, not the chain
        if input.run_id != run.id:
            continue  # another run's record is not this run's chain to verify
        producer = next(
            (r for r in records if r.run_id == input.run_id and r.step_id == input.step_id),
            None,
        )
        if input.step_id not in ancestors:
            findings.append(f"{where}: reads {input.step_id!r}, which is not a step before it")
        if producer is None:
            findings.append(f"{where}: reads {input.step_id!r}, which has no record")
            continue
        if input.kind is InputKind.ARTIFACT and (
            input.artifact_id is None or not producer.produced(input.artifact_id)
        ):
            findings.append(
                f"{where}: reads artifact {input.artifact_id!r} of {input.step_id!r}, "
                "which its record does not list"
            )
        if input.kind is InputKind.RESULT and input.digest != producer.result_digest:
            findings.append(
                f"{where}: reads the result of {input.step_id!r} under a digest its record "
                "does not carry"
            )
    return findings


def _against_ledger(provenance: Provenance, entry: LedgerEntry | None) -> list[str]:
    where = provenance.step_id
    if entry is None:
        return [f"{where}: names ledger entry {provenance.ledger_seq}, which does not exist"]
    findings: list[str] = []
    if entry.kind != FINISHED or entry.outcome != SUCCEEDED:
        findings.append(
            f"{where}: ledger entry {entry.seq} is {entry.kind} {entry.outcome or ''}, "
            f"not {FINISHED} {SUCCEEDED}"
        )
    if (entry.refs.run_id, entry.refs.step_id) != (provenance.run_id, provenance.step_id):
        findings.append(f"{where}: ledger entry {entry.seq} is about another step run")
    expected = {
        "method": (entry.method, provenance.method),
        "adapter": (entry.adapter, provenance.adapter),
        "artifact_ids": (entry.refs.artifact_ids or (), provenance.outputs),
        "content_digest": (entry.content_digest, provenance.result_digest),
    }
    findings.extend(
        f"{where}: {name} is {actual!r} in the record, {wanted!r} in ledger entry {entry.seq}"
        for name, (wanted, actual) in expected.items()
        if wanted != actual
    )
    return findings


__all__ = [
    "BYTES_PER_INPUT",
    "BYTES_PER_OUTPUT",
    "FIXED_BYTES",
    "ChainVerification",
    "record",
    "size_bound",
    "size_bytes",
    "verify",
]
