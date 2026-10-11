# DEC-0173 — How a rule's own result becomes exact

**Category:** NON-BLOCKING
**Raised in:** [#228](https://github.com/Jersyfi/taktus/pull/228), for issue #91
**Issue:** [#225](https://github.com/Jersyfi/taktus/issues/225)
**Needed by:** before #223 is built, which runs the checks
**Provisional answer:** Option A. The catalogue carries a sixth row, `recomputation`, marked provisional in `contracts/shared/v1/Check.json`, in ADR-0082 and in the fifteen steps that declare it.

## 1. What this is about

Every step of a process that produces a value carries a class that says how wrong the value may
be. The strictest class, `exact`, says that the value is right because a machine checks it. A
booked amount is the example: it is booked only if it adds up to the invoice total.

The requirement you accepted in DEC-0069 makes that concrete. Every step classed `exact` must
name its check, chosen from a fixed list of five:

1. **Reconciliation against a total** — the parts add up to a total another source holds.
2. **Agreement with a second system** — the value equals what an independent system holds.
3. **Plausibility bounds** — the value lies in a range, matches a pattern, has the right sign.
4. **Approval above a threshold** — a person confirms a value above it before it counts.
5. **Sampling** — a person checks a share of the results afterwards, and the error rate is counted.

A step classed `exact` without a check is refused. Where none of the five fits, the requirement
says the step is not `exact`: it goes to a person, or to the next class down, `sourced`.

Building this, the session applied the rule to Taktus's own processes. They have sixteen steps
classed `exact`. One fits the list: the worked example's last step checks that an answer matches
a pattern, which is a plausibility bound. The other fifteen do not. They compute a value from
their inputs by a fixed rule: whether an issue is ready, the order of the backlog, the name of a
branch, the title of a pull request, the verdict of a removal test. There is no total to add up
to, no second system, no meaningful range, and no person in the loop. The rule *is* the
computation.

Read literally, the requirement now takes the class `exact` away from all fifteen.

## 2. Why you are being asked

Entry M3.15 of `docs/decisions/anchors.taktus.md`: "What a use case requires — what is new beyond
`docs/vision/` and the owner's project definition [...]: its outcome, its verification condition
and its boundary". The list of five checks is part of what the use case requires, and its
boundary says: "A check outside the five rows is a change of the catalogue, not a choice of the
user." Adding a row, or reading the refusal differently, changes what it requires.

**Sources checked:** the vision — principle 8 (repeatability and cost control) and principle 12
(production-ready) point towards keeping a class honest; neither says which steps are exact.
ADR-0014 says `exact` means "provably correct and machine-checkable", admits only a fixed rule or
a statistic to produce the value, and "where no check can be formulated, `exact` is
unreachable"; it does not say whether running the rule again counts as a check. ADR-0018 settles
which steps carry a class, not which check. `docs/architecture/methods.md` §4.3 repeats the five
checks. Both anchor pages: M3.15 keeps what a use case requires with you; M3.13 keeps the choice
of a step's method kind with you, which no option here changes. The register: DEC-0069 accepted
the use case as written; it did not meet the fifteen steps, because the rule had not been applied
to them yet. No earlier decision answers this.

## 3. What you must decide

How a step whose value a fixed rule computes from its inputs alone stays, or stops being, `exact`.

## 4. What you need to know to decide

- **What the class does today.** A step classed `exact` may only be produced by a fixed rule or a
  statistic. A language model, or a coding agent, can never produce its value. That protection
  holds for the fifteen steps now, and is checked on every change.
- **What a check catches** is stated with it, as is what it misses. Every process will carry a
  statement in plain words, generated from its steps: which checks apply, what they cover, what
  they do not cover, and what would slip through. Taktus never says "guaranteed".
- **Recomputation**, the sixth row Option A proposes: the value is computed again from the inputs
  Taktus recorded when the step ran, and must come out the same. It finds a value that was
  altered after it was produced, or that does not follow from what the step read. It does not
  find inputs that were themselves wrong, nor a rule that computes the wrong thing the same way
  every time. The statement would say exactly that.
- **What becomes hard to change.** Once processes outside this repository declare recomputation,
  removing the row means reclassifying their steps. Tightening it later is cheap.

## 5. Options

### Option A — a sixth row, *recomputation* (recommended)

- **Meaning:** the list of checks gains a sixth row. A step on a fixed rule or a statistic may
  declare it: the value is computed again from its recorded inputs and must be the same. The
  fifteen steps keep the class `exact` and declare it, and their statement names what slips
  through: wrong inputs, or a rule that computes the wrong thing.
- **Consequence:** the use case UC-4.13 gains the row in a change of its own, after your answer.
  The pull request that raises this request builds on it, marked provisional.
- **Effort:** none beyond what is built; the use case edit is an hour.
- **Reversibility:** cheap while only this repository's processes use it.
- **Why recommended:** it is the stricter option in substance: the fifteen steps keep the
  protection that no model produces their value, and gain a check whose limit is said aloud. It
  adds no step and no person.

### Option B — the five rows stay; the fifteen steps leave `exact`

- **Meaning:** the requirement stands as written. The fifteen steps are reclassified to
  `sourced` or `tolerant`, and only the worked example's last step stays `exact`.
- **Consequence:** the class says less, and honestly so. The protection is gone: a later version
  could move any of the fifteen to a language model without the class objecting. `sourced`
  requires a check against a source, which most of them also lack.
- **Effort:** an hour of the session's.
- **Reversibility:** cheap.

### Option C — a fixed rule is its own check

- **Meaning:** an `exact` step on a fixed rule needs no declared check; the refusal applies to a
  step on a statistic only.
- **Consequence:** the fifteen steps register as they are, and their statement says "no check
  declared". The refusal then almost never applies: most `exact` steps are fixed rules, the
  booking rule the requirement was written for among them.
- **Effort:** an hour of the session's.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing waits now. The pull request that raises this request builds on Option A: the sixth row
exists, marked provisional, and fifteen steps declare it. The answer is needed before #223 runs
the checks, because running a recomputation is part of that issue. On Option B, the fifteen
steps are reclassified and the row removed; on Option C, their declarations are removed and the
refusal narrowed. Either is one change of its own.

## 7. How to answer

"DEC-0173: Option A." or "DEC-0173: Option B." or "DEC-0173: Option C." — in issue
[#225](https://github.com/Jersyfi/taktus/issues/225). A free-text answer is read back as an
interpretation and confirmed before it is acted on.
