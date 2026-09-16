"""The chain: how an entry is hashed, linked and verified. Pure functions, no I/O."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime

from taktus.ports.ledger import Fact, Verification
from taktus.shared.v1 import Digest, LedgerEntry


def canonical(document: dict[str, object]) -> bytes:
    """The bytes that are hashed: keys sorted, no whitespace, UTF-8, `hash` left out."""
    without_hash = {key: value for key, value in document.items() if key != "hash"}
    return json.dumps(
        without_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def hash_of(entry: LedgerEntry) -> Digest:
    return "sha256:" + hashlib.sha256(canonical(entry.document())).hexdigest()


def link(previous: LedgerEntry | None, fact: Fact, at: datetime) -> LedgerEntry:
    """The next entry of the chain for this fact, after `previous` (None for the first)."""
    seq = 1 if previous is None else previous.seq + 1
    prev_hash = None if previous is None else previous.hash
    unhashed = LedgerEntry(
        seq=seq,
        ts=at,
        prev_hash=prev_hash,
        hash="sha256:" + "0" * 64,  # replaced below; the hash covers everything but itself
        **fact.document(),
    )
    return unhashed.model_copy(update={"hash": hash_of(unhashed)})


def verify(entries: Sequence[LedgerEntry]) -> Verification:
    """Walk the chain from the first entry. Every finding names the sequence number."""
    findings: list[str] = []
    previous: LedgerEntry | None = None
    for entry in entries:
        expected_seq = 1 if previous is None else previous.seq + 1
        if entry.seq != expected_seq:
            findings.append(f"entry {entry.seq}: expected seq {expected_seq}")
        expected_prev = None if previous is None else previous.hash
        if entry.prev_hash != expected_prev:
            findings.append(f"entry {entry.seq}: prev_hash does not match entry {expected_seq - 1}")
        if hash_of(entry) != entry.hash:
            findings.append(f"entry {entry.seq}: hash does not match its content")
        previous = entry
    return Verification(entries=len(entries), intact=not findings, findings=tuple(findings))
