# DEC-0031 — Principle 14 in the doctrine was stricter than its ADR

**Category:** DEFECT
**Raised in:** [#46](https://github.com/Jersyfi/taktus/pull/46), which corrects it
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

Taktus measures how long a person takes to answer a decision request, because the throughput of
the work depends on it. Principle 14 forbids using that number to assess the person. The repository
said how in three places, and they did not agree.

The architecture decision that introduced the measurement, ADR-0015, says the analysis belongs to
the deciding person and *is visible only to them by default*, and that aggregation is by role or
department only. The governance architecture says the same. The doctrine, `CLAUDE.md` §5, said the
analysis *is visible only to them* — without "by default", and without the aggregation.

The two readings differ in one case: whether the deciding person may choose to share their own
figure. Under the doctrine's wording they could not.

## 2. Why you are being asked

You are not. Where the doctrine summarises an ADR and the two disagree, the ADR wins (CLAUDE.md §1);
correcting the summary is a documentation defect, entry M1.4 of `docs/decisions/anchors.taktus.md`.
The correction changes nothing the software does: nothing measures response times yet.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

- **Found while checking the vision layer.** The drafted `docs/vision/principles.md` and
  `personas.md` used the ADR's wording; checking them against the repository showed the doctrine was
  the one that differed.
- **"By default" does not weaken the rule for anyone else.** Nobody but the person can widen the
  visibility; the default protects them, and the choice is theirs. No view ever shows a named
  person's figure to someone else without that choice.

## 5. Options

None for the owner. The alternative — changing ADR-0015 to the doctrine's stricter wording — would
change a decision to match its summary, and would take from the person the choice to share their own
figure, which is what principle 14 protects.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0031" in an issue, with the reading you hold.

## Outcome

**Corrected:** 2026-09-29
**What was wrong:** `CLAUDE.md` §5 said a decider's response-time analysis is visible only to them;
ADR-0015 and `docs/architecture/governance.md` §6 say visible only to them by default, aggregated by
role or department only.
**Why it was wrong:** the doctrine summarised the ADR and lost the qualification; where the two
disagree, the ADR wins.
**What it now says:** `CLAUDE.md` §5 carries the ADR's wording — visible only to the decider by
default, aggregation by role or department, never by person.
**What changed in substance:** nothing the software does; the doctrine now says what was decided.
**Recorded in:** [#46](https://github.com/Jersyfi/taktus/pull/46)
