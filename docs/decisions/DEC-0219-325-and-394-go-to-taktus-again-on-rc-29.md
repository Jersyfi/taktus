# DEC-0219 — #325 and #394 go to Taktus again on rc.29

**Category:** NON-BLOCKING
**Mode entry:** DEC-0197 (handing a task to Taktus)
**Raised in:** the session that took up the milestones `0.1.0` to `0.3.0`, on 2026-10-23
**Issue:** none; the owner answered in conversation
**Needed by:** 2026-10-23
**Written after the answer:** the owner answered in conversation on 2026-10-23; left out of the acceptance rate (DEC-0042).

## 1. What this is about

Under P-03 version 22 on rc.28, #394's run ended when its agent called `bash`, which the coding worker did not know in that case (#559, fixed in rc.29). #325's ended waiting for a pipeline that hung. The instance runs rc.29 since 2026-10-23.

## 2. Why you are being asked

Handing a task to Taktus is the owner's (DEC-0197).

**Sources checked:** DEC-0205, DEC-0217.

## 3. What you must decide

Whether #325 and #394 go to Taktus again.

## 4. What you need to know to decide

A run of either also measures #324's pod starts after the release.

## 5. Options

### Option A — hand both again (recommended)

### Option B — the session takes them

## 6. What is blocked

#325, #394, and #324's measurement.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-10-23
**Answer:** Option A. "Passt. Mach weiter." (the owner's words: fine, go on), to the session's question whether #325 and #394 go to Taktus again with rc.29, and to its offer to go on with the backlog.
**Reasoning given:** none beyond the recommendation.
**What it changes:**

- #325 and #394 are handed to Taktus again, after their failed attempts' branches are deleted (DEC-0205).
- Their runs measure #324's pod starts per worker step after the release.

**Recorded in:** this pull request
