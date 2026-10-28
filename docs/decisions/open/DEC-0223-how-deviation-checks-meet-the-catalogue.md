# DEC-0223 — How deviation checks meet the catalogue

**Category:** NON-BLOCKING
**Raised in:** the branch `concept/package-a` (package A, DEC-0222), for issue #92
**Issue:** [#639](https://github.com/Jersyfi/taktus/issues/639)
**Needed by:** 2026-11-15
**Provisional answer:** Option A, without the refusal of a `sourced` step that declares no check. Marked in `docs/adr/ADR-0153-a-result-defect-is-bounded-decided-by-rule-and-planned-for.md` §1 and in `docs/status/0.5.0.md`.

## 1. What this is about

Two requirements describe the checks a step declares, and they do not describe the same thing.

The first is the catalogue of how a step becomes exact (UC-4.13). It has five rows, and a sixth
that you accepted provisionally (DEC-0173): reconciliation against a total, agreement with a
second system, plausibility bounds, approval above a threshold, sampling, recomputation. Its
boundary says that a check outside the rows is a change of the catalogue. These checks now run
before a value counts (#223): a value that fails one does not count, and the run goes to a
person.

The second is deviation detection (UC-4.10). It asks for four families of check after a step
has finished: distribution against earlier results, completeness, reference points, and the
shape of the source the step read. Each declares its method, a tolerance, and whether a failure
escalates or stops. A failed check marks the result *suspect* and never stops the run by itself.
It also asks that every `sourced` step carries at least one check.

Two of the four families have no row in the catalogue: completeness (412 rows where the source
has 418) and the shape of the source (a column order that changed). Distribution and reference
points match rows that exist: bounds, and reconciliation or agreement.

## 2. Why you are being asked

What a use case requires is yours (M3.15), and the two use cases conflict: UC-4.10 needs two
kinds of check that UC-4.13 says are a change of the catalogue.

**Sources checked:** the vision — principle 2 (AI at the core) and principle 8 (repeatability)
want a result checked against what it should be, and say nothing about which vocabulary. ADR-0014
requires a machine check for `exact` and says nothing counts when one disagrees. ADR-0021 asks for
detection of result defects and names no catalogue. ADR-0023 lets the rule, not the check, decide
escalation and stop. ADR-0082 fixes the catalogue as the shared kernel's `Check`. Both anchor
pages: M3.15 keeps a use case's requirement with you; nothing lets a session add a row. The
register: DEC-0069 accepted both use cases as written, and DEC-0173 added one row; neither met
the two families. No earlier decision answers this.

## 3. What you must decide

Whether completeness and the shape of a source become rows of the one catalogue, or a second
kind of declaration beside it.

## 4. What you need to know to decide

- **What is built.** The catalogue's checks run before a value counts (ADR-0152). A result that
  counted and is later found wrong — corrected by a person, or a sample judged wrong — is now
  bounded, decided on by rule and planned for (ADR-0153). What is not built is a check that finds
  a wrong result on its own after the fact.
- **What a `sourced` step without a check is.** Taktus's own blueprints have about forty-five,
  most of them connector reads and writes. Refusing them at registration would refuse every
  blueprint until each gets a check.
- **What is hard to change later.** A second declaration beside `checks` is a second vocabulary in
  every bundle. Two rows added to the catalogue are additions to one.

## 5. Options

### Option A — one catalogue, two new rows (recommended)

- **Meaning:** completeness (`count`, `source`: the parts must number what the source holds) and
  source shape (`columns` or `pattern` over what the step read) become rows of the catalogue.
  Every check runs before the value counts, as today. A check that passed when the value counted
  and fails when it is run again later marks the result suspect, which starts the analysis of
  ADR-0153. Whether to escalate or stop is the rule's (ADR-0023), not the check's. A `sourced`
  step declares at least one check from the version after the blueprints carry one each.
- **Consequence:** UC-4.10 is restated in the catalogue's rows in a change of its own; UC-4.13
  gains two rows; `Check.json` gains two kinds.
- **Effort:** two rows and their rules, about a day; a check per `sourced` blueprint step, about
  a day more.
- **Reversibility:** cheap while only this repository's bundles declare them.
- **Why recommended:** one vocabulary, one statement per process, and a check that keeps a wrong
  value from counting is stricter than one that only marks it afterwards.

### Option B — a second declaration for detection

- **Meaning:** `watch` beside `checks`: the four families with method, tolerance and
  `escalate` or `stop`, evaluated after a step finished, marking suspect and never gating.
- **Consequence:** two vocabularies; the exactness statement says nothing about watches unless it
  grows a fifth part.
- **Effort:** about three days.
- **Reversibility:** expensive once bundles declare watches.

### Option C — UC-4.10 is narrowed to the catalogue

- **Meaning:** completeness and source shape are dropped; distribution and reference points are
  the bounds and the reconciliation or agreement rows.
- **Consequence:** a partner file whose column order changed is found only where a bound happens
  to catch it.
- **Effort:** an hour.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing waits. The work continues on Option A without its two rows: the catalogue's checks run,
and a result reported wrong is bounded and planned for. The refusal of a `sourced` step without
a check is not enforced until the answer, because it would refuse the blueprints. On Option B or
C the provisional work stands as it is.

## 7. How to answer

"DEC-0223: Option A." or "DEC-0223: Option B." or "DEC-0223: Option C." — in issue [#639](https://github.com/Jersyfi/taktus/issues/639). A
free-text answer is read back as an interpretation and confirmed before it is acted on.
