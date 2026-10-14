# DEC-0198 — The first five tasks handed to Taktus, and #74's second run deferred

**Category:** NON-BLOCKING
**Mode entry:** M4 (what the project hands to Taktus, DEC-0197); M3.10 for #74's spend
**Raised in:** the session that took up the milestones `0.1.0` to `0.3.0`, on 2026-10-13; recorded in the pull request of its own that records the answer
**Issue:** none; the owner answered in conversation, and this record is the question with the answer
**Needed by:** 2026-10-14
**Written after the answer:** the owner answered in conversation on 2026-10-14; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

Stage 0 of DEC-0197 is in place on the installed instance since 2026-10-13: P-03 takes only an
issue labelled `to-taktus` (ADR-0097, #421). Two things were put to the owner:

1. Which tasks to hand over first. Five small tasks of `0.2.0` are ready, wait for no decision
   and need no ADR: #256, #277, #279, #282, #283.
2. #74's second run — P-03 with a token limit below what the first used, halting at a
   boundary — cannot run beside stage 0 without either racing the instance for the issue or
   registering a changed P-03 as the instance's active version. The halt itself is checked by
   the coding worker's conformance check W-14.

## 2. Why you are being asked

What the project hands to Taktus is the owner's (DEC-0197); #74's run spends under DEC-0196.

**Sources checked:** DEC-0197, DEC-0196, DEC-0053, #74; none chooses the tasks or the timing.

## 3. What you must decide

Which tasks Taktus gets first, and whether #74's second run waits.

## 4. What you need to know to decide

As §1.

## 5. Options

### Option A — hand over the five; defer #74's second run (recommended)

- **Meaning:** the five get `to-taktus`; #74 stays open with its second run deferred.
- **Why recommended:** stage 0 is measured on real tasks; #74's run needs a way to run that
  does not collide with stage 0.

### Option B — #74's run first, the handover after it

## 6. What is blocked

Stage 0's measures, until tasks are handed over.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-10-14
**Answer:** Option A. "Gib die fünf Issues an Taktus, #74 stellen wir zurück." (the owner's
words: hand the five issues to Taktus, #74 is deferred).
**Reasoning given:** none beyond the recommendation.
**What it changes:** the session labels #256, #277, #279, #282 and #283 `to-taktus` on
2026-10-14, the first tasks of stage 0. #74 stays open; its second run waits until it can run
without colliding with stage 0.
**What it does not change:** merging the pull requests Taktus opens stays a person's (#87).
**Recorded in:** this pull request
