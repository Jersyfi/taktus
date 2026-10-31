"""The chains: how an entry is hashed, linked and verified, and how the run chains are anchored
in the tenant's chain. Pure functions, no I/O (ADR-0006, ADR-0164)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import NamedTuple

from taktus.ports.ledger import Fact, Verification
from taktus.shared.v1 import Digest, LedgerEntry

TENANT_CHAIN = ""
"""The name of the tenant's own chain. Every other chain is named by its run's identifier."""

ANCHORED = "ledger.anchored"
"""The kind of the entry that anchors the heads of the run chains in the tenant's chain."""


def canonical(document: dict[str, object]) -> bytes:
    """The bytes that are hashed: keys sorted, no whitespace, UTF-8, `hash` left out."""
    without_hash = {key: value for key, value in document.items() if key != "hash"}
    return json.dumps(
        without_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def hash_of(entry: LedgerEntry) -> Digest:
    return "sha256:" + hashlib.sha256(canonical(entry.document())).hexdigest()


def chain_of(entry: LedgerEntry) -> str:
    """The chain an entry belongs to: its run's, unless it references no run or says it is on
    the tenant's chain. An entry written before ADR-0164 carries no `chain_seq` and belongs to
    the tenant's chain, whatever it references."""
    return entry.chain_name()


def position(entry: LedgerEntry) -> int:
    """The entry's place in its chain. An entry written before ADR-0164 has its sequence number
    there: the tenant's chain was the only one, and gapless."""
    return entry.seq if entry.chain_seq is None else entry.chain_seq


def chain_for(fact: Fact, *, tenant_chain: bool = False) -> str:
    """The chain an entry for this fact goes on."""
    if tenant_chain or fact.refs.run_id is None:
        return TENANT_CHAIN
    return fact.refs.run_id


def link(
    previous: LedgerEntry | None,
    fact: Fact,
    at: datetime,
    *,
    seq: int | None = None,
    tenant_chain: bool = False,
) -> LedgerEntry:
    """The next entry of a chain for this fact, after `previous`, the newest entry of the same
    chain (None for the first). `seq` is the reading position the store allocated; without it,
    the one after `previous`'s, which is what a test of one chain needs. With `tenant_chain`, a
    fact that references a run is put on the tenant's chain all the same."""
    at_seq = seq if seq is not None else (1 if previous is None else previous.seq + 1)
    unhashed = LedgerEntry(
        seq=at_seq,
        ts=at,
        prev_hash=None if previous is None else previous.hash,
        hash="sha256:" + "0" * 64,  # replaced below; the hash covers everything but itself
        chain_seq=1 if previous is None else position(previous) + 1,
        chain="tenant" if tenant_chain and fact.refs.run_id is not None else None,
        **fact.document(),
    )
    return unhashed.model_copy(update={"hash": hash_of(unhashed)})


class Link(NamedTuple):
    """Where a chain stands: the place and hash of its newest entry walked."""

    seq: int
    hash: Digest


class Head(NamedTuple):
    """A run chain's newest entry at an anchor's bound: a leaf of the anchor's tree."""

    chain: str
    position: int
    hash: Digest


def leaf(head: Head) -> Digest:
    # The head's hash is written as `digest`: the canonical form leaves out a key `hash`.
    document: dict[str, object] = {
        "chain": head.chain,
        "chain_seq": head.position,
        "digest": head.hash,
    }
    return "sha256:" + hashlib.sha256(canonical(document)).hexdigest()


def merkle_root(heads: Iterable[Head]) -> Digest | None:
    """The root of the tree over the heads, ordered by chain: each leaf the hash of its head,
    each node the hash of its two children's digests written one after the other, an odd node
    carried up unchanged. None when there is no head."""
    level = [leaf(h) for h in sorted(heads, key=lambda h: h.chain)]
    if not level:
        return None
    while len(level) > 1:
        paired = [
            "sha256:" + hashlib.sha256((level[i] + level[i + 1]).encode("ascii")).hexdigest()
            for i in range(0, len(level) - 1, 2)
        ]
        if len(level) % 2:
            paired.append(level[-1])
        level = paired
    return level[0]


@dataclass
class Walk:
    """A walk of a tenant's entries in sequence order, every chain at once.

    It checks, entry by entry: sequence numbers rise; each entry follows the newest one of its
    chain by place and by `prev_hash`; its hash matches its content; no entry of the rule
    before ADR-0164 follows one of the rule after it. The predecessors of chains it meets in the
    middle are seeded first (`needs`, `seed`). An anchor it meets is kept in `anchors` with the
    bound before it, so that the caller compares it with the heads it covers."""

    reached: int = 0
    """The sequence number of the newest entry walked; where the walk starts."""
    counted: int = 0
    """How many entries lie at or before `reached`."""
    anchored: int = 0
    """The bound of the newest anchor walked: where the next anchor's heads begin."""
    chains: dict[str, Link] = field(default_factory=dict)
    ruled: bool = False
    """Whether an entry of ADR-0164's rule was walked."""
    findings: list[str] = field(default_factory=list)
    anchors: list[tuple[LedgerEntry, int]] = field(default_factory=list)
    seqs: dict[str, int] = field(default_factory=dict)
    """The sequence number of each chain's newest entry walked, for the findings to name."""

    def needs(self, entries: Sequence[LedgerEntry]) -> set[tuple[str, int]]:
        """The predecessors this batch links to that the walk has not seen: (chain, place)."""
        seen: set[str] = set(self.chains)
        wanted: set[tuple[str, int]] = set()
        for entry in entries:
            chain = chain_of(entry)
            if chain not in seen and position(entry) > 1:
                wanted.add((chain, position(entry) - 1))
            seen.add(chain)
        return wanted

    def seed(self, chain: str, found: LedgerEntry | None) -> None:
        if found is not None:
            self.chains[chain] = Link(position(found), found.hash)
            self.seqs[chain] = found.seq

    def step(self, entries: Sequence[LedgerEntry]) -> None:
        for entry in entries:
            self._one(entry)

    def _one(self, entry: LedgerEntry) -> None:
        if entry.seq <= self.reached:
            self.findings.append(f"entry {entry.seq}: sequence number does not rise")
        if entry.chain_seq is None:
            if self.ruled:
                self.findings.append(f"entry {entry.seq}: written by the rule before ADR-0164")
        else:
            self.ruled = True
        chain = chain_of(entry)
        previous = self.chains.get(chain)
        expected = 1 if previous is None else previous.seq + 1
        if position(entry) != expected:
            self.findings.append(f"entry {entry.seq}: expected place {expected} in its chain")
        if entry.prev_hash != (None if previous is None else previous.hash):
            before = self.seqs.get(chain)
            named = "its predecessor" if before is None else f"entry {before}"
            self.findings.append(f"entry {entry.seq}: prev_hash does not match {named}")
        if hash_of(entry) != entry.hash:
            self.findings.append(f"entry {entry.seq}: hash does not match its content")
        if entry.kind == ANCHORED and chain == TENANT_CHAIN:
            through = entry.through
            if through is None or through < self.anchored or through >= entry.seq:
                self.findings.append(f"entry {entry.seq}: an anchor without a bound before it")
            else:
                self.anchors.append((entry, self.anchored))
                self.anchored = through
        self.chains[chain] = Link(position(entry), entry.hash)
        self.seqs[chain] = entry.seq
        self.reached = max(self.reached, entry.seq)
        self.counted += 1


def walk(entries: Sequence[LedgerEntry], previous: Link | None) -> tuple[list[str], Link | None]:
    """Walk entries of one chain that follow `previous` (None: from its first entry). The
    findings name sequence numbers; the link is to the last entry walked."""
    if not entries:
        return [], previous
    chain = chain_of(entries[0])
    w = Walk(chains={} if previous is None else {chain: previous})
    w.step(entries)
    return w.findings, w.chains.get(chain_of(entries[-1]))


def verify(entries: Sequence[LedgerEntry]) -> Verification:
    """Walk every chain from its first entry: what a list of entries alone can show, the
    anchors' heads left out. Every finding names the sequence number."""
    w = Walk()
    w.step(entries)
    return Verification(entries=len(entries), intact=not w.findings, findings=tuple(w.findings))
