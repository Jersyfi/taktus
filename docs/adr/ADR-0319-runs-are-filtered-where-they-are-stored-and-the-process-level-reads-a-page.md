# ADR-0319 — Runs are filtered where they are stored, and the process level reads a page

**Status:** accepted · DEC-0239 item 3 · amends ADR-0094 §1 and §3 (a filter on `newest` and
`count`, filters on `GET /runs`) and ADR-0064 (the runs the process level lists)

## Context
ADR-0094 made `GET /runs` read a page, and the overview count. Three readers still read every
run of a version or a tenant:

- **the process level** read every run of its version (`having(process_version)`) to list them
  all. Measured before this change at 2,000 runs of one version: 0.90 s and 1.02 MB;
- **`GET /autonomy`** read the process level of every process to show a level that does not
  depend on any run: 0.89 s for one process at 2,000 runs;
- **a Runs page** had no way to ask for the runs in one state or of one process, short of
  reading every page.

## Decision

### 1. `newest` and `count` take a filter
`Queried.newest` and `Queried.count` take `where`: per field of one value, the values it may
hold. A run is admitted where every named field holds one of its values; an empty set admits
none. The database answers it with `IN` on the run's own columns, and refuses any other field
with `NotQueryable`, as `count` does. The memory adapter filters the documents. The repository
suite holds the two equal.

Migration 0112 adds the index `run_version_created` (tenant, process version, creation time,
id): the order the process level and a filter by process read in. It adds nothing the previous
release reads or writes (ADR-0093 §1).

### 2. `GET /runs` filters by state and process
`state` (repeatable) keeps the runs in one of the states named; `process` keeps the runs of
one process, any version. Both are applied where the runs are stored, and a cursor keeps its
place within them. `cursor` is accepted as a second name of `after`; one request gives one of
the two. A state the run does not know is `422`.

### 3. The process level lists the runs not ended and a page of the ended
The process level of a version lists every run not yet ended — the run component's `WORKING`
and `WAITING`, at most 500, the newest — then the newest `limit` runs that ended (20 unless
asked, at most 100), and `next` where more ended runs follow. `after` (the `next` of the page
before) answers the next page of ended runs alone. `counts` gives every run of the version by
state, counted where they are stored and only where `may_count` admits the version; the
level's sentence counts runs from it. The runs not yet ended come first, then the ended, each
group newest first.

### 4. A reader of the level alone reads no run
`LevelQueries.process` takes the page to read; `None` reads no run and no count. `/autonomy`
and `/levels/today` ask it so: the level, its statement and its versions need none. The
figures that count a version's runs read the counts, and their consumption figure pages back
through the ended runs only as far as its period reaches.

## Measured
At 2,000 runs, one in twenty running, same machine before and after
(`tests/integration/test_run_listing_at_scale.py`): the process level 0.90 s and 1.02 MB before,
0.08 s and 65 KB after; `/autonomy` 0.89 s before, 0.07 s after; `GET /runs?state=running`
0.07 s. The process level's read alone (`bench.py`, one in twenty runs not ended): 46, 338 and
909 ms at 100, 1,000 and 3,000 runs before; 17, 29 and 54 ms after.

## Alternatives
- **A run-specific query per need.** The port knows no component (ADR-0003); a general filter
  serves the process level, the Runs page and the stream's snapshot (ADR-0317) alike.
- **Page the process level by offset.** A run that ends between two pages would shift every
  later page (ADR-0094 *Alternatives*).
- **Drop the runs from the process level.** Its graph draws which step runs in which run now,
  and a reader of a process asks for its recent runs; the page keeps both.

## Consequences
- The persistence port's `Queried` gains `Where`; both adapters implement it.
- `LevelRecords.process` takes a `RunPage`; `ProcessFacts` gains `counts` and the last run of
  the page; `ProcessLevel` gains `counts`, and the surface hands out `next`.
- `GET /runs` gains `state`, `process` and `cursor`; `GET /levels/processes/{id}` gains `limit`
  and `after`. `api/openapi.yaml` is regenerated, and the web app's fixtures with it.

## Where this promise ends
A filter names fields the run row holds as columns of one value; a field of a step run is not
filterable. A filter by process reads the versions runs were created for with one grouped
count, which grows with the versions of the tenant, not with its runs. The process level lists
at most 500 runs not yet ended; past that, the oldest of them are not listed, and `counts`
still counts them. A cursor is not a snapshot (ADR-0094): a run that ends after the first page
was read appears on no later page of ended runs. `may_count` is the tenant boundary until UC-6.4
tells the runs of one version apart (ADR-0094); `counts` is withheld whole where it says no. The
memory adapter answers by reading every document; the bounds are not promised for it.
