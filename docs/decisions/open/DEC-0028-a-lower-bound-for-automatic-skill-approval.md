# DEC-0028 — A lower bound for automatic skill approval

**Category:** NON-BLOCKING
**Raised in:** [#46](https://github.com/Jersyfi/taktus/pull/46)
**Issue:** [#43](https://github.com/Jersyfi/taktus/issues/43)
**Needed by:** 2026-12-31
**Provisional answer:** Option A. No skill is approved automatically; every skill is approved by a person until the skill lifecycle of `0.6.0` is designed against this answer. Marked here; nothing in the code approves a skill yet.

## 1. What this is about

A **skill** is a reusable, versioned piece of know-how that a model or a worker uses for one kind
of task: how to reconcile a certain statement, how to triage a certain kind of issue. Taktus will
draft skills itself. The architecture already says when: a fault that was healed three times the
same way is a design fault, and Taktus proposes a draft skill that removes it.

A drafted skill changes what later runs do. Today a person would approve every one. The original
project definition asked whether Taktus may approve some of them itself, and if so, what the least
evidence is that a skill must show first — the **lower bound**. It left the question open. It was
carried as an open question in the definition's last chapter; the vision layer now records it, and
this request is where it is answered.

## 2. Why you are being asked

Approving a skill without a person is autonomy for the act of approving, and raising autonomy is
entry M3.9 of `docs/decisions/anchors.taktus.md`: *"Raising an autonomy level of a process,
including the project's own processes."* It also sets how much evidence counts as enough, which is
the same judgement M3.9 asks of a raise. The question does not fit the entry word for word; if you
see it elsewhere, say which entry, and the page gains it.

## 3. What you must decide

What the least evidence is before Taktus may approve a skill without a person — or whether it never
may.

## 4. What you need to know to decide

- **What exists.** Nothing of the skill lifecycle is built; it is part of `0.6.0` on the roadmap,
  after the ML bench and the value ledger. No decision here changes code today.
- **What the repository already asks of a raise in autonomy.** A process carries its autonomy level
  with the reason and with what is missing to go higher — a demonstrated quality history, a check
  that does not exist yet (ADR-0026). A skill approved automatically would need at least as much.
- **Where it would be dangerous.** A skill used by a step whose result must be exact — an amount, a
  tax code — or used before an act with legal force, changes exactly what the principles keep with
  a person or with a rule.
- **What a skill may never contain.** A person's behavioural pattern: skills learn at process level
  (principle 14). That holds whatever is decided here.

## 5. Options

### Option A — the same bound as a raise in autonomy, never for exact steps or legal anchors (recommended)

- **Meaning:** a skill may be approved automatically only when it shows what a raise in autonomy
  shows: a quality history on the processes that would use it, measured by the value ledger, and a
  passed evaluation. Never for a skill used by a step of class `exact`, and never for one used
  before a legal anchor. The number of runs the history needs is set when `0.6.0` is designed, from
  the data `0.5.0` produces.
- **Consequence:** one rule for "enough evidence" in the whole product; the exact and legal cases
  stay with a person.
- **Effort:** none now; part of designing `0.6.0`.
- **Reversibility:** cheap until `0.6.0` is built.
- **Why recommended:** it reuses a standard you have already accepted instead of inventing a second
  one, and it names the two places where no evidence is enough.

### Option B — a fixed number now

- **Meaning:** for example, twenty uses without a correction and a passed evaluation, decided today.
- **Consequence:** a bound exists before any skill does; the number is not based on any measurement.
- **Effort:** none now.
- **Reversibility:** cheap until `0.6.0`; a number that turns out wrong is then changed by a request.

### Option C — never

- **Meaning:** every skill is approved by a person, at every autonomy level.
- **Consequence:** the skill lifecycle always waits for a person, and `0.6.0`'s criterion — a release
  end to end without intervention — holds only if no new skill is needed on the way.
- **Effort:** none.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing until the skill lifecycle of `0.6.0` is designed; the provisional answer — a person
approves every skill — is what happens anyway while nothing approves skills. The date is when you
are asked to look, well before that design starts.

## 7. How to answer

"DEC-0028: Option A." — or B with the number, or C — in issue
[#43](https://github.com/Jersyfi/taktus/issues/43). A free-text answer is read back as an
interpretation and confirmed before it is acted on.
