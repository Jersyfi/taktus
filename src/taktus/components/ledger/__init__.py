"""Owns the hash chain, its verification, and later its export (ADR-0006).

An entry references what happened — identifiers, method, adapter, measured consumption, an
outcome token, the digest of the content produced — and stores nothing else. Entries are
chained: each carries the hash of the one before it and its own hash over everything but that
hash field. Altering any field of any entry breaks the chain from there on, and `verify` says
where.

**The hash rule.** The entry is written as a JSON document the way `LedgerEntry.json` reads
it — absent optional fields left out, `prev_hash` written as null on the first entry — without
the `hash` field, then serialised canonically: keys sorted, no whitespace, non-ASCII kept as
is, encoded as UTF-8. The hash is `sha256:` followed by the SHA-256 of those bytes in lowercase
hex. Anyone with the entries and this paragraph can recompute the chain; no key and no secret is
involved, which is the point.

Verification walks the sequence numbers, the links and the hashes. It does not judge the
timestamps: they are part of what is hashed, so an altered one is found, but their order across
several instances is a matter of clocks, not of the chain.
"""
