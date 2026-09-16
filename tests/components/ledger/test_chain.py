"""The hash chain: linking, the hash rule, verification, and that every alteration is seen."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest
from fakes import FakeClock

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.ledger.domain.model import canonical, hash_of, link, verify
from taktus.ports.ledger import Fact
from taktus.shared.v1 import Consumption, LedgerEntry, LedgerRefs, Method

AT = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def fact(kind: str = "run.created", **refs: str) -> Fact:
    return Fact(kind=kind, refs=LedgerRefs(run_id="run_1", **refs))


def test_the_first_entry_has_no_predecessor() -> None:
    entry = link(None, fact(), AT)
    assert entry.seq == 1
    assert entry.prev_hash is None
    assert entry.document()["prev_hash"] is None, "written as null, as the schema requires"


def test_the_hash_rule_is_the_documented_one() -> None:
    entry = link(None, fact(), AT)
    document = entry.document()
    del document["hash"]
    expected = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert entry.hash == "sha256:" + hashlib.sha256(expected.encode("utf-8")).hexdigest()
    assert canonical(entry.document()) == expected.encode("utf-8")


def test_entries_link_and_verify() -> None:
    first = link(None, fact(), AT)
    second = link(first, fact("step.finished", step_id="a"), AT)
    third = link(second, fact("run.finished"), AT)
    assert (second.seq, second.prev_hash) == (2, first.hash)
    assert (third.seq, third.prev_hash) == (3, second.hash)
    result = verify([first, second, third])
    assert result.intact and result.entries == 3 and result.findings == ()


def chain(length: int = 4) -> list[LedgerEntry]:
    entries: list[LedgerEntry] = []
    previous = None
    for n in range(length):
        previous = link(previous, fact(f"step.event_{n}", step_id=f"s{n}"), AT)
        entries.append(previous)
    return entries


def test_an_altered_field_is_found() -> None:
    entries = chain()
    entries[1] = entries[1].model_copy(update={"kind": "step.forged"})
    result = verify(entries)
    assert not result.intact
    assert result.findings == ("entry 2: hash does not match its content",)


def test_an_altered_field_with_a_recomputed_hash_breaks_the_link() -> None:
    entries = chain()
    forged = entries[1].model_copy(update={"kind": "step.forged"})
    entries[1] = forged.model_copy(update={"hash": hash_of(forged)})
    result = verify(entries)
    assert not result.intact
    assert result.findings == ("entry 3: prev_hash does not match entry 2",)


def test_a_removed_entry_is_found() -> None:
    entries = chain()
    del entries[1]
    findings = verify(entries).findings
    assert "entry 3: expected seq 2" in findings
    assert "entry 3: prev_hash does not match entry 1" in findings


def test_a_reordered_chain_is_found() -> None:
    entries = chain()
    entries[1], entries[2] = entries[2], entries[1]
    assert not verify(entries).intact


def test_an_empty_chain_verifies() -> None:
    assert verify([]).intact


def test_a_fact_carries_no_text() -> None:
    with pytest.raises(ValueError):
        Fact.model_validate({"kind": "run.halted", "refs": {"run_id": "r"}, "reason": "free text"})
    with pytest.raises(ValueError):
        Fact(kind="run.halted", refs=LedgerRefs(run_id="r"), outcome="not a token!")


async def test_the_ledger_records_in_sequence_and_verifies() -> None:
    persistence = MemoryPersistence()
    ledger = ChainedLedger(MemoryLedgerStore(persistence), FakeClock())
    async with persistence.transaction("t"):
        await ledger.record("t", fact())
        await ledger.record(
            "t",
            Fact(
                kind="step.finished",
                refs=LedgerRefs(run_id="run_1", step_id="a", artifact_ids=("x",)),
                method=Method.WORKER,
                adapter="worker.http",
                consumption=Consumption(compute_seconds=1.5, resource_class="cpu.small"),
                outcome="succeeded",
            ),
        )
        await ledger.record("t", Fact(kind="run.created", refs=LedgerRefs(run_id="run_2")))
        entries = await ledger.entries("t")
        assert [e.seq for e in entries] == [1, 2, 3]
        assert [e.seq for e in await ledger.entries("t", "run_1")] == [1, 2]
        assert (await ledger.verify("t")).intact
    async with persistence.transaction("other"):
        assert list(await ledger.entries("other")) == [], "one chain per tenant"
