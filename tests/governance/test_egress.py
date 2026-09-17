"""The correction anchor's trigger (ADR-0022 §4): a result has left the system when the
ledger holds an egress entry for it or for anything derived from it. Table tests over
provenance records and ledger entries; no I/O."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from taktus.components.governance.domain.model import ResultRef
from taktus.components.governance.domain.service.egress import closure, left_the_system
from taktus.shared.v1 import (
    EGRESS_KINDS,
    InputKind,
    LedgerEntry,
    Provenance,
    ProvenanceInput,
)

AT = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
ZERO = "sha256:" + "0" * 64


def digest(n: int) -> str:
    return "sha256:" + f"{n:02x}" * 32


def record(
    run_id: str,
    step_id: str,
    seq: int,
    *,
    outputs: tuple[str, ...] = (),
    reads: tuple[tuple[str, str, str | None, int], ...] = (),
    result: int | None = None,
) -> Provenance:
    return Provenance(
        id=f"prov_{run_id}_{step_id}",
        run_id=run_id,
        step_id=step_id,
        process_version="p@1",
        method="rule",
        exactness="exact",
        inputs=tuple(
            ProvenanceInput(
                kind=InputKind.RESULT if artifact is None else InputKind.ARTIFACT,
                run_id=run,
                step_id=step,
                artifact_id=artifact,
                digest=digest(n),
                observed_at=AT,
            )
            for run, step, artifact, n in reads
        ),
        outputs=outputs,
        result_digest=None if result is None else digest(result),
        ledger_seq=seq,
        recorded_at=AT,
    )


def entry(
    seq: int,
    kind: str,
    run_id: str,
    step_id: str,
    *,
    artifacts: tuple[str, ...] | None = None,
    content: int | None = None,
) -> LedgerEntry:
    return LedgerEntry.model_validate(
        {
            "seq": seq,
            "ts": AT,
            "kind": kind,
            "prev_hash": ZERO,
            "hash": ZERO,
            "refs": {
                "run_id": run_id,
                "step_id": step_id,
                **({} if artifacts is None else {"artifact_ids": list(artifacts)}),
            },
            **({} if content is None else {"content_digest": digest(content)}),
        }
    )


# r0/fetch produced `source`. r1/a read it and produced a value (digest 1). r1/b read that
# value and produced `file`. r1/d read nothing of theirs and produced `aside`.
RECORDS = (
    record("r0", "fetch", 2, outputs=("source",)),
    record("r1", "a", 10, result=1, reads=(("r0", "fetch", "source", 0),)),
    record("r1", "b", 13, outputs=("file",), reads=(("r1", "a", None, 1),)),
    record("r1", "d", 16, outputs=("aside",)),
)
SOURCE = ResultRef(run_id="r0", step_id="fetch", artifact_id="source")
VALUE = ResultRef(run_id="r1", step_id="a", digest=digest(1))
FILE = ResultRef(run_id="r1", step_id="b", artifact_id="file")
ASIDE = ResultRef(run_id="r1", step_id="d", artifact_id="aside")


def test_the_closure_is_the_chain_read_forward() -> None:
    assert closure(SOURCE, RECORDS) == (SOURCE, VALUE, FILE)
    assert closure(VALUE, RECORDS) == (VALUE, FILE)
    assert closure(FILE, RECORDS) == (FILE,)
    assert closure(ASIDE, RECORDS) == (ASIDE,)


def test_a_result_nothing_wrote_out_has_not_left() -> None:
    entries = [
        entry(13, "step.finished", "r1", "b", artifacts=("file",)),
        entry(14, "run.finished", "r1", "b"),
    ]
    for result in (SOURCE, VALUE, FILE, ASIDE):
        assert left_the_system(result, RECORDS, entries) is None


@pytest.mark.parametrize("kind", sorted(EGRESS_KINDS))
def test_an_egress_entry_for_a_derived_artifact_means_the_source_has_left(kind: str) -> None:
    entries = [entry(20, kind, "r1", "b", artifacts=("file",))]
    egress = left_the_system(SOURCE, RECORDS, entries)
    assert egress is not None
    assert egress.seq == 20 and egress.kind == kind and egress.through == FILE
    assert left_the_system(VALUE, RECORDS, entries) is not None, "the value the file came from"
    assert left_the_system(ASIDE, RECORDS, entries) is None, "an unrelated artifact stays inside"


def test_an_egress_entry_for_a_value_names_it_by_digest() -> None:
    entries = [entry(21, "egress.read", "r1", "a", content=1)]
    egress = left_the_system(SOURCE, RECORDS, entries)
    assert egress is not None and egress.through == VALUE
    assert left_the_system(FILE, RECORDS, entries) is None, "what was built on it is still inside"
    wrong_digest = [entry(21, "egress.read", "r1", "a", content=7)]
    assert left_the_system(VALUE, RECORDS, wrong_digest) is None


def test_only_the_three_egress_kinds_count() -> None:
    assert EGRESS_KINDS == {"egress.write", "egress.delivery", "egress.read"}
    entries = [
        entry(30, "step.finished", "r1", "b", artifacts=("file",)),
        entry(31, "artifact.stored", "r1", "b", artifacts=("file",)),
        entry(32, "connector.called", "r1", "b", artifacts=("file",)),
    ]
    assert left_the_system(FILE, RECORDS, entries) is None


def test_an_egress_entry_about_another_step_run_does_not_count() -> None:
    entries = [entry(40, "egress.write", "r9", "b", artifacts=("file",))]
    assert left_the_system(FILE, RECORDS, entries) is None
