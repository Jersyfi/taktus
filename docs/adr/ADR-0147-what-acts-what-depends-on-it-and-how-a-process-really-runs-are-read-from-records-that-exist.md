# ADR-0147 — What acts, what depends on it, and how a process really runs are read from records that exist

**Status:** accepted · extends ADR-0021 (provenance), ADR-0022 (egress), ADR-0023 (a stop by a rule or a person), ADR-0029 (views own no figure), ADR-0030 (the removal test), ADR-0105 (projections of the ledger), ADR-0116 (residency) and ADR-0138 (a stop of an adapter) · issues #332, #333, #334; UC-7.8, UC-6.16, UC-9.7

## Context

The owner accepted three views in DEC-0190 (F4, F5, F6). Each answers a question no page
answers today:

- **What acts for us?** Every worker, connector and model that acts for a tenant, with how far
  it may act, what it produces, whether it is proven replaceable, where it processes, what it
  cost, and a stop for it (#332).
- **What depends on it?** What breaks and what only degrades if an adapter goes. Which steps a
  wrong result reached, and whether it left the system. Where data is processed (#333).
- **How does a process really run?** The path its runs took against the designed path, with
  fallbacks, retries and anchor halts, the waiting by cause, and proposals (#334).

Every fact these views need is recorded already, with two exceptions. The removal test's
verdicts and the maturity records are in the catalog component (ADR-0030, ADR-0044). The
configured adapters and what each serves are in the pools. The levels and exactness classes
are in the process versions. The residency rule is in governance, a model's location in its
configuration (ADR-0116). Consumption is on the ledger's `step.finished`. The provenance chain
names what each step read (ADR-0021). Egress entries name what left (ADR-0022). Blocks name
their cause (ADR-0043). A stop of an adapter exists (ADR-0138).

The two exceptions: the provenance store walks a chain only **backward**, from a result to
what it read. A wrong result needs it **forward**: to what read it. And a **retry** of a step
is not a ledger fact of its own; it is a second `step.admitted` after a `step.finished` that
failed. A fallback to a person is one: `step.awaiting` with outcome `fell_back` (ADR-0076).

## Decision

### 1. Three reads, one composition

The composition root joins the components in `composition/acting.py`, because the facts come
from the catalog, process, governance, run and identity components, which never import each
other. The reporting component owns the views: plain functions over plain facts in
`reporting/domain/service/acting.py` and `variants.py`. They store nothing.

### 2. The register

One row per configured worker, connector and model, keyed by its configuration identifier, never
by a product (ADR-0003). A row carries:

- its family and what it serves;
- its maturity, with what is missing (ADR-0044), and the last removal verdict with when it was
  taken;
- the processes that use it, each with the step, the level the step runs at, its exactness
  class, and whether the process breaks or degrades without the adapter;
- the highest level and the strongest exactness class among those uses;
- where it processes — a model's declared location, `undeclared` for the others — and whether
  that contradicts the tenant's residency rule;
- what it used over the last 28 days, from `step.finished`: steps, runs, tokens, compute
  seconds, and money by currency where the ledger records it;
- whether a stop of it is held.

A row **needs attention** when the removal test found it breaks a process, when it was never
removal-tested while a process uses it, when it processes outside the residency rule, when a
step above level 2 runs on it while it is not *verified*, or when a stop is held. Rows that
need attention come first, each with its reasons in words. No row and no figure names a person:
the identifiers are adapters', the counts are steps' and runs'.

**The stop.** `POST /register/{adapter}/stop` requests the stop of ADR-0138 for the adapter, by
the person, with no reason. The stop's rule then decides which runs halt, at their boundary, and
records it. The register adds no second kind of stop.

**The inventory.** `GET /register/inventory` writes the register in the shape a deployer's
inventory of AI systems asks for under the EU AI Act: per system its purpose (what it serves
and the processes that use it), the human oversight (the levels and the roles named at its
steps' fallbacks), where it processes, and its evidence (maturity, removal verdict). The
document says, in a field of its own, that it is generated from the configuration and **not
legally reviewed** (DEC-0029's rule for legal text).

### 3. Dependencies

- **Remove.** For one adapter: every process and step it serves, each marked *breaks* — no
  other adapter serves it and no fallback goes to a person — or *degrades* — another adapter or
  a person takes it, named. The verdict is the removal test's own rule
  (`catalog/domain/service/removal.step_finding`), applied to the configuration as it is now. The
  last removal verdict, with its date, stands beside it as evidence.
- **Wrong result.** For one step of one run: the records that read its result, forward,
  transitively, across runs and processes, each with its process, step and exactness class, and
  every egress entry of those runs that names one of their steps. The footer gives the counts of
  UC-4.11: what is affected, what was built on it, and what left the system. *Since when* is
  UC-4.11's window, which this view does not compute; it says so.
- **Residency.** Every adapter with where it processes, against the tenant's rule.

The provenance port gains `derived(tenant, run_id, step_id)`: the records whose inputs name the
step run, then every record whose inputs name one of those, in one query. The PostgreSQL
adapter reads it with a recursive query over the `inputs` document.

### 4. How a process really runs

**Two facts.** A retry is recorded as `step.retried`, outcome `after_failure`, in the
transaction of the `step.admitted` that admits a step again after it failed. A fallback to a
person stays `step.awaiting` with outcome `fell_back`.

**The projection.** `reporting.variants.v1` (ADR-0105) folds, per run, the process version, the
path of deviations in the order they happened — `fell_back`, `retried`, `anchored`,
`taken_over` at a step — whether it was a rehearsal, and how it ended. It reads only the kinds
it needs. A read takes the stored state and the entries since; it never reads the whole ledger.

**The view.** For one process: the designed path — its active version's steps in order — and
each variant with its share of the process's runs and up to five runs as examples; the share
of runs on the designed path; the waiting at each step by its cause, from the blocks of
ADR-0043; and proposals:

- a step that fell back to a person in at least a fifth of at least ten runs is proposed for a
  method change (ADR-0084);
- a step whose waits on a person make up at least two fifths of the process's waiting is
  proposed for a rule below a threshold.

A proposal is a sentence with its evidence. A person decides it through a change in dialogue
(UC-4.15); the view acts on nothing. There is no filter by person. A figure for a role is shown
only where at least two identities hold the role, as for response times (ADR-0015); otherwise it
says "too few to show".

### 5. The surfaces

`GET /register`, `GET /register/inventory`, `POST /register/{adapter}/stop`,
`GET /dependencies/remove/{adapter}`, `GET /dependencies/wrong-result/{run_id}/{step_id}`,
`GET /dependencies/residency`, `GET /processes/{process_id}/variants`. Each reads with an
account key or the web app's session. A process the reader may not see is left out, and a run
the reader may not see is answered as one that does not exist (ADR-0055 §5). The web app shows
each on a page of its own (DEC-0218).

## Alternatives

- **A store of actors.** Rejected: a second record of what the configuration already says would
  drift from it (ADR-0029, principle 1).
- **A dependency graph kept by hand, as a CMDB.** Rejected: it would be wrong as soon as a
  bundle or the configuration changed. The graph is derived on every read.
- **Variants from the whole ledger per request.** Rejected: #321 bounds every read on a hot
  path by what it returns.
- **A retry read from two `step.admitted` entries.** Rejected: every reader would have to repeat
  the pairing. A fact of its own is read once.
- **A stop of its own for the register.** Rejected: ADR-0138's stop already halts every run an
  adapter serves at its boundary and records it.

## Consequences

- `reporting/domain/service/acting.py`, `variants.py`, and their models.
- `composition/acting.py`, the HTTP routes in `adapters/driving/rest/acting.py`.
- `ProvenanceStore.derived`, in memory and in PostgreSQL.
- The ledger kind `step.retried`.
- `StaticModelPool.location`.
- The web app's pages `#/register`, `#/dependencies` and `#/variants/<process>`.

## Where this promise ends

- **No discovery.** The register lists what Taktus is configured with. A system outside Taktus is
  not found.
- **No agents or skills of their own yet.** An agent acts through its adapter, so it appears as
  its adapter. The skill hub (UC-14.3) and the agent hub (UC-8.7) are not built; their rows
  arrive with them.
- **No legal review.** The inventory is a draft generated from the configuration. It is never a
  compliance claim.
- **No error window.** The wrong-result view starts from one result. The window of UC-4.11 —
  since when, which other results of the same step — is UC-4.11's and not computed here.
- **No acting on the graph.** Neither view changes a process, an adapter or a run. The stop is
  ADR-0138's, requested by a person.
- **Retries before this record.** A retry recorded before `step.retried` existed is not counted
  as one.
- **No external event logs.** Variants are read from Taktus's own ledger only (UC-9.4 holds the
  rest).
