# ADR-0243 — An explanation is composed from a step's records, at the depth and in the language of the reader's role

**Status:** accepted · builds on ADR-0004, ADR-0021, ADR-0241 · serves UC-6.5 · DEC-0228

## Context

UC-6.5 asks that for every step a reader may see an explanation can be requested — what was
done, by which method and why, the alternatives rejected, what the step consumed and what came
out — stating only what the records hold, at the depth and in the language the reader's role is
configured for, and a summary of a period with the definitions every view uses.

## Decision

### 1. The facts

`GET /levels/runs/{run}/steps/{step}/explanation` gathers the step's facts from three records:
the process version (method, reason, alternatives rejected, fallback, exactness class), the run
(the step's state and outcome) and the provenance record (the inputs, each with its kind and the
moment it was read, and the result's digest). What the step consumed is the accounting
component's spend of the run for the step. No fact names a person: the record's actor is left
out.

### 2. The text and its check

The explanation is a list of lines composed from the facts by a template of the reader's
language, `en` or `de`. A **short** explanation states what was done, by which method, why, and
how it ended, and what it cost where it cost money; a **full** one adds the alternatives, the
fallback, the inputs and the result. Each line of the short explanation is in the full one. The
depth and the language are the role's, from the view configuration (ADR-0241 §2); a reader who
holds several roles gets the deepest. Every number in the text must be a number of the facts:
`grounded` fails a text with any other, and every explanation passes it before it is answered.

### 3. A summary of a period

`GET /summary?days=` states per process the runs that ended, the share that finished without a
correction, the escalations and the cost, using the value component's figures of ADR-0244 —
the same identifiers and values the export carries.

### 4. Visibility

A run the reader may not see is answered as one that does not exist, by the one predicate
(ADR-0055 §5).

## Alternatives

- **A language model phrases every explanation.** Not built: a template states the facts
  without a model's cost and variance. Were one used, `grounded` is the check it must pass.

## Where this promise ends

- The explanation says why a method was chosen and what it was given and returned; it does not
  explain what happened inside a model or a worker.
- `grounded` holds numbers; a wrong word next to a right number is not seen.
- Two languages are shipped; a role configured for another gets English.
