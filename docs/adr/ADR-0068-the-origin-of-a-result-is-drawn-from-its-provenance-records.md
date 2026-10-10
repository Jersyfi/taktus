# ADR-0068 — The origin of a result is drawn from its provenance records, and the vocabulary gains the forms of a result, a source and a decision request

**Status:** accepted · builds the fourth level of UC-6.10, the origin of a result (issue #192,
DEC-0055); fills what ADR-0059 left to the level that draws these forms

## Context
UC-6.10's last level is *the origin of a result*: the path from a result back through the steps
and inputs that produced it. With it, the use case's first condition holds as a whole: for every
process version a reader may see there is an overview, a process graph, a run, and the origin of
a result.

The provenance chain records, for every completed step, what produced its result and from which
inputs, read when (ADR-0021). It is written once and never changed. A step reads three kinds of
input: an artifact or a result of an earlier step run, possibly in another run, or an external
source read through a capability.

ADR-0059 gave forms to steps and runs only. A decision request, a result and the origin of a
result gain theirs with the level that draws them. Two questions remain beside the forms:

1. **Which records make up the path**, and where it ends.
2. **What the reader may see** of a path that crosses runs.

## Decision

### 1. The path is the provenance records, followed back
`GET /levels/origins/{run_id}/{step_id}` draws the result of one step of one run. The path
starts at the newest provenance record of that step run. Every result or artifact input it read
leads to the record of the step run that produced it, in whichever run. The path follows those
records back until no input leads further. Every external source read is a leaf, with its
capability, its reference, its digest and when it was read.

Nothing is drawn that a record does not hold. Each step on the path shows its method kind and
exactness class, the model and the adapter where the record names them, and when it was
recorded. The result shows its exactness class, its digest and the artifacts it produced. A step
of kind `human` or `wait` produces no result (ADR-0018); asking for its origin is answered as
asking for a result that does not exist.

A past result is drawn as it was recorded. It is not replayed as motion (UC-6.10 §3), and nothing
on the path moves. The web app reads the level once, because a record never changes.

### 2. What the reader may not see ends the path
Every record on the path is asked of the predicate by its run (`may_see`). A record whose run
the reader may not see is absent. So is every record reached only through it: the path ends
there. When the result's own run is withheld, the level is answered `404`, alike with a result
that does not exist.

### 3. The forms of a result, a source and a decision request
The vocabulary gains three subjects, each with an outline no other element has:

- **a result** — outline `seal`, its exactness class as its mark, with `exact`'s mark kept for
  `exact` alone; one state, `recorded`;
- **a source** — outline `page`; one state, `read`;
- **a decision request** — outline `flag`; one form per status of the shared kernel: `open` (empty,
  a question mark), `answered` (partial, a dot), `interpreted` (partial, a quote), `confirmed`
  (partial, a check), `applied` (full, a check).

None of them moves: none is work. Each has a text with its name and its class or status. The
check holds a representation to these forms as it holds steps and runs.

### 4. Decision requests on the run level
A step that raised decision requests (ADR-0042) carries them at the run level, each with its
status as the decision component records it, its glyph and its text. No decider and no person is
named.

### 5. Each run level leads to the origin of its results
On the run level, every completed step that produced a result links to its origin. From the
origin, each step leads back to its run.

## Alternatives
- **Draw the origin of an artifact rather than of a step's result.** The provenance store can
  follow an artifact (`chain`), but a result without an artifact would have no origin. The
  step's record lists the artifacts it produced, and the level shows them.
- **Show a withheld step as a placeholder.** UC-6.10 says an element the reader may not see is
  absent, not greyed out and not counted.
- **Follow the stream on the origin page.** A record is written once; the only change a result
  can see is a newer run, which is another result.
- **Read each decision request's status from the stream's last change.** The status is the
  decision component's record; a reader who opened the page late would see none.

## Consequences
- The surface gains `GET /levels/origins/{run_id}/{step_id}`.
- `reporting` gains the origin level, its port method and its query, and the three forms in the
  vocabulary. The composition root reads the run's provenance store and the decision component's
  requests for the levels.
- ADR-0059 is amended: its *Where this promise ends* no longer says that only steps and runs have
  a form.
- The web app gains `#/origins/<run>/<step>`; the run level draws decision requests and links
  each result to its origin.
- The web app's fixtures gain an origin, and a decision request on the run level.

## Where this promise ends
The path is as complete as the provenance records are. A step that read something without
recording it as an input shows no edge to it. A record is the newest of its step run, so a step
retried shows the attempt that produced the result. The path follows the inputs a record names,
and does not look inside a worker or a connector: it ends where Taktus handed the work over, and
shows what came back (UC-6.10 §3). A source is shown as it was read, with its digest; whether the
source has changed since is not checked here, and is the correction anchor's (ADR-0022). Until
UC-6.4 the predicate is the tenant boundary, so a path never crosses into another tenant, and
inside one tenant nothing is withheld. A decision request's status is read when the run level is
read; one decided since shows its new status at the next change of the run.
