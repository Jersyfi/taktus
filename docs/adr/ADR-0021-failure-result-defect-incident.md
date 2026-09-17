# ADR-0021 — Failure, result defect, incident

**Status:** accepted · amends ADR-0017 (the register's `DEFECT` is a documentation defect)

## Context
The run model knows one kind of going wrong. A step does not complete: the worker fails, a rule
refuses, a limit is reached, a stop arrives. The run halts or escalates at the step boundary, the
ledger records the cause, a person gets a situation package (control-plane.md §5.2). That is
loud, immediate, and handled.

A second kind is not handled and not even visible. A run completes. Every step reports success.
The result is wrong. Nothing in the model sees it, because everything the model checks — did the
step finish, did it fit the budget, did the value come from an admissible method — is true.

Exactness classes (ADR-0014) prevent a wrong value from being *produced*: an `exact` result comes
from a rule that checks it against its sources. They do not prevent a correct value from
*becoming* wrong. The source changes underneath it. A reference table is updated. A partner's
export changes its column order. A model version drifts. A prompt is edited. The value that was
right on Monday is wrong on Thursday, and every run since Monday reported success.

An unattended system that only notices loud failures is not usable for accounting, partner data
exchange or billing, however good its governance is. At autonomy level 4 nobody is watching the
results one by one; that is the point of level 4. Whatever is not noticed by the system is not
noticed.

## Decision

### 1. Three terms
From here on, code, schemas and documentation use exactly these words for exactly these things.

| Term | Meaning | Visible how |
|---|---|---|
| **Failure** | a run or a step did not complete | loud and immediate: the run halts or escalates at the boundary, the ledger carries the cause (`Cause` in the run component) |
| **Result defect** | a run completed and reported success, but its result is wrong | silent: only a check of the result against what it should be can find it |
| **Incident** | the tracked object above either of them: severity, timeline, affected scope, remediation plan, addressees, closure | raised and delivered by Taktus into the organisation's own tracking system |

A **failure** may be a *symptom* of a result defect, and a result defect may be *found* by a
later failure; the terms still name different things. A failure is about completion. A result
defect is about correctness. An incident is about handling.

The word *defect* is not used on its own. ADR-0017 uses `DEFECT` as the register category for a
fault in the repository's own documents; that category now reads as *documentation defect*, and
ADR-0017 carries the amendment. A wrong result is always a *result defect*. One word does not
mean two things.

### 2. What the model needs for result defects, and in which order
Handling a result defect has four parts. Detection: a result is checked against properties it
should have. Bounding: since when, and which results are affected. Impact: what was built on the
affected results and what has left the system. Repair: a remediation plan, and its execution.

Three of the four are analysis and arrive with `0.5.0`, when the value ledger and the role-based
views exist that they report into (UC-4.10 to UC-4.12, UC-6.8 in `docs/usecases/`). One cannot
wait: **the record that makes the analysis possible.** Bounding a result defect means answering
"since when has this been wrong?" over the past. An analysis of the past is impossible over data
that was never recorded. Every run that happens before the record exists is a run whose results
can never be bounded. That is why the provenance chain arrives now and the detection later, and
not the other way round.

### 3. The provenance chain
Every step result, and every artifact, is traceable to what produced it. The **provenance
record** of a step run names:

- the process version;
- the step, its method and its exactness class;
- the model version and the prompt version, where a model was involved;
- the adapter that executed and its version, where an adapter was involved;
- the inputs: which artifacts and results of earlier steps, which external sources, and at
  which point in time each was read;
- the outputs: the artifacts the step produced, and the digest of its value;
- the run, the step run, and the ledger entry that recorded the step's completion.

The record is a shared-kernel concept (`contracts/shared/v1/Provenance.json`), so that a
worker, a connector or a third-party view reads it the same way the core does.

**One record per completed step.** It is written in the same transaction as the ledger entry
that says the step finished, so that the two land together or not at all. A step that fails or
stops leaves no record; the attempt that later succeeds leaves one, and it lists every artifact
the step run produced across its attempts.

**Written once, never changed.** A provenance record is immutable at the database level, as the
ledger is (ADR-0006): the application role may insert and read, and a trigger rejects update,
delete and truncate for everyone but a superuser. A record that could be edited would let a
result defect edit its own history.

**Reference, do not copy.** A record carries identifiers, tokens and digests. It points at the
ledger entry, at artifact identifiers and at the results of earlier steps by digest. It carries
no artifact content, no value, no text. Its `method`, `adapter`, `model`, `outputs` and
`result_digest` are the same tokens the ledger entry carries, so that a record can be checked
against the ledger and the ledger's hash chain covers what the record claims.

**The chain.** A record's inputs name earlier step runs. Following inputs from the record that
produced an artifact leads back through every step run that contributed to it, to the first
input of the run — or into an earlier run, once results cross runs. That walk is one query on the
store, and the run component's provenance service verifies a chain: every completed step has
exactly one record, every input names a record that exists and an output it lists, every record
agrees with its ledger entry.

### 4. Cost
Provenance grows with every step and must not become the largest table in the system by an
order of magnitude. The bound, stated so that a test can measure it:

- **Rows.** A run of *n* completed steps adds exactly *n* records. A completed step produces at
  least three ledger entries (admitted, started, finished), so a run's provenance never has
  more rows than one third of that run's ledger entries.
- **Bytes.** With identifiers of at most 64 characters, a record serialised as JSON is at most
  1 KiB, plus 384 bytes per input, plus 80 bytes per output. The number of inputs is the number of
  artifacts and results the step read; the number of outputs is the number of artifacts it
  produced. Neither is inflated by provenance: a step that reads a hundred artifacts reads a
  hundred artifacts.

`tests/components/run/test_provenance.py` and `tests/adapters/persistence` measure both.

## Alternatives
- **Detection first, provenance later.** Detection without bounding finds that something is
  wrong and cannot say since when or what else is affected. Every run before the record exists
  is lost to the analysis for good. Rejected for the reason in §2.
- **Provenance as more ledger entries.** The ledger records what happened; a provenance record
  says what a result is made of. Folding the second into the first would put the inputs of every
  step into the hash chain and make the ledger the largest table. The record points at the
  ledger instead, and the chain covers the tokens the record repeats.
- **Provenance as a copy of the inputs.** Convenient for analysis, and the copy would be the
  largest table by an order of magnitude, a GDPR liability and a secret-leak risk — the same
  reasons ADR-0006 gives for the ledger. Referenced content can be fetched when an analysis
  needs it.
- **Treating a result defect as a failure.** A failure has a cause token and a step to resume
  from. A result defect has a window, an affected scope and things that have left the system. A
  model that treats them the same reports a wrong invoice the way it reports a timeout.
- **One word for both faults.** ADR-0017's `DEFECT` and the product's wrong result would have
  shared a word. A reader of a DEC record and a reader of an incident report would each have to
  ask which one is meant. Qualifying both costs one word each.

## Consequences
- `contracts/shared/v1` gains `Provenance.json`; the run component writes a record per completed
  step; the persistence port gains a provenance store; the database gains an immutable table.
- The ledger's kind vocabulary gains `egress.*` entries for what leaves the system (ADR-0022),
  so that the impact analysis of `0.5.0` has something to read.
- Detection, windowing, impact analysis, remediation and incidents are specified now
  (`docs/usecases/`) and built at `0.5.0`; the roadmap names them there.
- Correction after the fact is a risk class of its own and gets its own decision: ADR-0022.
- An automatic emergency stop, once detection can trigger one, is rule-based: ADR-0023.
