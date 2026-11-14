# ADR-0318 — The start page is one request, read from counts and open records

**Status:** accepted · DEC-0239 item 3 · complements ADR-0178 (the start page ordered by what
waits), ADR-0121 and ADR-0122 (what keeps the operation running, what governs the work) ·
revisits what ADR-0094 *Alternatives* rejected, and keeps the rejection

## Context
The start page of the web app asked 13 requests when it opened (analysis of 2026-11-14): the
stream's snapshot, the overview, the decision requests twice, the reports to the owner three
times, `/autonomy` twice, `/findings` twice and `/operation` twice. `/autonomy` read every run
of each process's active version to draw a level it did not show. Measured before this change on
a local PostgreSQL 16 with 2,000 runs of ten steps, one in twenty running: the snapshot took
0.92 s and sent 1.23 MB, each `/autonomy` 0.89 s; five readers opening the page at once waited
17.4 s, the event loop stalled for up to 0.52 s, and the process's resident memory peaked at
1,221 MB (`tests/integration/test_run_listing_at_scale.py`'s budget run against the release
before; the reader was not one of the owner's, so the owner's reads answered `403`).

The analysis proposed folding summaries on write as ledger projections (A2), which ADR-0094
rejected as "a second record of the same fact, and a write on every commit".

## Decision

### 1. `GET /levels/today` answers the start page and the frame
One request, with:

- `overview` — the answer of `GET /levels/overview`, unchanged;
- `counts` — what waits for the reader (decision requests addressed to them, open needs, open
  reports, alerts in effect), the runs that work now, the runs that wait on a person, the runs
  that failed in the last 24 hours, the open incidents, and the alerts in effect, or `null` for
  a reader who does not read the owner's reports;
- `waits` — §2;
- `marks` — what the navigation marks: the decision requests and how many are overdue, the
  open needs, how many processes run below their stated level and how many raises wait, the
  findings in review, and `GET /operation`'s summary unchanged.

Every part asks the predicate the request that reads it alone asks: a process or a run the
reader may not see is absent and not counted, and a reader who does not read the owner's
reports receives `readable: false` and no figure of them (ADR-0121). The routes it summarises
stay as they were.

### 2. What waits is one short list
At most five things, merged from the decision requests, the needs, the other open reports, the
failures of the last day and the alerts in effect. The urgent come first — a request or a report
past its date, an alert in effect — then the newest. Each carries its kind, a title of one line
of at most 120 characters, the route in the web app (`#/requests/…`, `#/reports/…`,
`#/runs/…`, `#/alerts`) and since when. A rule orders them
(`components/reporting/domain/service/today.py`); nothing names a person.

### 3. Read from counts and open records, not from history
- the overview as before: counts by version and state, the runs with a step running now
  (ADR-0094 §4);
- the runs by state: one `count` grouped by version and state;
- the failures: the ledger's entries of kind `run.escalated` of the last 24 hours, through the
  index by kind and time;
- the levels and corrections without reading a run (ADR-0319 §4);
- the findings in review only at the level `review`; at another level none waits, and nothing
  is read.

No projection is added. Every figure is one indexed query or a read of records that are open
by nature, so ADR-0094's reason against a second record still holds. A projection
(ADR-0105) is the step to take where a figure here comes to need history.

### 4. The answer is cheap to ask again
`GET /levels/today` carries an `ETag`, the digest of its body. A reader that sends it in
`If-None-Match` receives `304` with no body while nothing changed. A JSON answer above 1 KiB
is compressed where the reader accepts `gzip`; the stream of changes and files that are
compressed already never are. The web app's files under `_app/immutable/` are named by their
content's hash and are served with `Cache-Control: public, max-age=31536000, immutable`; the page
itself with `no-cache`.

## Measured
Same database, machine and seed as the Context, after the change
(`test_the_start_page_and_every_view_answer_within_the_budget_at_two_thousand_runs`):
`/levels/today` 0.07 s, the stream opened for its position 0.01 s, `/changes/recent` 0.01 s.
Five readers opening the start page at once, three requests each: 0.17 s, the longest stall of
the loop 0.005 s, the process's peak resident memory 249 MB.

## Alternatives
- **Fold the counts on write as ledger projections (A2).** Each count is one grouped query in
  milliseconds; a projection would be a second record and a write on every commit for it,
  ADR-0094's reason, which this ADR keeps.
- **Keep the separate requests and only remove the duplicates.** Seven requests remain, each
  with its own authentication and transaction; `/autonomy` still read every run.
- **Push the counts on the stream.** The stream carries changes of state and no figure
  (ADR-0055 §4).

## Consequences
- `GET /levels/today` joins the surface; `api/openapi.yaml` is regenerated.
- The `api` role compresses its JSON answers, and the web app's hashed files are cached.
- The web app reads its start page and its frame from one request (the design area's change).

## Where this promise ends
The figures are read when the request is answered; nothing is pushed. The decision requests,
the reports, the incidents and the alerts are read whole, as their own routes read them: they
grow with what people must answer, not with runs. A tenant whose closed incidents or filed
reports number in the tens of thousands makes this request slower in proportion; a projection
is then the next step. The failures counted are the runs that escalated in the last 24 hours as
the ledger records them, a rehearsal left out; a run that escalated and was resumed since still
counts. The `ETag` saves the bytes of an unchanged answer, not the reads behind it: the answer
is computed for every request. The measured times are one machine's; the budget a test holds
is ADR-0320's.
