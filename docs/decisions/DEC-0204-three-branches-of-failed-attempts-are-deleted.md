# DEC-0204 — Three branches of failed attempts are deleted

**Category:** NON-BLOCKING
**Mode entry:** CLAUDE.md §9 (never delete without asking)
**Raised in:** the session that took up the milestones `0.1.0` to `0.3.0`, on 2026-10-15
**Issue:** none; the owner answered in conversation
**Needed by:** 2026-10-16
**Written after the answer:** the owner answered in conversation on 2026-10-16; left out of the acceptance rate (DEC-0042).

## 1. What this is about

Three branches of Taktus's app were left by attempts that failed or were closed: `taktus/issue-256` (red pipeline, 2026-10-14; it made the re-handed run for #256 fail after paying for its coding step), `taktus/issue-388` (the duplicate #415, closed) and `taktus/issue-396` (red pipeline). Since ADR-0099 a run refuses a branch it did not make before it spends, so #256 cannot run again while its old branch stays.

## 2. Why you are being asked

Deleting is the owner's (CLAUDE.md §9).

**Sources checked:** CLAUDE.md §9, DEC-0196 (stale claims), ADR-0099; none deletes branches.

## 3. What you must decide

Whether the three branches are deleted.

## 4. What you need to know to decide

Each belongs to a closed or given-back attempt; the issues and the pull request #415 keep their record.

## 5. Options

### Option A — delete the three branches (recommended)

### Option B — keep them; #256 stays blocked

## 6. What is blocked

#256's next handover.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-10-16
**Answer:** Option A. "Ja, lösch die drei Branches und mach weiter." (the owner's words: yes, delete the three branches and go on).
**Reasoning given:** none.
**What it changes:** the session deletes `taktus/issue-256`, `taktus/issue-388` and `taktus/issue-396` and hands #256 to Taktus again.
**Recorded in:** this pull request
