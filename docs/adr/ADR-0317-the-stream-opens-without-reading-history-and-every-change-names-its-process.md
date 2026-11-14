# ADR-0317 — The stream opens without reading history, and every change names its process

**Status:** accepted · DEC-0239 item 3 ("no page waits for a full read of history") · amends
ADR-0055 §4 and §6 (the snapshot) and ADR-0094's *Where this promise ends* (the snapshot's read)
· changes `contracts/changes/v1` compatibly

## Context
The web app's first paint waits for the first event of `GET /changes`, the snapshot. Under
ADR-0055 §4 the snapshot listed every run of the scope. In the tenant scope that is every run
the tenant ever had. The analysis of 2026-11-14 measured the read behind it, `Records.state`,
on a local PostgreSQL 16 with ten-step runs: 48 ms at 100 runs, 331 ms at 1,000 and 1,021 ms at
3,000; the event at 3,000 runs is 1.17 MB. This session measured the same read again before the
change: 28 ms, 326 ms and 951 ms. The scope was applied after the read, in Python. The web app
then threw the runs away: it draws every level from its own request and reads it again on every
change.

A strip of what happened in the last minutes has no source either. A reader would have to keep
the stream open for an hour, or read the ledger whole.

## Decision

### 1. A snapshot lists a bounded set of runs, chosen where they are stored
- **tenant scope** — the runs that have not ended: the run component's `WORKING` and
  `WAITING`, every state but `finished`. A halted or an escalated run may still go on, and is
  listed.
- **process scope** — the runs of the process, any version.
- **run scope** — the run.

The repository's `newest` with a filter (ADR-0319 §1) chooses them in the database. A
snapshot lists at most `SNAPSHOT_RUNS` = 1,000 runs, the newest. Where the scope holds more, the
snapshot says `truncated: true`. The predicate of ADR-0055 §5 is asked of each listed run, as
before. The position and the runs are still read in one consistent transaction after the
stable head (ADR-0164).

### 2. A reader may ask for the position alone
`GET /changes?snapshot=position` opens with a snapshot that carries the position, `listed:
false` and no run. No run is read. A reader that draws from its own requests, as the web app
does, needs nothing more. `snapshot=runs` is the default and lists the runs of §1. A resume
after a long absence (ADR-0055 §6) answers in the mode the reader asked for.

### 3. Every change names the process and the version of its run
A change gains `process: {id, version}`. It is read from the run the change is paired with
before it is sent, which the stream reads anyway to apply the scope and the predicate. The
ledger entry's own references are not used for it: the run is the record of where it belongs.

### 4. The recent changes are one request
`GET /changes/recent?minutes=N` answers the changes of the last `N` minutes as one JSON
document, oldest first. `N` is at most 60, and 60 unless given. The scope parameters are the
stream's. Each change is projected, paired with its run and filtered by the same functions as
the stream's: the projection of ADR-0055 §4, the scope, and the predicate of §5. The read is
`LedgerStore.of_kinds_since` with a new bound `newest`: at most the newest
`RECENT_CHANGES` = 500 entries of the kinds that change a state, up to the stable head. The
answer says `complete: false` where the read reached that bound.

### 5. The contract changes compatibly
`contracts/changes/v1` gains `ProcessOf`, the optional `process` of a change, and the optional
`truncated` (only `true`) and `listed` (only `false`) of a snapshot. Every document the schema
accepted before it still accepts. `make gate-compat` classifies the change as compatible.

## Measured
On a local PostgreSQL 16, ten-step runs, one in twenty not ended, the release before and after
measured one after the other on the same machine (`bench.py` of the analysis, and the same seed
read through the new `Records.state`):

| Runs | Snapshot before (all runs) | Tenant scope after (runs not ended) | Position alone |
|---|---|---|---|
| 100 | 28 ms | 6 ms | 3 ms |
| 1,000 | 326 ms | 17 ms | 3 ms |
| 3,000 | 951 ms | 40 ms | 3 ms |

## Alternatives
- **Keep the full snapshot and page it.** A reader would page through every run to draw
  nothing from them.
- **Drop the snapshot.** ADR-0055 §6 needs a position to resume from, and a reader without a
  position has no other way to learn one.
- **List the finished runs of the last day as well.** The tenant scope would grow with the
  tenant's throughput again, and the start page draws its counts from `GET /levels/today`
  (ADR-0318).
- **Read the process from the ledger entry.** Not every entry names its process version; the
  run always does.

## Consequences
- `LiveRecords.state` takes the scope and a limit, and gains `recent`. `LiveChanges.open` and
  the hub's `open` take `listed`; both gain `recent`.
- `LedgerStore.of_kinds_since` gains the keyword `newest`. Both adapters implement it.
- `api/openapi.yaml` gains the query parameter `snapshot` and the path `/changes/recent`.
- A reader that drew the finished runs of the tenant from the snapshot draws them from
  `GET /runs` (ADR-0319) instead.

## Where this promise ends
The tenant scope's snapshot grows with the runs not yet ended, not with history. A tenant
whose escalated or halted runs are never resumed or cancelled keeps them listed; past 1,000 of
them the oldest are left out, and the snapshot says so. A process scope still grows with the
runs of the process, up to the same 1,000. The bound is on what is read and sent, not on time:
the measured times above are on one machine, and the budget a test holds is ADR-0320's.

The recent changes are those the stream would have sent. They are not a replay: a change the
reader may not see now is absent, even if they could see it then. More than 500 changes in the
window are cut to the newest 500, and `complete` says so; it says `false` also where exactly 500
were read. Entries above the stable head are left out until they are below it. A reader of an
older replica receives changes without `process`.
