# ADR-0164 — Each run has its own chain, anchored in the tenant's chain

**Status:** accepted · amends ADR-0006 (what a link is), ADR-0020 §4 (one chain per tenant), ADR-0055 (the order of commit) and ADR-0105 §6 (the checkpoint) · issue #341

## Context

A tenant's ledger was one hash chain (ADR-0006, ADR-0020 §4). Each entry carried the next
sequence number of the tenant and the hash of the tenant's newest entry. Two transactions could
therefore not append at once. The store took a claim on the tenant's chain at the first entry a
transaction recorded, and held it until the transaction ended.

On 2026-10-12 this was measured with 2 ms of work in each transaction
(`docs/research/2026-10-12-devops-review.md` §L1). One tenant topped out at about 200 commits
per second, however many writers it had. One tenant per writer reached 1 020 with eight
writers. A step takes about three commits, so the ceiling is 60 to 70 steps per second for a
whole corporation in one tenant. Splitting the tenant is no way out: a corporation's processes
cross its departments.

Three readers rely on the tenant's order, and any change must keep them correct.

- **Provenance** stores the sequence number of a step's entry, inside the transaction that
  recorded it (ADR-0021). The number must be known when the entry is recorded.
- **The readers that keep their place** — a projection, the checkpoint of the verification
  (ADR-0105), a stream of changes (ADR-0055) — read the entries after a number. They rely on
  an entry never committing below one they have read.
- **The admission of a run under a cap on open work** records `open_work.admitted` and reads
  the runs in flight again under the tenant's claim (ADR-0132). The claim is what keeps two
  admissions from passing the cap together.

UC-6.1 requires that altering, removing or reordering entries is found by verification.

Four terms are used below. A **chain** is a sequence of entries in which each carries the hash
of the one before it. An entry's **place** is its position in its chain. Its **reading
position** is its `seq`, the order a reader reads the tenant's entries in. An entry is
**final** when it is committed, or when the transaction that would have committed it has ended.

## Decision

### 1. Each run has its own chain

An entry that references a run goes on its run's chain. Every other entry goes on the tenant's
chain. So does an entry recorded `in_order` (§5), and the anchors (§4). The entry's `chain_seq`
is its place, from 1 and without gaps. Its `prev_hash` is the hash of the entry before it in the
same chain. The first entry of a chain has none.

Writing a chain still needs a claim on it. The store claims a run's chain under a key of its own
(namespace `RUN_CHAIN`), and the tenant's chain under the tenant's key, as before. Two
transactions that write different chains do not wait for each other.

### 2. The hash rule

The rule of `src/taktus/components/ledger/__init__.py` is unchanged in form. The entry is
written as JSON without its `hash`, keys sorted, no whitespace, UTF-8, and hashed with SHA-256.
The hash covers `seq`, `chain_seq`, `prev_hash` and every other field. What changed is what
`prev_hash` points to: the entry before it in its chain, not in the tenant.

An entry written before this decision has no `chain_seq`. It belongs to the tenant's chain, and
its place is its `seq`. The tenant's chain continues from it: the first entry written after
it takes the next place. No stored entry is rewritten, and every existing chain verifies as it
did.

### 3. Reading positions are handed out without waiting

`seq` stays the tenant's reading position. It is unique in the tenant and rises in the order the
store handed it out. It may have gaps, where a transaction rolled back. The database adapter
takes it from one sequence, `ledger_entry_seq`, without waiting for any other writer. The
number is known when the entry is recorded, so provenance keeps it.

A position may now commit after a higher one. A reader that keeps its place therefore reads only
up to the **stable head**: the newest entry at or below which every entry is final.

The database adapter finds it without waiting. A transaction that takes its first position for a
tenant first holds a **marker**. The marker is a shared advisory lock whose key carries the
tenant and a bound below every position the transaction will hold: the sequence's value as read
before it takes the position. A reader reads the newest committed entry first. It then reads
the markers of the other open transactions from the lock table. The stable head is the newest
entry at or below both. A transaction whose position lies below the first read was open when it
was read. It is then either still open, and its marker bounds the head, or committed, and the
second read sees it.

A transaction that reads one snapshot throughout cannot ask for the stable head: what commits
after its snapshot stays invisible to it. The adapter refuses it. The stream of changes reads
the head in a transaction of its own and then its snapshot.

A projection is stored up to the stable head. The value a reader receives also folds every entry
committed beyond it. The memory adapter keeps the positions gapless and in the order of commit;
there, the stable head is the newest entry.

### 4. The run chains are anchored in the tenant's chain

While it leads, the scheduler anchors every tenant's run chains once a minute. An **anchor** is
an entry `ledger.anchored` on the tenant's chain. Its `through` is the stable head when it was
made. Its `content_digest` is the root of a tree over the **heads**: for every run chain with
an entry above the previous anchor's `through` and at or below its own, the newest such entry.

The tree is a Merkle tree, so that one run's head can later be shown to be in an anchor without
the other heads. A leaf is the hash of `{"chain", "chain_seq", "digest"}` of a head — its chain, its place
and its hash — written in the canonical form of §2. The key is `digest`, because the canonical
form leaves out a key named `hash`. The leaves are ordered by chain. A node is the hash of its two children's
digests written one after the other. An odd node is carried up unchanged. No anchor is written
when no run chain moved.

