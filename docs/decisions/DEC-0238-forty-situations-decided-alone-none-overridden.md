# DEC-0238 — Forty situations decided alone, none overridden

**Category:** NON-BLOCKING
**Raised in:** the pull request of the final round (DEC-0236), whose notice NTC-0279 is the fortieth `unlisted` notice; `make gate-decisions` fails the register until this request exists (DEC-0042)
**Issue:** [#685](https://github.com/Jersyfi/taktus/issues/685)
**Needed by:** 2026-11-27
**Provisional answer:** Option A. Sessions go on deciding a situation no anchor names, and record it as an `unlisted` notice; the next review comes at sixty.
**Override review:** 40 `unlisted` notices, 0 overridden by a later decision: an override rate of 0 %.

## 1. What this is about

A session sometimes meets a situation that no entry of the anchor page names. Since DEC-0039
it decides in the direction the vision and the existing anchors point, and records the decision
as a *notice* of kind `unlisted`. You read the notice and override it where it went the wrong
way. You answered the first review, at twenty, with "keep it" (DEC-0221). This is the second,
at forty.

## 2. Why you are being asked

DEC-0042 makes the review a request to you after every twenty `unlisted` notices. How much a
session decides alone is yours to set (DEC-0039).

**Sources checked:** `docs/vision/` (principles 9 and 10 set no number); ADR-0017 §9 (places the
review, leaves its outcome to you); both anchor pages (section *Neither list* says that the
review happens, not what follows); the register: DEC-0039, DEC-0042 and DEC-0221 (the first
review, Option A). None answers the second review.

## 3. What you must decide

Whether sessions go on deciding situations no anchor names, recording each as a notice, or
whether such a situation becomes a question to you again.

## 4. What you need to know to decide

- **The rate.** Forty `unlisted` notices; none was overridden by a later decision.
- **What the twenty since DEC-0221 decided.**
  - Shipped defaults of a tenant: NTC-0227 (working time), NTC-0228 (how far a score may
    fall), NTC-0230 (the trace's reader and retention), NTC-0234 (no message a model wrote
    without rules), NTC-0242 (rules for a result defect), NTC-0246 (when a skill is approved),
    NTC-0249 (rules from precedent), NTC-0258 (recovery objectives), NTC-0271 and NTC-0277
    (which role a stop or a chain's halt reaches).
  - Readings of a requirement: NTC-0232 (UC-03's stages hold for four weeks), NTC-0263 and
    NTC-0266 (parts of B-3.02, not processes of their own).
  - Tools and providers: NTC-0255 (the compatibility baseline), NTC-0261 (a dependency alert),
    NTC-0272 (Zensical for the documentation site), NTC-0278 (the first evaluation platform).
  - Rights: NTC-0269 (writing on a warehouse), NTC-0270 (who states the value basis).
  - Maintenance: NTC-0279 (when a scaffold's artifact counts as unmaintained).
- **What 0 % says.** Either the sessions decide as you would, or the notices are not read; the
  register cannot tell the two apart.

## 5. Options

### Option A — keep the reversed default (recommended)

- **Meaning:** a session goes on deciding a situation no anchor names, and records it as an
  `unlisted` notice. The next review comes at sixty.
- **Consequence:** the work continues without waiting; you read the notices when you choose.
- **Effort:** none.
- **Reversibility:** cheap: a later answer can narrow it at any time.
- **Why recommended:** none of forty was overridden, and each took the stricter option where two
  were consistent with the sources (DEC-0040).

### Option B — such a situation becomes a question again

- **Meaning:** a situation no anchor names becomes a `NON-BLOCKING` decision request, and the
  work continues on its provisional answer.
- **Consequence:** about one request in every other pull request, at the pace of the last forty.
- **Effort:** the anchor pages, CLAUDE.md §8 and the gate.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing. The work continues on Option A.

## 7. How to answer

"DEC-0238: Option A." or "DEC-0238: Option B."

## Outcome

**Decided:** 2026-11-14
**Answer:** Option A. "DEC-0238: Option A." (the owner's words, in conversation with the session).
**Reasoning given:** none beyond the recommendation.
**What it changes:** Sessions go on deciding a situation no anchor names and record it as an `unlisted` notice; the next review comes at sixty.
**Recorded in:** this pull request
