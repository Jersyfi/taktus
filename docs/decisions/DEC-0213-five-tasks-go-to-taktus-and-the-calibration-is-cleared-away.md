# DEC-0213 — Five tasks go to Taktus, and the calibration is cleared away

**Category:** NON-BLOCKING
**Mode entry:** DEC-0197 (handing a task to Taktus); CLAUDE.md §9 (never delete without asking)
**Raised in:** the session that took up the milestones `0.1.0` to `0.3.0`, on 2026-10-18
**Issue:** none; the owner answered in conversation
**Needed by:** 2026-10-18
**Written after the answer:** the owner answered in conversation on 2026-10-18; left out of the acceptance rate (DEC-0042).

## 1. What this is about

- Stage 1 of #87 started on 2026-10-18 (DEC-0212). P-03 has no handed task left.
- The calibration of 2026-10-17 (DEC-0211) left the branch `calibration/issue-481` and two processes on the instance: `p03-calibration` and `p03-limit-check`.

## 2. Why you are being asked

Handing a task to Taktus is the owner's (DEC-0197). Deleting a branch and switching off a process need the owner's yes (CLAUDE.md §9).

**Sources checked:** DEC-0197, DEC-0205 (covers only a failed attempt's branch), DEC-0211, DEC-0212.

## 3. What you must decide

Whether #317, #326, #327, #394 and #325 go to Taktus, and whether the calibration's branch and processes go.

## 4. What you need to know to decide

The five are ready, unclaimed, in `0.4.0`, and need neither an ADR nor a decision. The calibration is recorded in `docs/runs/2026-10-17-the-coding-model-calibrated-on-one-fixed-case.md`; its base commit `e4305cdb` stays in `main`'s history.

## 5. Options

### Option A — hand the five over; delete the branch; deactivate both processes (recommended)

- **Why recommended:** P-03 gets work in stage 1, and nothing the record needs is lost.

### Option B — keep things as they are

## 6. What is blocked

P-03's work in stage 1.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-10-18
**Answer:** Option A. "Zu 1 und 2. ja." (the owner's words: to 1 and 2, yes).
**Reasoning given:** none beyond the recommendation.
**What it changes:**

- #317, #326, #327, #394 and #325 carry the label `to-taktus`.
- The branch `calibration/issue-481` is deleted.
- `p03-calibration` and `p03-limit-check` are deactivated on the instance (`taktusctl deactivate`); their versions and runs stay.

**Recorded in:** this pull request