### 5. An admission is recorded in order

`Ledger.record` takes `in_order`. Such an entry goes on the tenant's chain whatever it
references, and carries `chain: "tenant"`. Its claim orders the transactions that record in
order: each runs after every earlier one and before every later one. Reads in the same
transaction see every entry the earlier ones committed. `open_work.admitted` is recorded so,
and ADR-0132's check of the runs in flight holds as it did.

### 6. Verification walks every chain at once

A verification walks the tenant's entries in reading order, from its checkpoint. It finds:

- a reading position that does not rise;
- an entry that does not take the next place of its chain, or whose `prev_hash` is not the
  hash of the entry before it there;
- an entry whose hash does not match its content;
- an entry of the rule before this decision after one of the rule after it;
- an anchor whose root differs from the root of the heads it covers, read again from the store.

The checkpoint stays where ADR-0105 §6 put it, at the newest entry walked. It also keeps how
many entries lie at or before it and the bound of the newest anchor walked. A chain whose
predecessor lies before the checkpoint is linked to it by one read of that entry.

### 7. The ledger is partitioned by time

`ledger_entry` is partitioned by month of `ts` (migration 0091). The table as it was becomes
its first partition, without a row copied or moved. The scheduler makes the months ahead on
the same tick as the anchors. A default partition catches an entry no month covers. The
append-only trigger stands on every partition; each partition refuses a truncate.

Archiving an old partition means detaching it and keeping it. It is never dropped. This
decision makes archiving possible; it does not archive. The operation and where a verification
starts after an archived month are left to the change that archives.

## Alternatives

- **One chain per tenant, with the claim taken at the end of the transaction.** The claim would
  last only for the insert and the commit. Provenance needs the number when the entry is
  recorded, and the commit's flush to disk would still be serialised.
- **Positions assigned by a sequencer after commit.** Order of commit and no gaps, kept by
  one process. An entry would not be readable, not even by its own transaction, until the
  sequencer had run. Provenance could not name it.
- **The stable head from transaction identifiers alone.** A transaction's identifier is taken
  at its first write, not at its first position, so the two orders differ. A reader could not
  tell from them which positions are still open.
- **Wait in the reader for the open writers to end.** A reader inside a writing transaction
  would wait for a writer that waits for its claim.
- **Several tenants for a corporation.** Its processes cross its departments (Context).

## Consequences

- With eight writers in one tenant, the commits per second are at least four times one
  writer's. A test measures it (`tests/adapters/persistence/test_ledger_throughput.py`, marker
  `timing`).
- `LedgerEntry` gains `chain_seq`, `chain` and `through`, all optional; `ledger.anchored` is a
  new kind. The ledger store port gains `allocate`, `in_chain` and `heads`; `last` names a chain,
  and `after` takes a bound.
- Migration 0091 names itself as the oldest build it serves. A build before it would chain every
  entry to the tenant's newest and interleave with the run chains (ADR-0093 §1).
- The stream of changes (ADR-0055) and every projection read up to the stable head. A
  snapshot of the stream may show a change it then sends again; a change sets a state, so it
  changes nothing twice.
- A checkpoint stored before this decision keeps its meaning: it stood on a gapless chain, so
  its number is its count.

## Where this promise ends

- **A rewrite is found only against what was taken before it.** A rewrite of a run's chain with
  every hash recomputed is found against the anchor that covers its head. It is not found when
  the anchors after it are rewritten too, and the tenant's chain from there. That is ADR-0006's
  bound, now one level up: a copy of an anchor taken earlier is what finds it.
- **The newest entries are not yet anchored.** An entry above the newest anchor's `through` is
  covered by its chain's links only. Removing the newest entries of a run's chain, or a whole run
  chain written since the last anchor, is not found until an anchor covers them, and not at all if
  they are removed first. The scheduler anchors once a minute while it leads; an instance
  without a scheduler anchors nothing.
- **The order between two runs is the reading order, not the order of commit.** Within a chain
  the order is proven. Between two chains, a reader learns the order in which positions were
  handed out.
- **The stable head waits for the slowest open writer.** A transaction that recorded and stays
  open holds the head below its first position. Readers do not wait for it, but they do not move
  past it either. A stream's 5 seconds (ADR-0055 §7) hold while no writing transaction stays open
  longer.
- **The marker's key holds 40 bits of position and 23 of tenant key.** A ledger handed out more
  than about 10^12 positions, or a registry past about 8 million tenants, needs a wider key.
- **The throughput figure is a measurement on one machine**, with 10 ms of work in each
  transaction and the database on the same host. With 2 ms, a host of four cores is bound by its
  processors before the ledger (3.7 times one writer on the CI runner, 8.3 times on a larger
  machine), so the test waits 10 ms, as a step's call to the outside does. It says that the tenant no longer serialises
  its writers. It is not a capacity promise for a given deployment.
- **The tenant's own chain still serialises** what references no run and what is recorded in
  order. Only the run chains write side by side.
