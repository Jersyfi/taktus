# ADR-0135 — The trace inside a step is kept outside the ledger for the tenant's retention, and shared by role

**Status:** accepted · extends ADR-0007 (the worker contract's events), ADR-0055 (live changes), ADR-0063 (the run level in the web app) and ADR-0029 (reporting owns views) · issue #409, DEC-0195 W8, UC-6.14

## Context

A worker reports what it does while it works a step. Its event stream carries the steps of its
own plan, its progress, every tool it called or refused, the choices it made and why, what it
used, what it produced, and how it ended (`contracts/worker/v1` §4). Until now the run read the
stream and kept only its effect: the consumption, the artifacts and the boundaries. Everything
else was read and dropped. A person who looked at a running worker step saw that it ran, not
what it did.

UC-6.14 asks for that record. It is the step's *trace*. Four things already hold that the trace
must not weaken:

- The ledger is content-free (ADR-0006). A worker's events carry the worker's own words, so the
  trace cannot be ledger entries.
- The stream of changes is read from the ledger (ADR-0055). It cannot carry the trace either.
- Who sees what is one predicate, `visibility.may_see`, asked by every path (ADR-0055 §5).
- No figure has a named person as its subject (principle 14, ADR-0015).

## Decision

### 1. The run keeps every event as a line of the step's trace

As the run reads a worker's stream, it keeps every event it has not read before as a *line*. A
line holds the run, the step, the assignment, the event's `seq`, the time the worker gave, the
type, and what the contract carries for the event beyond its envelope. It also holds when the
run read it. The line is written in a transaction of its own as the event arrives, before the
run acts on the event.

The trace is not the run's record. A line that cannot be written is lost, and the step goes on.

A stream read again after a crash brings events a second time. The store keeps one line per
event of an assignment and drops the repeat. Each line takes the step's next *position*: 1, 2,
3, across every assignment of the step. One runner writes a step at a time, because the run's
claim keeps any other out (#107), so no two lines of a step take the same position.

### 2. Every text is masked before it is kept

Every string in a line is masked before the line is written. Each secret value the instance
holds is replaced by `***`. The values are those its `TAKTUS_…_FILE` variables point at, the one
way a secret reaches an instance (CLAUDE.md §9). The owner's channel already refuses a message
that carries one (`KnownSecrets`). The contract forbids a worker to report a credential (W-08).
Masking makes the trace hold that even for a worker that breaks the rule.

A tool's arguments are a digest in the contract (W-09), and stay one.

### 3. The trace is read beside the run level, and asked for again

`GET /levels/runs/{run}/steps/{step}/trace?after=N` answers the lines after position `N`. Each
line comes with a sentence made from it: its text equivalent (UC-6.10). The answer says whether
the step is in flight (`open`), the last position read (`after`), the roles it is shared with,
and the link to it in the web app.

The web app reads the trace on the run's page. While the step is in flight, it asks again every
two seconds after the last line it holds. A line is therefore on the page within the five
seconds UC-6.14 allows: two seconds of waiting, plus the time one read takes. Once the step
ended, the page asks no more. It asks again when the run level shows the step running again.

The stream of changes stays as it is. It carries changes of state read from the ledger, and a
trace is neither.

### 4. Who sees a trace: the run's readers who hold the owner's role, or a role it is shared with

A trace is shown to a reader only where `visibility.may_see` lets them see its run. Beyond that,
the reader must hold the role `owner`, or a role the trace is shared with
(`visibility.may_see_trace`). A trace the reader may not see is answered as one that does not
exist, as a run is.

A reader who may see a trace shares it with a role. The share names the role and nothing else.
A role is a lowercase token, as the ledger records it. The surface refuses any other field, so
a person cannot be named as the receiver. A share never widens what the role sees of runs,
because the run's predicate is asked first. The ledger records `trace.shared` and
`trace.unshared` with the run, the step, the role as outcome, and the reader as actor.

The share answers with the link `app/#/runs/<run>/steps/<step>`. The link carries no key. A
browser that follows it signs in first (ADR-0119). The page opens only for an identity that may
see the trace.

The owner's role is the default reader because a decision is addressed to it when an anchor
names no other (NTC-0230).

### 5. The trace is kept for the tenant's retention, then erased

Each tenant has a *retention*: how many days a line is kept, from when the run read it. A tenant
that set none keeps lines for 30 days (NTC-0230). `taktusctl trace retention --days N` sets it,
between 1 day and 3650 days. The ledger records `trace.retention_configured` with who set it.

While the scheduler leads, it looks once an hour at every tenant it serves. It erases every line
recorded longer ago than the tenant's retention. An erasure that removed lines is the ledger
entry `trace.erased`, with outcome `retention`. A share of an erased trace stays: it is a role
and two identifiers, and opens nothing.

### 6. Where it is stored

Three tables (migration `0070`), each with the tenant and row-level security as every other:

- `step_trace`, one row per line;
- `step_trace_share`, one row per role a step's trace is shared with;
- `trace_retention`, one row per tenant that set its retention.

The port is `ports/traces.py`. Its adapters are a store over the database and one in memory. The
run writes lines through it. The reporting component reads them, and keeps the shares and the
retention (`StepTraces`).

## Alternatives

- **Lines as ledger entries.** Rejected: the ledger is content-free (ADR-0006). The research
  behind DEC-0195 asked this question and answered it the same way (§4, question 4).
- **The trace as one artifact per step in the object store, written at the end.** Rejected: an
  artifact is written once and addressed by its digest. A trace grows while it is read, and a
  person watching a running step would see nothing until it ended. The object store also keeps
  no tenant's retention.
- **The trace carried on the stream of changes.** Rejected: the stream is read from the ledger
  and carries nothing with content (ADR-0055). A second stream for the trace would need its own
  position, limits and resumption, to save at most two seconds over asking again.
- **Sharing by an open link with a token in it.** Rejected: whoever holds the link would read
  the trace with no identity, and nobody could say who did. UC-6.14 forbids it.
- **Every reader of the run sees its trace.** Rejected: the trace holds the worker's own words.
  The share by role would then grant nothing, and a person could not keep a trace narrower than
  its run.

## Consequences

- `RunEngine` takes `traces` and `masking`. Without both it keeps no trace, as before.
- `KnownSecrets` gains `mask`.
- `LedgerEntry` gains four kinds in its description: `trace.shared`, `trace.unshared`,
  `trace.retention_configured` and `trace.erased`.
- The memory persistence's transaction can remove an item when it commits. The trace store is
  the only one that does.
- The run's page in the web app is drawn by `RunPage` for both of its routes.

## Where this promise ends

It covers the events a worker reports over the worker contract, for steps of method `worker`,
and the trace a step a person took over keeps from before. A step on a model, a rule or a person
has no trace. A worker that reports little has a short trace. The trace shows what the worker
said, not whether it is true.

Masking replaces the secret values the instance holds, each at least eight characters long, as
written. A secret the instance never held is not known and not masked. Neither is a value split
across two events, or encoded otherwise.

A line is on the page within five seconds of being read from the worker, while the database and
the network answer as usual. A worker that buffers its events reports them late, and the bound
starts when they arrive.

The default reader is the role `owner`. A tenant cannot name another default yet. A share is
withdrawn per role; withdrawing it does not reach a copy a reader made.

Lines are erased at most an hour after their retention ended. A backup taken before that holds
them until the backup itself is gone (ADR-0087). Nothing here reaches into a backup.
