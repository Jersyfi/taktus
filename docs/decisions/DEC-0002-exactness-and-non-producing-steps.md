# DEC-0002 — Exactness and non-producing steps

**Category:** DEFECT
**Raised in:** [#1](https://github.com/Jersyfi/taktus/pull/1), as open point 2 of its description, where it was presented as a decision
**Issue:** none; raised before ADR-0017, in the description only

This record is the worked example of ADR-0017 §2: a defect in the repository's own documents,
escalated as a choice between two readings instead of being corrected. It is kept in the register
so that the pattern is recognisable next time.

## 1. What this is about

Every step of a Taktus process names the *method* that does its work: a rule, a statistical
calculation, a trained model, a language model, a person, or simply waiting for something
external. Some results must never be wrong — an amount that gets booked. Others may vary — a
draft text. So every step also carries an *exactness class* that says how wrong its result may be
and, from that, which methods are allowed to produce it. The strictest class, `exact`, allows only
a rule or a statistical calculation; a language model may propose, never decide.

The rule "every step carries an exactness class" was written with steps that produce a value in
mind. Two kinds of step produce none: a step that *waits* — for a pipeline to finish, for a date,
for an event — and a step where a *person* decides. For them, "which method may produce the
result" has no object. Read literally, the rule still demanded a class for them, and the first
pull request that wrote the contracts followed the letter: a step that waits for a pipeline result
had to be labelled `sourced` to be accepted at all, although it produces nothing to source.

## 2. Why you are being asked

You are not. This section exists to name the row of `anchors.md` §1 that makes a question the
owner's call, and no row applies. The nearest is O4, *a change to the substance of an accepted
ADR* — but nothing in substance was to change: no method was to gain admission to `exact`, no
step that produces a value was to lose its class. What was wrong was the wording of a rule, and
`anchors.md` §2, row D6 puts that with the session: *correcting a defect in the repository's own
documents*. Applying that test is what reclassified this item.

## 3. What you must decide

Nothing. As raised in #1 the question was: "extend the set of methods admissible for `exact` to
include waiting, or leave the rule as it is?" Both readings were wrong in kind. Waiting is not a
way of producing a value, so it belongs neither inside nor outside the admissible set; the class
does not apply to it. A question whose every option is wrong is not a decision but a sign that
the document behind it needs correcting.

## 4. What you need to know to decide

- **Method.** One of eight kinds of doing a step's work: `rule`, `statistics`, `ml` (a trained
  classical model), `neural`, `llm` (a language model), `worker` (an agent with tools), `human`,
  `wait`. Four of them give the same result every time; two vary; two produce no result.
- **Exactness class.** One of `exact`, `sourced`, `tolerant`, `free`. It limits which methods may
  produce the step's result. `exact` admits `rule` and `statistics` only.
- **Result-producing step.** A step whose method yields a value: the first six kinds. `wait`
  passes on what arrives; `human` is itself the authority.
- **What the documents said.** ADR-0014: "every step and every process carries an exactness
  class." The contract written in #1: `exactness` required on every step. The blueprint written
  alongside ADR-0014: `wait` and `human` steps with no class. The three disagreed.
- **What the correction commits the project to.** Nothing new. The substantive rule — a number
  produced by a language model never reaches the accounting journal — is unchanged.

## 5. Options

The two readings #1 offered, and the correction that replaced both:

- **Reading 1 — admit `wait` to `exact`.** Treats waiting as a way of producing a value and invites
  the next exception (`human`). Rejected.
- **Reading 2 — leave the rule, label the waiting step `sourced`.** Keeps a field on the step that
  constrains nothing and is read as if it did. Rejected; this is what #1 shipped.
- **Correction — the class applies to result-producing steps only.** `wait` and `human` carry
  none; the six producing kinds carry one without exception. Applied.

## 6. What is blocked

Nothing was blocked. One example was mislabelled, and one contract required a field that had no
meaning for two of the eight method kinds. Both are corrected in the same pull request as this
record.

## 7. How to answer

Nothing to answer. To object to the correction: "Reopen DEC-0002" in an issue, with the reading
you hold — that would make it a decision under `anchors.md` row O4, and it would be raised as one.

## Outcome

**Corrected:** 2026-09-15
**What was wrong:** ADR-0014 required an exactness class on every step, including the two kinds
that produce no result. The contract in #1 enforced the letter and an example that waits for a
pipeline result had to be classed `sourced`; the blueprint written alongside the ADR already
omitted the class on `wait` and `human` steps. The documents contradicted each other, and #1
escalated the contradiction as a choice.
**Why it was wrong:** the exactness class answers "which method may produce this result?" For a
step that produces no result the question has no object. A rule written for producing steps was
applied to all steps, and the reader was asked to pick between two wrong readings of it.
**What it now says:** exactness classes apply to result-producing steps; `wait` and `human`
carry none, and the schema rejects one on them ([ADR-0018](../adr/ADR-0018-exactness-applies-to-result-producing-steps.md)).
**What changed in substance:** nothing. `exact` still admits `rule` and `statistics` only. No
step that produces a value lost its class; no method gained admission.
**Recorded in:** [ADR-0018](../adr/ADR-0018-exactness-applies-to-result-producing-steps.md),
applied in [#3](https://github.com/Jersyfi/taktus/pull/3)
