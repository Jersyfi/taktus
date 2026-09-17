"""What is particular to the in-memory adapters: the snapshot brings the state back, and the
object store is content-addressed. Everything an implementation of the persistence port must
do is in `persistence/`, run against this adapter and the database alike."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryRepository,
)
from taktus.shared.v1 import Artifact, LedgerEntry, LedgerRefs

AT = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
ZERO = "sha256:" + "0" * 64


async def test_a_committed_transaction_round_trips_through_the_snapshot(tmp_path: Path) -> None:
    first = MemoryPersistence(tmp_path)
    artifacts = MemoryRepository(first, Artifact)
    ledger = MemoryLedgerStore(first)
    artifact = Artifact(id="a", kind="report", digest=ZERO, created_at=AT)
    entry = LedgerEntry(
        seq=1, ts=AT, kind="run.created", prev_hash=None, hash=ZERO, refs=LedgerRefs(run_id="r")
    )
    async with first.transaction("t1"):
        await artifacts.put("t1", artifact)
        await artifacts.put("t1", artifact.model_copy(update={"title": "second write wins"}))
        await ledger.append("t1", entry)
    assert (tmp_path / "artifact.json").is_file() and (tmp_path / "ledger.json").is_file()

    second = MemoryPersistence(tmp_path)
    again = MemoryRepository(second, Artifact)
    async with second.transaction("t1"):
        stored = await again.get("t1", "a")
        assert stored is not None and stored.title == "second write wins"
        assert await again.get("t1", "nope") is None
        assert len(await again.list("t1")) == 1
        assert list(await MemoryLedgerStore(second).entries("t1")) == [entry]
        assert (await MemoryLedgerStore(second).entries("t1"))[0].document()["prev_hash"] is None
    async with second.transaction("t2"):
        assert await again.list("t2") == [], "another tenant sees nothing"


def test_the_ledger_store_has_no_way_to_change_an_entry() -> None:
    store = MemoryLedgerStore(MemoryPersistence())
    assert not hasattr(store, "remove") and not hasattr(store, "replace")


async def test_object_store_is_content_addressed(tmp_path: Path) -> None:
    store = MemoryObjectStore(tmp_path / "objects")
    digest = await store.put(b"hello")
    assert digest == "sha256:" + hashlib.sha256(b"hello").hexdigest()
    assert await store.get(digest) == b"hello"
    assert await MemoryObjectStore(tmp_path / "objects").get(digest) == b"hello", "read from disk"
    assert await store.get(ZERO) is None
