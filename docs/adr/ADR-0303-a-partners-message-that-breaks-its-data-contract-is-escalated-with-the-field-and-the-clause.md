# ADR-0303 — A partner's message that breaks its data contract is escalated with the field and the clause

**Status:** accepted · extends ADR-0273, ADR-0252 · UC-15.3 · DEC-0236

## Context

UC-15.3 requires that a received message which lacks a mandatory field is marked as deviating
"with the field and the clause it breaks", escalated, and never corrected, completed or guessed.
It requires the same of an export: one that fails its check is not sent.

ADR-0273 holds a version to its data contract at registration. At run time an import step's
`source_shape` check failed with `check_failed`, and the run escalated (UC-4.5). The failure
named the columns it found and those it was written for. It did not name the field that was
missing. Nothing named the contract, nor the clause of it that the message broke. The person the
escalation reached had to find the contract in the bundle.

## Decision

### 1. The failed shape check names what is lacking

A failed `source_shape` check over columns says, after the columns it found and those it was
written for, `it lacks` and every declared column the value does not carry, in their declared
order (`run/domain/service/checking.py`, `LACKS`).

### 2. The process component names the clause

`partners.breach(version, step, lacking)` (`process/domain/service/partners.py`) is a rule. It
finds the contract that names the step. For a step that checks the document an export sends,
it finds the export's contract by the export step's dependency. It returns, in words: the
direction, the contract's name, the partner and the standard or the reason for a proprietary
format; for every lacking field the contract requires, that it is missing and the clause
`fields.<name>: required`; who answers for the contract on each side; and that nothing of the
message was mapped, completed or guessed. Where the check failed on something other than a
missing field, the clause is `fields` with every required field. Where no contract names the
step, there is no breach.

### 3. The situation package carries it

The composition reads the failed step's reason when it writes the escalation's record
(`composition/escalations.py`). It takes the lacking fields from it and asks the rule. The
governance component's `Escalated.breaks` carries the answer. The package's *what happened*
ends with it. Its options gain one: ask the partner for a message that holds the contract, and
resume the run once it is there. The options never offer to correct the message.

### 4. An export that breaks its contract is not sent

Nothing new is needed for this. ADR-0273 makes an export step depend on a step whose check
covers the contract's required fields. A value whose check failed reaches no step after it
(ADR-0014). The export step therefore never starts. Its connector is never called, and no egress
entry is written. A test now proves it at run time.

## Alternatives

- **The run engine reads the contract.** The engine would learn a process concept it does not
  need in order to run a step. The step's own check already says what is missing.
- **The contract's clause as free text in the bundle, one per field.** A second wording of what
  `fields` already states, which can drift from it.

## Consequences

- The text of a failed `source_shape` check over columns gains `; it lacks …`.
- `Escalated` has the field `breaks`; the escalation's report title carries it.

## Where this promise ends

- **The field is named where the check is over columns.** A message that fails a `pattern`, or
  one with no columns at all, is escalated with the clause `fields` and all required fields, not
  a single one.
- **The clause is the contract's `fields` clause.** A message that arrives too often is not
  found by this decision; the frequency is held by the expected runs (ADR-0273).
- **The escalation is said, not acted on.** Asking the partner for a corrected message stays
  with the person the escalation reaches.
