# ADR-0238 — The guided mode asks for what a plan draft lacks, and the expert mode sets it

**Status:** accepted · extends ADR-0029, ADR-0237 · UC-13.1, UC-10.3, DEC-0228

## Context

UC-13.1 asks for two ways of working with Taktus that reach the same results: an expert mode
with full control, and a guided mode that leads a person step by step, translating the terms of
the trade and hiding nothing. Switching between them must lose nothing and ask nothing twice,
and the mode must never be a permission. ADR-0029 files the dialogue in which a person says what
they want under `command`. ADR-0237 made that dialogue's record: the plan draft.

## Decision

### 1. Both modes change the one plan draft

The expert mode sets any field of a draft at once, as one revision. The guided mode asks one
question at a time and turns each answer into a revision of the same draft. There is no second
record of the guided mode's progress: what it has asked is what the draft holds.

### 2. The guided mode asks for the first part the draft lacks

It asks, in this order, for the goal, the steps — a template or process to choose, or steps to
describe —, the date it is due, the autonomy level, its reason, and an estimate for each step
without one. A question carries the plain explanation of the term it uses where it first
appears. The level it offers is 1 or 2 (ADR-0026). A part set in either mode is never asked
again; so a person who switches mode at any point continues where the draft stands.

### 3. Every setting is shown, asked or not

The guided mode shows every setting of the draft that takes effect, with its value and why it
takes it. The two it never asks — what the plan results in, and the process version a chosen
template registered — are marked as not asked and shown all the same.

### 4. The mode is not read by any decision

No use case of the dialogue takes the mode. Commissioning is the same act, by the same identity,
with the same rights, whichever mode filled the draft.

## Alternatives

- **A wizard of its own with its own state.** It would be a second record of the same intent,
  and switching mode would have to reconcile two.
- **A simplified product for people who are not technical.** UC-10.3 and UC-13.1 forbid it: the
  guided start leads into the same system and the same settings.

## Consequences

- `components/command/domain/service/guided.py`: `next_question`, `settings`, `Mode`.
- `tests/components/command/test_guided_and_expert.py`.

## Where this promise ends

- The questions are English. Their translation, and the web app's presentation of them, are not
  part of this decision.
- An answer is taken as given. Understanding a free-text answer and reflecting it back is
  ADR-0008's, and is the caller's to do before it revises the draft.
- The mode is a value a surface passes; it is not stored per person here.
