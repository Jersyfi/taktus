# ADR-0233 — A sourced step declares a check, and a read declares the shape of its answer

**Status:** accepted · extends ADR-0082, amends ADR-0185 §2 · issue #92, UC-4.10 §2 · DEC-0223,
DEC-0228

## Context

UC-4.10 §2 requires that a step of class `exact` or `sourced` carries at least one check, and
that a bundle in which one does not is refused at registration, with the finding naming the
step. Registration refused only an `exact` step without a check (ADR-0082). DEC-0223 kept the
refusal of a `sourced` step back until the blueprints carried a check on each: 264 `sourced`
steps in 68 bundles declared none. Of them, 227 call a connector, 36 compose a text from a
template, and one asks a model.

A `sourced` result is what its source holds. The catalogue's row that judges that is the
shape of the source (ADR-0185 §2): what the step read has the columns it was written for. A
connector answers with an object, and the steps after it read that object's members by name.

ADR-0185 §2 held an object's keys to the declared columns in the declared order. An object's
members have no order (RFC 8259 §4): the tests found the same connector's answer once in the
connector's order and once sorted, as a replayed recording gives it back. Two connectors that
serve one capability answer with different members besides the ones a process reads, and an
answer may carry a member only when it has a value.

## Decision

### 1. The refusal

A bundle registers only if every `exact` and every `sourced` step declares at least one check
from the catalogue. The finding for a `sourced` step without one names the step and the
catalogue row by row, as the finding for an `exact` step does, and says that where none fits
the step is `tolerant` or `free`, and the exactness statement names it unchecked. The refusal
is held at registration, as ADR-0082 §3 holds the other, so that a version stored before stays
readable and its runs resume.

### 2. The shape of an object is the members it must carry

The shape of the source judges a table read as text by its header row, exactly and in order, as
before: a column more or a column moved shifts what every later column means. It judges an
object, and each record of a list of records, by whether it carries every declared column, in
any order: a member more changes nothing a step reads by name, and a member missing is what the
step was not written for.

### 3. The check each kind of `sourced` step declares

- **A step that calls a connector** — a read, and a write's answer — declares the shape of the
  source over what the operation answered (`checking: {select: output}`). Its columns are the
  members of the answer the bundle reads: every `output.<member>` a later step selects from it,
  and every member its own `expect` reads. Where the bundle reads none, they are the members
  every answer of that operation carried in the tests, whichever connector served it. Where
  those have none in common, the step declares plausibility bounds: the answer is an object
  (`^\{`).
- **A step that composes a text from a template** declares plausibility bounds with a
  `pattern`: the longest fixed words of its template, which the composed text must carry.
- **A step that asks a model** for text declares plausibility bounds with the pattern its work
  already holds the answer to, over the answer's text (`checking: {select: text}`).

Every bundle whose steps changed has a new version.

### 4. What stays as it was

A `tolerant` or `free` step may declare none. A check is a rule, never a model. A failed check
fails its step with `check_failed`, and no step after it reads the value (ADR-0152).

## Alternatives

- **Keep admitting a `sourced` step without a check** (DEC-0223's provisional answer). It leaves
  the requirement of UC-4.10 unmet. Rejected: a requirement is met or its failure argued
  (CLAUDE.md §11.13), and here it can be met.
- **Every member of the answer, in order.** It failed a replayed recording, and every
  connector that serves the capability with members of its own.
- **Sampling by a person on every `sourced` step.** It fits the catalogue, but it would put a
  share of 264 steps' results in front of people every day, and a read is judged better by a
  rule than by a person.
- **The fields of every record a list holds.** An empty list has no records and so no columns,
  and the check would fail every read that found nothing.
- **Reclassifying the steps `tolerant`.** A connector's read is what the source holds; calling it
  tolerant would weaken the class to escape its check.

## Consequences

- `components/process/domain/service/exactness.py`: the refusal of a `sourced` step without a
  check; `components/run/domain/service/checking.py`: an object carries its columns.
- Every bundle under `blueprints/` with a `sourced` step carries a check on it and a new
  version; `dev-orchestration` P-03 among them, which the instance runs: its version 25 is
  rolled out as every version is. Its local recording is relabelled 25.
- A bundle written elsewhere — another branch, a tenant's own — registers only once each of its
  `sourced` steps declares a check; the finding says which and how.

## Where this promise ends

- The shape of a connector's answer is its top-level members, not the members of the records a
  list holds, and not their values: a record with a field renamed passes until a later step
  reads the field.
- Where nothing of an answer is read, the members it must carry are those the tests saw; a
  connector that answers without one of them, in a case the tests do not reach, fails the step:
  the run escalates with the check and what it compared, and the step's fallback applies.
- Plausibility bounds of `^\{` say only that the answer is an object.
- A template's pattern holds the fixed words, not the values put between them.
- A step skipped by its `when` produces no value and runs no check.
