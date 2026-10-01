# DEC-0033 — The size of the database's volume

**Category:** NON-BLOCKING
**Raised in:** [#26](https://github.com/Jersyfi/taktus/pull/26), whose deployment plan names `database.size` without a value (`deploy/k8s/README.md` §2); answered in conversation and recorded in [#51](https://github.com/Jersyfi/taktus/pull/51)
**Issue:** none; the owner answered before a request was written, and this record is the request with its answer
**Needed by:** 2026-10-20
**Written after the answer:** the owner gave the size before a request was written; left out of the acceptance rate (DEC-0042).

## 1. What this is about

The database of the Taktus instance lives on a disk volume of a fixed size. On the owner's
integration server, the kind of storage the cluster offers cannot make a volume larger after it
was created. The record of every step Taktus runs only ever grows: nothing in it is deleted. The
size chosen now is therefore the size the instance lives with until someone moves the database
to a larger volume by hand.

## 2. Why you are being asked

Entry M3.10 of `docs/decisions/anchors.taktus.md`: "Raising or lowering a limit: a budget, a
quota, a compute bound". The volume is the bound on what the instance can keep.

## 3. What you must decide

What size the chart gives the database's volume by default.

## 4. What you need to know to decide

- **Effectively irreversible.** The storage class cannot expand a volume. A larger volume later
  means a migration: stop, copy, point the instance at the new volume, start.
- **Growth is not yet measured.** The first live run kept its state in memory. From this pull
  request on, the instance reports its growth per run and the date its volume will be full
  (ADR-0031), so the size can be checked against real numbers from the first day.

## 5. Options

### Option A — 20 Gi (recommended)

- **Meaning:** the chart's default `database.size` is 20 Gi.
- **Consequence:** room for a long time at the growth expected; a report long before it is tight.
- **Effort:** none.
- **Reversibility:** not reversible without a migration, as any size.
- **Why recommended:** the owner's choice, below.

### Option B — a smaller volume now, a migration when measured

- **Meaning:** start small and move once the growth per run is known.
- **Consequence:** a migration is planned from the start.
- **Effort:** the migration, later.
- **Reversibility:** not reversible without a migration.

## 6. What is blocked

The chart's default, which the deployment pull request writes.

## 7. How to answer

"DEC-0033: Option A." or "DEC-0033: Option B."

## Outcome

**Decided:** 2026-09-30
**Answer:** Option A, 20 Gi as the chart's default, given by the owner in conversation. Recorded
with it, as the owner asked: the target's storage class cannot expand a volume after creation
and the ledger only grows, so the choice is effectively irreversible; and the growth per run is
measured from the first day.
**Reasoning given:** none beyond the two facts recorded with the answer — the volume cannot be
enlarged later, and the ledger only grows.
**Recorded in:** [#51](https://github.com/Jersyfi/taktus/pull/51). `deploy/k8s/README.md` §2 sets `database.size: 20Gi` and derives
`TAKTUS_CAPACITY_DATABASE_VOLUME_MB` and `TAKTUS_CAPACITY_STORAGE_EXPANDABLE: false` from it;
the capacity report of ADR-0031 measures the growth per run from the first run and names the
date a person must act by.
