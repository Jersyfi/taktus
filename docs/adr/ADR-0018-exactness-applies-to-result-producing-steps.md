# ADR-0018 — Exactness classes apply to result-producing steps only

**Status:** accepted · amends ADR-0014

## Context
ADR-0014 says: "Every step and every process carries an exactness class. It limits the admissible
methods." The table then says that `exact` admits `rule` or `statistics` only.

The rule was written with steps that produce a value in mind: an amount, a class, a text. Two of
the eight method kinds produce none. A `wait` step waits for something external — a pipeline
result, a point in time, an event — and passes on whatever arrives. A `human` step is itself the
authority: a person decides, and no method "produces" that decision. For both, the question the
exactness class answers — *which method may produce this result?* — has no object.

Read literally, ADR-0014 still demanded a class for them. Pull request #1 followed the letter:
the schema required `exactness` on every step, and an example step that waits for a pipeline
result, which is nothing but exact, had to be classed `sourced` to validate. The blueprint under
`blueprints/dev-orchestration/`, written alongside ADR-0014, already left `wait` and `human` steps
without a class. The documents disagreed with each other; that is a defect in the documents, not
a choice to put to the owner (ADR-0017 §2). This ADR corrects it. The record is DEC-0002.

## Decision
**Exactness classes apply to result-producing steps.** The six method kinds that produce a result —
`rule`, `statistics`, `ml`, `neural`, `llm`, `worker` — carry one, without exception. The two that
do not — `wait` and `human` — carry none. A `wait` or `human` step with an exactness class is a
schema error, so that the distinction cannot blur.

Everything else in ADR-0014 stands unchanged: the four classes, their meaning, the table of
admissible methods, the CI rule. `exact` still admits `rule` or `statistics` only. A number
produced by a language model still never reaches the accounting journal.

Where ADR-0014 says "every step", read "every result-producing step". Where it says "every
process", it stands: a process carries the class of the strictest result it produces.

## What changed in substance
Nothing. No method gained admission to `exact`. No step that produces a value lost its class. The
only observable change is that a `wait` or `human` step no longer carries a field that had no
meaning for it.

## Alternatives
- **Admit `wait` to `exact`** (the option #1 put forward). Wrong in kind: it treats waiting as a
  way of producing a value. It would also have invited the next question — what about `human`? —
  and an admissible set that grows by exception.
- **Leave the class on `wait` and `human` as documentation.** A field that constrains nothing is
  read as if it did. The forced `sourced` in #1 is what that looks like in practice.

## Consequences
- `contracts/shared/v1`: `Method` gains the subsets `producing` and `nonProducing`; `Step`
  requires `exactness` exactly for producing methods and rejects it on the others; the example
  that waits for a pipeline result is restored without a class; a `human` step example is added.
- `docs/architecture/methods.md` §4, `control-plane.md` §4.1, `project-structure.md` §4 and
  CLAUDE.md §4 say "result-producing step".
- ADR-0014 carries the amendment note and is otherwise untouched.

## Where this promise ends

The rule that `wait` and `human` carry no class is a schema rule and holds wherever the schema
is validated. It says nothing about what a `wait` step passes on: a wait that reads an
external state passes it on unchecked, and the step that reads the result is where a class
applies. A `human` step is the authority for its decision; whether the person decided well is
outside every class.
