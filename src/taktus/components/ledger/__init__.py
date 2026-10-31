"""Owns the hash chains, their verification, and later their export (ADR-0006, ADR-0164).

An entry references what happened — identifiers, method, adapter, measured consumption, an
outcome token, the digest of the content produced — and stores nothing else. Entries are
chained: each carries the hash of the one before it in its chain and its own hash over
everything but that hash field. Altering any field of any entry breaks its chain from there on,
and `verify` says where.

**The chains.** Each run has a chain of its own: the entries whose `refs.run_id` names it. The
tenant's chain holds every other entry, every entry marked `chain: "tenant"`, and the anchors.
An entry's `chain_seq` is its place in its chain, from 1 and without gaps; its `prev_hash` is
the hash of the entry before it there, null for a chain's first. Its `seq` is the tenant's
reading position: unique, rising, with gaps. An entry written before ADR-0164 has no
`chain_seq`: it belongs to the tenant's chain, at the place of its `seq`, and the tenant's
chain continues from it.

**The hash rule.** The entry is written as a JSON document the way `LedgerEntry.json` reads
it — absent optional fields left out, `prev_hash` written as null on a chain's first entry —
without the `hash` field, then serialised canonically: keys sorted, no whitespace, non-ASCII
kept as is, encoded as UTF-8. The hash is `sha256:` followed by the SHA-256 of those bytes in
lowercase hex. It covers `seq` and `chain_seq` with everything else. Anyone with the entries and
this paragraph can recompute every chain; no key and no secret is involved, which is the point.

**The anchors.** An entry `ledger.anchored` on the tenant's chain covers the run chains up to
its `through`. For every run chain with an entry above the previous anchor's `through` and at
or below its own, the newest such entry is a head. Each head's leaf is the hash, by the rule
above, of `{"chain": <run>, "chain_seq": <place>, "digest": <its hash>}`. The leaves are ordered
by run; each node is the SHA-256 of its two children's digests written one after the other, as
`sha256:<hex>`; an odd node is carried up unchanged. The root is the anchor's `content_digest`.

Verification walks the reading positions, every chain's places and links, the hashes, and every
anchor against the heads it covers. It does not judge the timestamps: they are part of what is
hashed, so an altered one is found, but their order across several instances is a matter of
clocks, not of the chains.
"""
