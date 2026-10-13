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


async def test_the_object_cache_stays_bounded_and_every_object_stays_readable(
    tmp_path: Path,
) -> None:
    """#311: with a directory, memory holds at most the configured bytes however many objects
    pass through, and every object is read back by its digest from the directory."""
    size, limit = 64 * 1024, 256 * 1024
    store = MemoryObjectStore(tmp_path / "objects", cache_bytes=limit)
    written = {await store.put(bytes([i]) * size): bytes([i]) * size for i in range(40)}
    assert store.cached_bytes <= limit, "writing more than the limit"
    for digest, content in written.items():
        assert await store.get(digest) == content
        assert store.cached_bytes <= limit, "reading more than the limit"
    restarted = MemoryObjectStore(tmp_path / "objects", cache_bytes=limit)
    for digest, content in written.items():
        assert await restarted.get(digest) == content, "read from disk after a restart"
    assert restarted.cached_bytes <= limit

    none = MemoryObjectStore(tmp_path / "objects", cache_bytes=0)
    for digest, content in written.items():
        assert await none.get(digest) == content
    assert none.cached_bytes == 0, "a cache of 0 keeps nothing"

    larger = MemoryObjectStore(tmp_path / "objects", cache_bytes=size - 1)
    assert await larger.get(next(iter(written))) is not None
    assert larger.cached_bytes == 0, "an object larger than the cache is never cached"


async def test_the_object_cache_evicts_the_least_recently_used(tmp_path: Path) -> None:
    store = MemoryObjectStore(tmp_path / "objects", cache_bytes=2)
    a, b = await store.put(b"a"), await store.put(b"b")
    assert await store.get(a) == b"a"  # a is now the most recently used
    c = await store.put(b"c")  # b leaves
    (tmp_path / "objects" / b.removeprefix("sha256:")).unlink()
    assert await store.get(b) is None, "b was evicted, so its deleted file is the only copy"
    (tmp_path / "objects" / a.removeprefix("sha256:")).unlink()
    assert await store.get(a) == b"a" and await store.get(c) == b"c"


async def test_without_a_directory_every_object_is_kept() -> None:
    store = MemoryObjectStore(cache_bytes=0)
    digest = await store.put(b"only here")
    assert await store.get(digest) == b"only here"


async def test_the_snapshot_size_is_the_state_size(tmp_path: Path) -> None:
    """The `StateSize` port over the development store: nothing on disk without a snapshot,
    and the snapshot files' size with one, growing as entries are committed."""
    assert await MemoryPersistence().state_bytes() is None
    memory = MemoryPersistence(tmp_path)
    assert await memory.state_bytes() == 0
    ledger = MemoryLedgerStore(memory)
    entry = LedgerEntry(
        seq=1, ts=AT, kind="run.created", prev_hash=None, hash=ZERO, refs=LedgerRefs(run_id="r")
    )
    async with memory.transaction("t1"):
        await ledger.append("t1", entry)
    size = await memory.state_bytes()
    assert size is not None and size == (tmp_path / "ledger.json").stat().st_size > 0
