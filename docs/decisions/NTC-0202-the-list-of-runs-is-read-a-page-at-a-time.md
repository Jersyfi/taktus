# NTC-0202 — The list of runs is read a page at a time

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-12
**Raised in:** the pull request for issue #310

## 1. What was decided

`GET /runs` used to answer every run of the reader's tenant in one answer. It now answers a
page. ADR-0094 is the decision; this notice records the change of behaviour.

1. **A page holds at most `limit` runs.** `limit` is 100 unless the request gives it, and at
   most 500. A request with a `limit` outside 1 to 500 is answered `422`.
2. **The order is the order of before.** Newest first; runs created at the same moment in
   ascending id.
3. **`next` leads to the next page.** It is present when more runs follow. The reader passes it
   back as `after`. A value of `after` this surface did not hand out is answered `422`.
4. **A page may hold fewer runs than `limit`.** The visibility predicate is asked of each run on
   the page, as before; a run it withholds is left out, and `next` still leads on.
5. **Each run is the same document as before.** A tenant with at most 100 runs receives exactly
   the answer it received before: the same runs, in the same order, and no `next`.

The overview and the process level read the same records by query instead of reading every run
(ADR-0094 §4); what they answer is unchanged.

## 2. The evidence

- Issue #310 and `docs/research/2026-10-12-devops-review.md` §E4: with 2 000 runs, `GET /runs`
  took 56.9 s and blocked the event loop for 56 s.
- `tests/integration/test_run_listing_at_scale.py`, 2 000 runs of ten steps each, on this
  change's machine. Before the change: `GET /runs` 45 to 53 s with a stall of the same length,
  the overview 45.0 s with a stall of 44.7 s. After: the first page 0.06 s, the overview 0.01 s,
  the largest page of 500 runs 0.28 s, the whole list through the repository 0.95 s; no stall
  over 0.14 s. Every page read in turn returns every run exactly once, newest first.
- `tests/adapters/rest/test_reads.py`: pages of two lead through five runs in order, and the
  pages joined are the single answer; a `limit` of 0 or 501 and a foreign `after` are `422`.
- `tests/adapters/persistence/test_queries.py`, on both adapters: a page holds the same
  documents as the whole list, in the same order.

## 3. What was considered

- **No default limit**, a page only when the request asks. Every reader that does not know of
  pages would still read every run, which is the fault #310 names. Not taken.
- **A default of 50, or of 1 000.** 50 would split a small tenant's list for no gain. A page of
  1 000 stalled the loop for 0.31 s on this machine, too close to the 0.5 s bound on a slower
  one. 100 answers in a twentieth of a second; 500 stays a sixth of the bound. Taken: 100 and
  500.
- **An offset instead of a cursor.** A run created between two pages would shift the next page:
  one run twice or one missed. Not taken.

## 4. Which entry permits it

M2.4 of `docs/decisions/anchors.taktus.md`: "A change of what the software does, made inside an
agreed scope, that breaks no contract, moves no limit or autonomy level and says nothing
public." The scope is issue #310, under DEC-0187. The HTTP surface (`api/openapi.yaml`) is
generated and is no contract under `contracts/`, and no release has shipped it. The page size is
not a limit in the sense of M3.10, which names a run's budget, quota, compute bound and safety
margin. No level moves, and nothing public is said. The amendment of ADR-0067 is M1.9.
