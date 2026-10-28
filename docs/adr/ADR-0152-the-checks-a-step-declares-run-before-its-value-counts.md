# ADR-0152 — The checks a step declares run before its value counts

**Status:** accepted · builds on ADR-0014 ("`exact`, written out"), ADR-0082 (the catalogue of
checks) and ADR-0042 (the decision request at a step boundary) · serves UC-4.13 · issue #223

## Context

A step classed `exact` declares at least one check from the catalogue (ADR-0082, UC-4.13). The
catalogue has six rows: reconciliation against a total, agreement with a second system,
plausibility bounds, approval above a threshold, sampling, and recomputation (provisional,
DEC-0173). Until now the declaration was read only to write the exactness statement. No check
ran. A step whose value broke its own bounds finished, and the steps after it read the value.

ADR-0014 says what must happen instead. A value counts only when a rule checked it against its
sources. If anything disagrees, nothing counts and a question is raised.

Two rows need more than the declaration says. A reconciliation names its total and the
capability it is read through, but not the operation that reads it. An agreement names the
capability of the second system, but not where in its answer the value lies. A process
references adapters by capability; the operation and its input belong to the step's work, as
they do for a connector step (ADR-0024).

## Decision

### 1. The checks run when the value is computed, before it counts

A step that declares checks has them applied to its value in the run, after the value is
computed and before the step finishes. Each row is a rule over the value and what the check
read (`domain/service/checking.py`):

| Row | What the rule does |
|---|---|
| bounds | the value is a number within `minimum` and `maximum`, and its text matches `pattern` |
| reconciliation | the parts — a list of numbers, an object's numbers, or one number — sum to the total read |
| agreement | the value equals the second system's value; numbers agree by value, anything else by text |
| recomputation | the step's rule or statistic, evaluated again over the same inputs, gives a value of the same digest |
| approval | a value above `threshold` waits for a person of `role` (§3) |
| sampling | `share` of the results go to a person of `role` after they counted (§4) |

Numbers are compared in decimal, from their text. No language model chooses, runs or judges a
check.

### 2. A check that disagrees stops the value

When any check a rule decides fails, the step fails. Its reason names every failed check, the
check's parameters and the values it compared. The step leaves no result, so no step after it
reads one, and the run escalates as for any failed step. The ledger records `step.finished`
with the outcome `check_failed`.

A check that cannot be applied fails as well. Examples are a value that is not a number where a
number is needed, a reading without the part it names, or a recomputation of a call. A value no
check could judge does not count.

### 3. An approval holds the value at the step boundary

When every check a rule decides has passed and the value is above an approval's threshold, the
step waits for a person. It raises a decision request of class `domain` to the check's role and
holds the steps after it, as an anchored step does (ADR-0042). The request's identifier names the
check and the digest of the value. On a confirmation the step is evaluated again over the same
inputs. A value of the same digest then counts, because a person of the role confirmed exactly
that value. A decline halts the run, and the value does not count. A value at or below the
threshold counts without a request.

### 4. A sample is taken after the value counted

A sampling check chooses a result by a digest of the run and the step: the same results are
chosen for the same runs, and over many runs the stated share. A chosen result counts, and the
run goes on. A decision request of class `domain` asks the role whether the result was right;
it blocks nothing. The ledger records `check.sampled`, naming the step, the check by its place
(`check_<n>`) and the request. The error rate per check is read from these entries and the
verdicts (`application/query/samples.py`), and it names no person (principle 14).

### 5. A check reads through the step's work, and the reading is provenance

A reconciliation or an agreement reads its source through the operation the step's work names
under `checking.reads`, keyed by the check's capability. The operation is a read; an outward
operation is refused. `checking.select` names the part of the step's value the checks judge.
What a check read joins the step's provenance record as a source input, with its digest and the
moment it was read (ADR-0021).

## Alternatives

- **The operation in the check's declaration.** The shared kernel's `Check` would grow
  connector details, and a process would then name an operation where it names a capability.
  The work already carries how a step calls a connector.
- **Checks as steps of their own.** A check step after the producing step would let the value
  exist as a result before it was checked, and a dependent step that forgot the check would
  read it. Running the check inside the step keeps the value from counting at all.
- **Approval by storing the value and finishing the step on confirmation.** The step would
  finish without its checks running against the confirmed value. Evaluating again keeps one
  road to a finished step. The price is a variable method, which may compute another value and
  ask again (see below).
- **Sampling by a random draw.** A draw would choose different results each time a run is
  looked at. A digest chooses the same results, and a person can check that it did.

## Consequences

- `domain/service/checking.py` holds the rules; `RunEngine._checked` applies them in
  `_local_step`; `domain/service/anchoring.py` drafts the approval and the sample requests.
- `Control.checking` (`domain/model/work.py`) carries `select` and `reads`.
- The ledger gains `check.sampled`, and `step.finished` gains the outcome `check_failed`.
- The exactness statement is unchanged: what a check covers and what it does not was already
  stated per row. `tests/exactness/test_checks.py` holds each row to a fixture that passes, one
  that fails, and a wrong value that slips through it as the statement says.

## Where this promise ends

The checks run on steps the run evaluates itself: rules, statistics, connector calls and
language model calls. A worker step's checks do not run yet; a worker step is never `exact`
(ADR-0014). A check judges the value it is given against what it read at that moment. It does
not judge whether its total or its second system is right, which is what its row does not
cover. A recomputation evaluates the rule again in the same instance, over the same resolved
inputs; it finds a rule that does not repeat itself, not a rule that is wrong the same way twice.
An approval of a value from a variable method asks again when the method computes another value
after the confirmation. A sample whose request cannot be raised is not taken, and the result
still counts. The measured rate of corrections after the checks passed is the value ledger's
(UC-6.9), not this one.
