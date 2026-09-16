"""The in-memory adapters keep what they are given, and a snapshot brings it back."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryObjectStore, MemoryRepository
from taktus.shared.v1 import Artifact, LedgerEntry, LedgerRefs

AT = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
ZERO = "sha256:" + "0" * 64


async def test_repository_round_trips_through_its_snapshot(tmp_path: Path) -> None:
    snapshot = tmp_path / "artifacts.json"
    first = MemoryRepository(Artifact, key=lambda a: a.id, snapshot=snapshot)
    artifact = Artifact(id="a", kind="report", digest=ZERO, created_at=AT)
    await first.put(artifact)
    await first.put(artifact.model_copy(update={"title": "second write wins"}))
    second = MemoryRepository(Artifact, key=lambda a: a.id, snapshot=snapshot)
    stored = await second.get("a")
    assert stored is not None and stored.title == "second write wins"
    assert await second.get("nope") is None
    assert len(await second.list()) == 1


async def test_ledger_store_is_append_only_and_round_trips(tmp_path: Path) -> None:
    snapshot = tmp_path / "ledger.json"
    store = MemoryLedgerStore(snapshot)
    assert await store.last() is None
    entry = LedgerEntry(
        seq=1, ts=AT, kind="run.created", prev_hash=None, hash=ZERO, refs=LedgerRefs(run_id="r")
    )
    await store.append(entry)
    assert await store.last() == entry
    assert not hasattr(store, "remove") and not hasattr(store, "replace")
    again = MemoryLedgerStore(snapshot)
    assert await again.entries() == (entry,)
    assert (await again.entries())[0].document()["prev_hash"] is None


async def test_object_store_is_content_addressed(tmp_path: Path) -> None:
    store = MemoryObjectStore(tmp_path / "objects")
    digest = await store.put(b"hello")
    assert digest == "sha256:" + hashlib.sha256(b"hello").hexdigest()
    assert await store.get(digest) == b"hello"
    assert await MemoryObjectStore(tmp_path / "objects").get(digest) == b"hello", "read from disk"
    assert await store.get(ZERO) is None
