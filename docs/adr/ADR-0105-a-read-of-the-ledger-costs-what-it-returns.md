# ADR-0105 — A read of the ledger costs what it returns

**Status:** accepted · amends ADR-0006: a projection derived from the ledger is allowed · issue #321

## Context

The ledger is a tenant's one chain of entries (ADR-0006). Every metric is computed from it. Until
now, every reader read the whole chain and kept what it needed.

Four of those readers are on a hot path. A *hot path* is a read that happens on every run, every
request or every tick of the scheduler:

- the calibration at every run start, resume and claim (ADR-0005 §4);
- `GET /runs/{id}/ledger`, which also verified the whole chain;
- `BlockedTime`, which the product finding reads (ADR-0043, ADR-0046);
- the interface sweep, every 60 s (ADR-0047).

On 2026-10-12, with 500 000 entries in one tenant, a run start took 23.6 s and the ledger route
26.2 s. The process held 2.5 GB. The index `ledger_entry_run` existed and was never used
(`docs/research/2026-10-12-devops-review.md` §L2).

## Decision

1. **A read names what it needs.** The entries of one run are read through the index
   `ledger_entry_run`. The entries of some kinds are read through the index `ledger_entry_kind`,
   by kind and sequence number. Neither read touches another run's or another kind's entries.
2. **A projection is allowed.** A *projection* is a value computed from the ledger and stored
   beside it. It records the sequence number of the last entry it read. A reader brings it up to
   date by reading only the entries after that number, and stores the result again. The
   projection's definition names the kinds of entry it reads, how it starts and how one entry
   changes it.
3. **The ledger stays the one source.** A projection is never written from anything but ledger
   entries. It can be rebuilt from the ledger at any time, and the rebuilt value equals the
   stored one. A test rebuilds every projection and compares. A projection whose rule changes
   gets a new name, and starts again from the first entry.
4. **The calibration is a projection.** It keeps, for each adapter, method and step, the last
   observations the calibration uses (`WINDOW`, twenty), and the estimates still waiting for
   their step to finish. The factors it gives equal the factors computed from every observation.
5. **The activity of runs is a projection.** It keeps, per process and day, which runs had an
   entry. The blocked-time sums read it for the share of the work a block held up.
6. **A chain is verified from its last verified checkpoint.** A *checkpoint* is the sequence
   number and hash of the newest entry a verification found intact. A verification walks the
   entries after it, links the first of them to its hash, and moves the checkpoint when it finds
   nothing. A verification that finds a fault leaves the checkpoint where it was.
7. **A full verification stays an explicit act.** It walks the chain from the first entry and
   trusts no checkpoint (`taktusctl ledger verify --full`). When it finds a fault, the checkpoint
   goes back to the start. Every later verification then walks the whole chain again and reports
   the fault again.
8. **Writing a projection never waits.** Two readers may bring one projection up to date at
   once. Each holds a correct value for the sequence number it read to. Only the one that takes
   the projection's claim stores its value; the other returns its own and stores nothing.

## Alternatives

- **Maintain each projection when an entry is recorded.** Every write would pay for every
  reader, inside the transaction that holds the chain. A reader that brings its projection up to
  date pays only for the entries since its last read.
- **A materialised view in the database.** It is refreshed as a whole, and it exists only where
  the database does. The development store would compute a different way.
- **Archive the old part of the ledger.** It makes the chain shorter, not the reads cheaper, and
  it deletes what the ledger promises to keep (issue #321, boundary).
- **Cache the whole chain in the process.** The memory grows with the history, which is the
  fault this decision removes.

## Consequences

- A run start reads the calibration and the entries since its last read. Its cost no longer
  grows with the tenant's history.
- `GET /runs/{id}/ledger` reads the run's own entries and the entries after the checkpoint. The
  answer says where the walk started, as `chain.checkpoint`.
- The table `ledger_projection` holds every projection and the checkpoint, one row per tenant
  and name. It is derived, so a backup without it loses nothing the ledger cannot give back.
- The first read after this change, and the first read of a new projection, walks the whole
  ledger once.

## Where this promise ends

A projection is as current as its last reader. The first read after a long pause pays for every
entry since. A verification from the checkpoint does not see a change to an entry before the
checkpoint, and it trusts the checkpoint's row. Only a full verification finds either, and it
costs what the whole chain costs. The reads that still walk the whole ledger — the Takt rate,
the measures, the quality history of a raise, and the registration of a version — are not on a
hot path and are not covered here (#522). The chain's shape is unchanged (#341). Nothing of the ledger
is deleted or archived.
