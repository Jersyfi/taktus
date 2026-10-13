# ADR-0095 — A run reserves the numbers of the records its change adds, through the connector

**Status:** accepted · issues #382 and #281 · builds on ADR-0017 §5 (amendment of 2026-10-13) and ADR-0024

## Context
Since 2026-10-13 a record of the register — a decision, a notice, a needs request — carries a
number reserved on the repository before it is written (DEC-0189 rule 6, ADR-0017 §5). A
reservation is the reference `refs/register/<PREFIX>-<NNNN>` on the remote. The host creates a
reference once, so of two writers that try the same number exactly one gets it. The pipeline's
register check fails a record a branch adds whose number is not reserved.

A session reserves with `make reserve`, which pushes the reference with `git`. P-03 cannot. Its
coding worker writes the change in a workspace without the right to push, and the run writes
the branch through the repository connector, as Taktus's own app. Neither reserved. A change P-03
made that added a record therefore failed its pipeline until a person reserved the number. In
the live run of #74, the coding agent also took a number `main` already held, and replaced that
number's row of the register's index (#281). The index is generated since; the number is what
remains.

## Decision

### 1. The connector creates references
The reference connector gains `repository.refs.create`, in a capability of its own,
`repository.refs`. It takes up to ten fully qualified names, `refs/<namespace>/<name>`, and a
`target`, a branch or a commit. Each reference points at a commit of its own: a child of the
target with the target's tree, which changes nothing. That commit's message carries the
idempotency key as a trailer, as a branch's commit does. A repeat finds each reference by its
name and the key at it, and replays. A reference that exists without the key is somebody
else's, and the call ends in `conflict` naming it. The connector knows no namespace: what a
reference means is the caller's. No contract changes; an operation is the connector's own
declaration (`contracts/connector/v1` §3).

### 2. A rule extracts what a pattern names
The run gains a rule kind, `extract`. It takes a list of texts, or of entries with a `path` or
a `name`, a regular expression with named groups, and a text composed from those groups. Its
result is every distinct composed text of `values` that `excluding` does not compose too. It is
deterministic, and admissible for `exact`. It names nothing of any project.

### 3. P-03 reserves before it writes the branch
P-03, version 8, reads the records `main` holds, in the register's directory and in its
directory of open records, after the worker's change. The step `record-references` extracts,
from the paths the changeset writes, the reference of every record whose identifier `main` does
not hold. The step `reserve-records` creates those references through the connector, before
`create-branch`. A change without a new record skips it. A number somebody else holds is a
conflict that names the reference, and the run stops before anything is written. The person
the step falls back to renumbers, or runs the issue again. The register's pattern and namespace
are in the bundle, the project's own blueprint: the product holds none of them (ADR-0092).

The worker's task says where the next free number comes from: one above the highest that a
record on the base or a reservation holds, the reservations listed by
`git ls-remote origin 'refs/register/*'`. It says that the workspace does not reserve, and that
no row of the index is written.

## Alternatives
- **The worker renumbers to a free number.** It sees the base it cloned, and the reservations
  when it lists them, but not what is reserved between that moment and the branch. Only an
  atomic creation decides who holds a number.
- **A placeholder renamed on merge.** ADR-0017 §5 rejected it: `main` accepts a change only
  through a pull request, and a placeholder cannot be named before it merges.
- **An operation that reserves register numbers.** It would put the project's namespace and
  its record format into the product's connector, which ADR-0092 forbids.
- **One reference per call, from a loop in the process.** A process has no loop; a list in one
  call keeps one step and one idempotency key per reservation set.
- **Renumber and retry inside the run on a conflict.** The changeset is fixed once the worker
  ends; renumbering means changing files and every mention of the number, which is the
  worker's or a person's work, not a rule's.

## Consequences
- The reference connector declares `repository.refs` and `repository.refs.create`; its
  conformance scenario creates one reference per key.
- `tests/fakes/repository_service.py` creates and reads references besides branches.
- The run's rules gain `extract` (`examples/README.md`).
- P-03 has twenty-two steps. Its takeover by hand reserves with `make reserve`.
- The verification of a run's provenance accepts a step that its `when` skipped, or that a
  person declined, as completed. It refused them before, and P-03's skipped reservation showed
  it (ADR-0088 says such a step succeeds).

## Where this promise ends
A reservation P-03 creates is checked against what `main` holds when the step reads it, not
against the base the worker cloned. A number that `main` gained under the same identifier in
between is taken for the change's own and is not reserved; the pipeline's check that a number
is used once stops that change instead. The run reserves only what the pattern in the bundle
names, and only files the changeset writes. A record named in another file's text, or one a
change writes elsewhere, is not seen.

A conflict stops the run; it does not renumber. A resume after a failure that was not
retryable runs with a new idempotency key, and then finds the references its earlier attempt
created as somebody else's, as `create-branch` finds its branch. A person then reads the
references and deletes or keeps them. A number reserved for a change that never merges is a
gap, and a gap means nothing.

The operation creates at most ten references in one call. On a conflict, those created before
it stay. Atomicity is the host's: a host that lets a second writer create an existing
reference makes the reservation worthless, and this connector cannot tell.
