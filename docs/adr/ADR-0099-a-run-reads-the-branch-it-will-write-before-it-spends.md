# ADR-0099 — A run reads the branch it will write before it spends

**Status:** accepted · builds on ADR-0024, ADR-0095 and ADR-0097 · DEC-0202

## Context
P-03 writes its change onto the branch `taktus/issue-<n>` at the step `create-branch`. The commit
at the branch's head carries the step's idempotency key, `taktus:<run>:<step>:<attempt>`, as a
trailer. A branch of that name whose head carries another key, or none, is somebody else's, and
`create-branch` ends in `conflict`.

On 2026-10-15 the instance handed #256 to P-03 a second time. The first attempt had given the
issue back (ADR-0097) and left its branch, its pipeline red. The second run paid for its coding
step and then failed at `create-branch` with that conflict. Everything that decided the failure
was known before the coding step began. The owner's condition is that money is not spent again
and again on runs that then break off (DEC-0202).

The connector had no operation that reads a branch. `repository.pipelines.status` resolves a
branch to its head, but says nothing about the key and fails on a missing branch.
`repository.files.list` at a ref says nothing about who made it. Neither is an honest answer to
"would `create-branch` write here, or find its own branch".

A step could ask with the key `create-branch` will carry only by writing the key's format into
the bundle. The format belongs to the run (`ports/connector.py`), not to a process.

## Decision

### 1. The connector reads a branch
The reference connector gains `repository.branches.read`, a read in the capability
`repository.branches`. It takes a `name` and an optional `key`. It answers whether the branch
exists, the commit at its head, and the key that commit carries as a trailer, or null. `free`
says whether a `repository.branches.create` under the given key would create the branch or find
it as its own: none exists, or its head carries exactly that key. Without a key, `free` says only
that none exists. It is the lookup `create-branch` makes, without acting. No contract changes:
an operation is the connector's own declaration (`contracts/connector/v1` §3).

### 2. A step can name the key of a later step
A `$run` reference reads `keys.<step-id>`: the idempotency key that step's current attempt
carries to a connector, the first attempt's while it has not started. A process can hand that
key to a read, so that a step before another asks whether what the later one will write is
already its own. The format of the key stays in the run.

### 3. A reading says what its failure means
An expectation on a read (`expect`) may carry `says`: what a reading that does not show it
means, for the person who reads the failure. Each `${field}` of the reading is put in. The
failure states it before the check that did not hold. This is how a refusal names the branch
and what a person does, without a rule that knows about branches.

### 4. P-03 reads the branch after its claim and before the coding step
P-03, version 11, names the branch right after admission and reads it in the step `read-branch`,
after the claim and before `implement`. The read passes the key of `create-branch` and expects
`free`. A branch the run did not make stops the run there, before anything is spent. The reason
names the branch, its head and the key at it, and says that a person looks at the branch,
deletes or renames it, and hands the task over again. A branch whose head carries the run's own
key is free: `create-branch` replays it.

The read comes after the claim, not before it. A run started by an event has nobody watching it.
After the claim, the escalation gives the claim back, and its comment carries the reason to the
issue, where a person reads it (ADR-0097). Before the claim the reason would reach only the
run's record. The claim costs two requests and no money. The branch's name is the bundle's
template; the product holds none of it (ADR-0092).

## Alternatives
- **Read the branch before the claim.** Nothing would be written on a refusal, and nothing would
  be given back. The reason would not reach the issue, and an unwatched run would fail where no
  one looks.
- **Let `create-branch` delete or overwrite the old branch.** The old branch may hold work a
  person wants to see. Nothing that deletes belongs in a step without asking (CLAUDE.md §9).
- **A new branch name per run.** It would never conflict, and would leave one branch per attempt
  for a person to clean up. It hides the leftover instead of stopping at it.
- **Compose the key in the bundle with a template.** It writes the run's key format into every
  process that asks, and breaks silently when the format changes.
- **A rule that fails with a composed text.** A `check` over a template's output can fail, but
  its reason is the check's, not the text. An expectation that says what it means keeps the read
  and its verdict in one step, and a resume reads again (issue #31).

## Consequences
- The reference connector declares `repository.branches.read`, two requests a call.
- `Run.record()` carries `keys`; `examples/README.md` names `keys.<step-id>` and `says`.
- P-03 has twenty-eight steps, twenty-one of them on the repository connector. Its takeover by
  hand looks for the branch after the claim.
- `tools/first_run.sh` recognises the refusal at `read-branch` as a leftover branch, as it did the
  conflict at `create-branch`.

## Where this promise ends
The read tells the branch's state when it runs, not when `create-branch` writes. A branch
pushed between the two still ends the run in `conflict` at `create-branch`, after the coding
step has spent.

`free` compares exact keys. A key carries the attempt, so a branch made by an earlier attempt of
`create-branch` in the same run is not free for a later one, as ADR-0095 states for references.
Whose a branch is beyond the key at its head is not judged: a branch somebody pushed onto after
the marked commit is not free, and a branch somebody marked with a copied key is taken as the
run's own.

The read protects only the branch the process names. Any other way a run breaks off after its
coding step, such as a red pipeline or a reference somebody else holds, still costs that money.
The reason is the bundle's text, put in by the run. It can be wrong if the bundle's text is.
