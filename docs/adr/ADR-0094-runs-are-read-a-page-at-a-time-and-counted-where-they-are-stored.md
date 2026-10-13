# ADR-0094 — Runs are read a page at a time, and counted where they are stored

**Status:** accepted · from DEC-0187 (finding E4), issue #310 · amends ADR-0067 §2 and its promise

## Context
The review of 2026-10-12 (`docs/research/2026-10-12-devops-review.md`, E4) measured the list of
runs. With 2 000 runs, `GET /runs` took 56.9 s, and the event loop was blocked for 56 s. With
`TAKTUS_ROLES=all`, the HTTP surface and the runner share that loop, and the runner renews its
lease on it. The lease is 60 s.

Three causes were found:

- **The list was quadratic.** The run mapper read every child row of the tenant and then, for
  each run, filtered all of them again in Python: runs times children.
- **`GET /runs` had no page.** Every request read every run of the tenant, however many.
- **The overview read every run to count them.** It answers a few hundred bytes. To do so it
  loaded every run with every step, and finished runs count for nothing on it.

The work was also all on the loop. Building and validating thousands of documents is processor
work, and while it lasts the loop serves nothing else.

## Decision

### 1. A repository can be queried, not only listed
The persistence port gains `Queried[T]`, a repository with three queries. A field is named by its
key in the aggregate's document; `a.b` names the field `b` of every element of the list `a`.

- **`newest`** — at most `limit` aggregates, newest first by `created_at`, ties in ascending
  `id`, after a `Mark` when one is given. A `Mark` is the creation time and the id of the last
  aggregate a reader received.
- **`count`** — how many aggregates hold each combination of values of the named fields,
  counted where they are stored. No aggregate is read.
- **`having`** — the aggregates whose field holds a value, or a list with an element whose
  field does.

The database adapter answers for the fields its tables hold as columns, and refuses any other
with `NotQueryable`. The run's queryable fields are its own columns of one value, and the step
run's `step_id`, `index`, `method`, `state` and `adapter`. The in-memory adapter answers every
field by reading every document: the same answers, not in the same time. The repository suite
holds the two equal.

### 2. The list is linear, and its assembly leaves the loop
The run mapper reads each child table once and groups the rows in one pass. A page reads the
children of its own runs only. Assembling the documents, and validating more than 50 of them,
runs in a thread. The loop goes on serving, and renewing leases, meanwhile.

### 3. `GET /runs` answers a page
`GET /runs` reads at most `limit` runs: 100 unless the request says, at most 500. Its order is
the order of before: newest first, runs created at the same moment in ascending id. When more
follow, the answer carries `next`, an opaque cursor; the reader passes it back as `after`. A
cursor this surface did not hand out is answered `422`.

The visibility predicate (ADR-0055 §5) is asked of every run on the page. A page may therefore
hold fewer runs than `limit`, and `next` still leads on. Each run on a page is the same document
as before.

### 4. The overview counts by query
The overview reads the runs of each process version counted by state, with `count`. Whether a
state works or waits stays the run component's own definition, `WORKING` and `WAITING` (ADR-0067
§2). It reads one by one only the runs with a step running now, with `having`, because each such
step is drawn and leads down to its run. A version whose runs have all ended counts zero of each,
and its process is still listed, as before.

A count cannot ask the visibility predicate about each run in it. `reporting` therefore gains a
second function beside `may_see`: `may_count`, asked once for the runs of one version. It must
never say yes where `may_see` would say no for a run among them; a test holds that. The process
level reads the runs of its version with `having` as well.

### 5. Two indexes
Migration 0052 adds `run_created` (tenant, creation time, id), the order a page reads in, and
`step_run_state` (tenant, state), how the overview finds the steps running now. They add nothing
the previous release reads or writes (ADR-0093 §1).

## Alternatives
- **Keep the list and only group in one pass.** It makes the list linear: 2 000 runs in about
  1 s. A tenant that keeps growing makes every request longer still, without bound.
- **A summary of counts kept by the run component**, updated on every state change. It would
  answer the overview without a query. It is a second record of the same fact, and a write on
  every commit, for a figure one `GROUP BY` returns in milliseconds.
- **Paginate by offset.** A run created between two pages shifts every later page by one. A
  reader would see a run twice, or miss one.
- **One run-specific port.** The port knows no component (ADR-0003). The three queries are
  general, and the run is the first aggregate to need them.

## Consequences
- The persistence port gains `Queried`, `Mark` and `NotQueryable`; both adapters implement them.
- `GET /runs` gains `limit`, `after` and `next`; `api/openapi.yaml` is regenerated.
- `reporting` gains `RunCount`, `CountedRuns` and `may_count`. `OverviewFacts` carries counts
  and the runs with a step running now, instead of every run.
- `tests/integration/test_run_listing_at_scale.py` holds the bounds at 2 000 runs of ten steps
  each.

## Where this promise ends
The bounds are measured at 2 000 runs of ten steps each, with one artifact and one checkpoint per
step, on a database of the test's own: `GET /runs` under 2 s, the overview under 2 s, and no
stall of the loop over 0.5 s. A page is bounded by its `limit`, not by the tenant's size. The
overview's counts are one query over all of a tenant's runs; that query grows with the tenant,
though far more slowly than reading them did. A reader of the whole list, such as the snapshot of
the stream of changes, still reads every run. It does so in time proportional to their number,
and the loop turns meanwhile, but its answer has no bound.

A cursor is not a snapshot. A run created after the first page is read appears on no later page.
A run's creation time is set once, so no run moves from one page to another. A run deleted
between two pages is missing from them. Two runs created at the same moment are told apart by their id,
in the database's collation.

`may_count` answers for the runs of one version together. Until UC-6.4 it is the tenant boundary,
like `may_see`. A view of UC-6.4 that tells the runs of one version apart has to change it, or a
count would show what `may_see` hides. The memory adapter answers every query by reading every
document; it is for development and tests, and the bounds are not promised for it.
