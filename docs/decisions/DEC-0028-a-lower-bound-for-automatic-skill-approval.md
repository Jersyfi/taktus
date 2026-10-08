# DEC-0028 — A lower bound for automatic skill approval

**Category:** NON-BLOCKING
**Raised in:** [#46](https://github.com/Jersyfi/taktus/pull/46)
**Issue:** [#43](https://github.com/Jersyfi/taktus/issues/43)
**Needed by:** 2026-12-31

## 1. What this is about

A **skill** is a reusable, versioned piece of know-how that a model or a worker uses for one kind
of task: how to reconcile a certain statement, how to triage a certain kind of issue. The project
definition requires Taktus to learn skills from its own work, under governance: it notices a
recurring way of working, writes it down as a draft skill, evaluates it, and approves it. At
autonomy levels 1 to 3 a person approves. At level 4 — whole process chains running unattended —
the definition requires approval to be automatic once the skill has passed **n** evaluations, with
**n** configurable. A skill that later performs worse falls back to its previous version on its
own.

The definition's own open questions ask whether n needs a **floor**: a smallest value that no
organisation can configure below. Without one, an organisation can set n to 1, and a skill that
passed a single evaluation changes what every later run does.

## 2. Why you are being asked

Approving a skill without a person is autonomy for the act of approving, and the floor sets how
much evidence counts as enough. That is the judgement entry M3.9 of
`docs/decisions/anchors.taktus.md` gives you: *"Raising an autonomy level of a process, including
the project's own processes."* The question does not fit the entry word for word; if you see it
elsewhere, say which entry, and the page gains it.

## 3. What you must decide

Whether there is a value of n below which automatic approval at level 4 cannot be configured — and
if there is, whether it is set now or from data.

## 4. What you need to know to decide

- **What is already required.** Definition UC-14.2: no skill reaches production without passed
  evaluations; a person approves at levels 1 to 3; approval is automatic at level 4 after n passed
  evaluations; quality is measured and a worse skill falls back automatically; learning happens
  at process level, never from a person's behaviour. None of that is in question here.
- **What exists.** Nothing of the skill lifecycle is built; the roadmap places it in `0.6.0`,
  after the evaluation data of `0.5.0`. No answer changes code today.
- **What the repository asks of evidence elsewhere.** Raising a process's autonomy requires a
  demonstrated quality history, and the process says what is missing to go higher (ADR-0026). A
  floor for n is the same kind of rule for skills.
- **Where a floor matters most.** A skill used by a step whose result must be exact — an amount, a
  tax code — changes what the principles keep with a rule; a skill used before an act with legal
  force changes what a person then signs. The legal anchors hold regardless of any skill, but the
  person signs what the skill prepared.

## 5. Options

### Option A — a floor, its value set from data (recommended)

- **Meaning:** n has a floor no configuration can go below. Its value is fixed when `0.6.0` is
  designed, from how often skills that passed k evaluations later fell back in `0.5.0`'s data, and
  it is higher for skills used by `exact` steps.
- **Consequence:** automatic approval exists as the definition requires, and cannot be configured
  into a single evaluation; the number rests on measurement.
- **Effort:** none now; part of designing `0.6.0`.
- **Reversibility:** cheap until `0.6.0` is built.
- **Why recommended:** it answers the question the definition asks — yes, a floor — without
  inventing a number no measurement supports.

### Option B — a floor, fixed now

- **Meaning:** for example, n is never below 20, decided today.
- **Consequence:** the rule exists before any skill does; the number is not based on any
  measurement and may be changed by a request later.
- **Effort:** none now.
- **Reversibility:** cheap until `0.6.0`.

### Option C — no floor

- **Meaning:** n is freely configurable, as the definition currently reads.
- **Consequence:** an organisation can approve a skill automatically after one evaluation; the
  protection is the automatic fallback and the organisation's own judgement.
- **Effort:** none.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing until the skill lifecycle of `0.6.0` is designed; nothing approves skills before then. The
date is when you are asked to look, well before that design starts.

## 7. How to answer

"DEC-0028: Option A." — or B with the number, or C — in issue
[#43](https://github.com/Jersyfi/taktus/issues/43). A free-text answer is read back as an
interpretation and confirmed before it is acted on.

## Outcome

**Decided:** 2026-10-08
**Answer:** Option A. Automatic approval of a skill at autonomy level 4 has a floor for n that no configuration can go below. Its value is set when the skill lifecycle of `0.6.0` is designed, from the evaluation data of `0.5.0`, and it is higher for skills used by `exact` steps.
**Reasoning given:** none beyond accepting the recommendation, whose reason was that it answers the definition's question — yes, a floor — without inventing a number no measurement supports.
**Recorded in:** [#106](https://github.com/Jersyfi/taktus/pull/106); `docs/roadmap.md`, `0.6.0`
