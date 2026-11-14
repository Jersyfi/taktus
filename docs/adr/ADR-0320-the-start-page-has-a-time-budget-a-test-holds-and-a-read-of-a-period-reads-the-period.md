# ADR-0320 — The start page has a time budget a test holds, and a read of a period reads the period

**Status:** accepted · DEC-0239 item 3 · extends ADR-0094's bounds to the start page and the
views; DoD point 11 (a suite too slow to be useful is a finding)

## Context
ADR-0094's test held `GET /runs` and the overview at 2,000 runs. The start page asked twelve
more requests that no test measured, and two of them grew with every run the tenant ever had
(ADR-0317, ADR-0318). The analysis of 2026-11-14 found more readers that read every run, or
read one record at a time, on paths a person waits for:

- the runner, before it admits a step held to a budget, read every run of the tenant to sum
  the costs of the current month (`_over_tenant_budget`) or of a limit's period (`_unit_costs`,
  also inside the transaction that claims the limit), and the demand estimate of a run read
  them all for its last 28 days;
- the signals read the provenance of each measured run in its own query, and each result from
  the object store in turn, inside the transaction;
- `GET /findings` read what would leave twice, and each record of a block from the object
  store in turn;
- a session or an account key was looked for in every tenant served, in a transaction each,
  on every request;
- the chart gave the `api` role a memory limit of 512 MiB; five full reads at once measured a
  peak of 816 MB at 3,000 runs (`bench3.py` of the analysis, rerun before this change).

## Decision

### 1. A test holds the start page and the views to a budget
`tests/integration/test_run_listing_at_scale.py` seeds 2,000 runs of ten steps, one in twenty
running, with their process registered, and asks a served `api` role:

- each request of the start page (`/levels/today`, `/changes?snapshot=position` to its first
  event, `/changes/recent`) and of the views' first reads (`/levels/overview`, `/changes` to its
  first event, `/runs`, `/runs?state=running`, `/levels/processes/{id}`, `/autonomy`,
  `/operation`) on its own: each under 1 s;
- the start page of five readers at once, fifteen requests: all under 3 s;
- the event loop never stalls over 0.5 s meanwhile.

It is marked `timing` and runs in CI's lane `timing`, in one process. It prints every time, the
size of every answer and the process's peak resident memory.

### 2. A rule over a period reads the period
The runner's budget checks, its demand estimate and its recheck under the claim read the
tenant's runs newest first a page of 500 at a time, until a page reaches before the period:
the month's first day less one, or the limit's start or the 28 days before today less one,
whichever is earlier. The rule over them is unchanged and filters as before; only runs it
skipped anyway are no longer read. A repository that cannot be queried still answers with every
run.

### 3. Records are read together
- The signals read the provenance of every measured run in one query (`ProvenanceStore.of_runs`)
  in the transaction, and the results from the object store after it, 32 at a time.
- `GET /findings` reads what would leave once and chooses what waits for a review from it. The
  records of the blocks are fetched 32 at a time, and a block once read is kept: a digest names
  one content forever.
- The directory remembers in which tenant a key's or a session's digest was last found and
  looks there first. Whether it still proves an identity is read every time.

### 4. The `api` role has the memory its peak needs
The chart's `api` role requests 384 MiB and is limited to 1 GiB; the `small` profile, which runs
every role in one process, is limited to 1 GiB (NTC-0288).

## Measured
Same machine and seed, the release before and after (§1's test; the release before measured by
the same requests where they existed):

| | Before | After |
|---|---|---|
| start page, one reader | 13 requests; the snapshot 0.92 s, `/autonomy` 0.89 s twice | 3 requests; 0.07 s, 0.01 s, 0.01 s |
| start page, five readers at once | 17.4 s, loop stalled 0.52 s | 0.17 s, loop stalled 0.005 s |
| process level | 0.90 s, 1.02 MB | 0.08 s, 65 KB |
| peak resident memory of the process | 1,221 MB | 249 MB |

## Alternatives
- **Bound wall-clock time in every test.** Most tests prove behaviour; a time bound belongs
  where a promise names one (`timing`, `pyproject.toml`).
- **A budget at 20,000 runs in CI.** Seeding and the lane's time grow tenfold; 2,000 is ADR-0094's
  size and the bounds above hold with room. The analysis' figures at larger sizes are its own.
- **Cache the costs of a month.** A second record of what the runs hold (ADR-0094, ADR-0318);
  reading the period is enough.

## Consequences
- `ProvenanceStore` gains `of_runs`; both adapters implement it.
- The runner reads `newest` where its repository offers it.
- The chart's defaults change; an operator who set their own keeps them.

## Where this promise ends
The budget holds at 2,000 runs of ten steps on the test's own database, on the machine that runs
the lane; a slower machine may need the same headroom the bounds leave (the measured times are
a tenth of them). It holds for an identity that is not the owner's reader: the owner's reports,
alerts and findings are read whole, and a tenant with many of them is not measured here. It
does not hold for every view: the figures of a process's consumption, the bottlenecks, the
subjects, the case spend, the proposals, the recordings and the measures still read every run
of the tenant, each in time proportional to the runs, with the loop turning meanwhile; a
tenant's whole export does so by design. The runner's budget checks read the runs of the period,
which grow with the tenant's throughput, not its history. The memory default holds the peak
measured here and in the analysis, not an unbounded number of concurrent full reads.
