"""Has a result left the system? The predicate behind the correction anchor (ADR-0022 §4).

A result has left the system when the ledger holds an egress entry — `egress.write`,
`egress.delivery`, `egress.read` — for it or for anything derived from it. *Derived from* is
the provenance chain read forward: the outputs of every step run whose inputs name the result,
transitively, across runs. Pure functions over provenance records and ledger entries; the
records and the entries are read from their components, never written here.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Sequence

from taktus.components.governance.domain.model import Egress, ResultRef
from taktus.shared.v1 import EGRESS_KINDS, InputKind, LedgerEntry, Provenance


def closure(start: ResultRef, records: Sequence[Provenance]) -> tuple[ResultRef, ...]:
    """The result and everything derived from it, in the order it was reached. A step run
    that read the result — as an artifact, or as the value by digest — derives every one of
    its outputs and its value from it."""
    reached: list[ResultRef] = [start]
    seen: set[tuple[str, str, str | None, str | None]] = {_key(start)}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for record in records:
            if not _reads(record, current):
                continue
            for derived in _outputs(record):
                if _key(derived) not in seen:
                    seen.add(_key(derived))
                    reached.append(derived)
                    queue.append(derived)
    return tuple(reached)


def left_the_system(
    result: ResultRef, records: Sequence[Provenance], entries: Iterable[LedgerEntry]
) -> Egress | None:
    """The first egress entry that names the result or anything derived from it, or None:
    the result is still inside, and correcting it is not anchored."""
    members = closure(result, records)
    for entry in entries:
        if entry.kind not in EGRESS_KINDS:
            continue
        for member in members:
            if _names(entry, member):
                return Egress(seq=entry.seq, kind=entry.kind, through=member)
    return None


def _key(ref: ResultRef) -> tuple[str, str, str | None, str | None]:
    return (ref.run_id, ref.step_id, ref.artifact_id, ref.digest)


def _reads(record: Provenance, ref: ResultRef) -> bool:
    for input in record.inputs:
        if input.kind is InputKind.SOURCE:
            continue
        if (input.run_id, input.step_id) != (ref.run_id, ref.step_id):
            continue
        if input.kind is InputKind.ARTIFACT and input.artifact_id == ref.artifact_id:
            return True
        if (
            input.kind is InputKind.RESULT
            and ref.artifact_id is None
            and (input.digest == ref.digest)
        ):
            return True
    return False


def _outputs(record: Provenance) -> list[ResultRef]:
    outputs = [
        ResultRef(run_id=record.run_id, step_id=record.step_id, artifact_id=artifact_id)
        for artifact_id in record.outputs
    ]
    if record.result_digest is not None:
        outputs.append(
            ResultRef(run_id=record.run_id, step_id=record.step_id, digest=record.result_digest)
        )
    return outputs


def _names(entry: LedgerEntry, member: ResultRef) -> bool:
    refs = entry.refs
    if (refs.run_id, refs.step_id) != (member.run_id, member.step_id):
        return False
    if member.artifact_id is not None:
        return member.artifact_id in (refs.artifact_ids or ())
    return member.digest is not None and entry.content_digest == member.digest
