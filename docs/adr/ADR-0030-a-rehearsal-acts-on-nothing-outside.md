# ADR-0030 — A rehearsal acts on nothing outside; a removal verdict says what it was taken under

**Status:** accepted

## Context
The removal test (ADR-0003, ADR-0027) withholds one integration and runs the processes that
use it twice, once with the integration and once without. Its first run with real processes,
on 2026-09-23, ran none of them (`docs/runs/first-run.md` §6). Every real process of the
repository writes outward — a comment, a branch, a pull request — and running a process twice
to test an adapter must not write twice to a real repository. The exercise therefore fell
back to resolution: which adapter would serve each step without the integration. The half of
the test that actually runs a process had never run against a real process.

Every connector operation already declares whether its effect leaves Taktus: the effect field,
`read`, `write` or `delivery` (ADR-0024 §3). What was missing is a way to run a process
without acting on that declaration.

The same run showed two faults in the verdicts themselves (issue #36). An integration that no
registered process uses was reported as *changed*, the verdict for "removing it changes
quality or cost and breaks nothing". Nothing was exercised, so nothing was learned, and the
verdict still counted towards the adapter's maturity. And no verdict said which adapter stood
behind the identifier it names. `worker.endpoint` served the reference worker that day, which
serves none of the capabilities of the implementation step. With the coding worker behind the
same identifier the verdict would have been another one.

## Decision

### 1. A run can be a rehearsal
A run carries `rehearsal`, false by default, set when the run is started and persisted with
it. In a rehearsal run the engine never sends a connector call whose operation is declared
outward. The step answers instead with a **recording**: the stored result of the most recent
real call of the same operation through the same adapter in the same tenant. A real call is a
successful step run of a run that is not a rehearsal. A recording is therefore never taken
from a rehearsal run. The stored result is the document the connector answered — output,
effect, consumption — and the rehearsed step keeps it, together with the run and step it came
from.

Everything else in a rehearsal runs as it does in any run. A read through a connector is a
real read, because a read does not leave the system. Rules, waits, llm steps and worker steps
run unchanged.

### 2. A rehearsal is marked wherever it is recorded
Every ledger entry of a rehearsal run carries `rehearsal: true` (`contracts/shared/v1/
LedgerEntry.json`), so that no entry of a rehearsal can be read as an entry of a real run. The
rehearsed step finishes with outcome `rehearsed`, not `succeeded`. No egress entry is written
for it, because nothing left the system. The correction anchor's predicate (ADR-0022 §4)
ignores an egress entry that carries the mark, although a rehearsal writes none. The step's
provenance record names the recording as what it read: the recorded run's result, by run,
step and digest. A rehearsed step consumes nothing, because nothing was called.

Without a recording the outward step fails, with a reason that names the operation and the
adapter. The run escalates at that boundary, as a run without an adapter does (ADR-0027).

### 3. The removal test rehearses
Both runs of an exercised process — with the integration and without it — are rehearsals. A
process is rehearsed only when three things hold. Every outward connector operation it would
call has a recording, through the adapter that serves it with the integration and through the
one that serves it without. No worker step's frame allows hosts: what a worker sends to a host
is not a connector operation, and nothing can answer for it. Every input has an example. When
one of these fails, the verdict rests on resolution alone, and the finding says which, for
example `not run: no recorded response for <operation> through <adapter> — it has never been
called for real on this instance`.

### 4. A fourth verdict: untested
An integration that no registered process uses is **untested**: there was nothing to
exercise. It is not *changed*. It does not count as the removal half of the adapter's
maturity, and the maturity record says why. The verdicts are now *broke*, *changed*,
*untested* and *exception*.

### 5. A verdict names its configuration
The removal result carries `configuration`: the adapter identifier that served the
integration, what it declared — a worker's or a connector's capabilities, a model's purposes, a
connector's operations — and the version it declared, where it declares one. The result is the
document whose digest the `removal.tested` entry carries, and the one the maturity record
keeps, so both name the configuration.

## Alternatives
- **Declare a process safe to run by hand.** A flag on the bundle saying "this process may be
  run twice". It shifts the judgement to the author, and every real process of this repository
  would carry `false`.
- **Point the rehearsal at a sandbox copy of the target system.** It needs a second account per
  connector and a copy that behaves like the original. It is the right test of a connector, and
  that test is the conformance suite, not the removal test.
- **A fake adapter per connector for rehearsals.** It would rehearse the fake, not the process
  as it runs. A recording is what the real adapter answered.
- **Overload *exception* for "nothing uses it".** *Exception* means the integration cannot be
  removed by design. An integration nobody uses can be removed; nobody has shown what happens.

## Consequences
- The run carries `rehearsal`; PostgreSQL gains `run.rehearsal` and `ledger_entry.rehearsal`
  (migration 0008). The ledger field is optional: entries written before carry none, and their
  hashes are unchanged.
- The run component gains a query for recordings (`application/query/recordings.py`) and a
  pure rule that chooses one (`domain/service/rehearsal.py`). The removal test asks the query
  before it rehearses, so that a process without recordings is resolved, not run into a failure.
- A process can be rehearsed only after it has run for real on the instance. On a new instance
  the first removal test resolves every outward process, and says so.

## Where this promise ends
A rehearsal acts on nothing outside through a connector operation declared outward. The promise
rests on the declaration: an operation declared `read` that writes is called in a rehearsal, as
in any run, and that is the connector's contract broken, not the rehearsal's. A worker step
runs in a rehearsal as in any run. The removal test does not rehearse a process with a worker
whose frame allows hosts, but the engine does not refuse one in a run someone else starts as a
rehearsal. A model call is not an outward connector operation and runs as it does. A recording
is what the target answered once. It is not what the target would answer now, so a rehearsal
shows where a process comes to with that answer, not that the answer is still right. The
configuration a verdict names is what the adapter declared. An adapter that declares a
capability it cannot serve is recorded as serving it. The recording lookup reads every run of
the tenant; it is a scan, and it will need an index when the number of runs makes it slow.
