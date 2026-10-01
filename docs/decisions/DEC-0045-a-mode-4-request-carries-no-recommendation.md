# DEC-0045 — A mode-4 request carries no recommendation; the gate demanded one

**Category:** DEFECT
**Raised in:** [#52](https://github.com/Jersyfi/taktus/pull/52), where the first mode-4 request, DEC-0044, was written
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

Two documents disagreed about a request in mode 4 — a question that is the owner's own, such as
the licence or the price. `anchors.md` §1 says the operator's part in mode 4 "is to supply what
the owner needs to think, not a recommendation". ADR-0017 §4 said every request marks one option
recommended, and `make gate-decisions` failed a request that did not. No mode-4 request had been
written before DEC-0044, so the disagreement had never surfaced.

## 2. Why you are being asked

You are not. The repository contradicted itself, which is entry M1.4 of
`docs/decisions/anchors.taktus.md`.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

- The mode is the anchor page's and the owner's; the request's shape follows the mode. ADR-0017
  §4 now says that a mode-4 request carries its options without a recommendation, and names its
  entry in `**Mode entry:**`.
- The gate follows: a request whose `**Mode entry:**` is a mode-4 entry fails if it marks an
  option recommended; every other request still needs exactly one.
- `make status` leaves mode-4 answers out of the acceptance rate: there is no recommendation to
  accept.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0045" in an issue.

## Outcome

**Corrected:** 2026-10-01
**What was wrong:** ADR-0017 §4 and the decisions gate required a recommended option in every
request, including mode 4, where `anchors.md` §1 forbids one.
**Why it was wrong:** the request's shape was written before the four modes existed, and was not
revisited when mode 4 was defined.
**What it now says:** a mode-4 request names its entry and carries its options without a
recommendation; the gate checks both ways; the acceptance rate leaves mode 4 out.
**What changed in substance:** the decisions gate and the acceptance line of `make status`.
**Recorded in:** [#52](https://github.com/Jersyfi/taktus/pull/52)
