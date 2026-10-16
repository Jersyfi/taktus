# DEC-0205 — A failed attempt's branch is deleted when its task is handed again

**Category:** NON-BLOCKING
**Mode entry:** CLAUDE.md §9 (never delete without asking)
**Raised in:** the session that took up the milestones `0.1.0` to `0.3.0`, on 2026-10-16
**Issue:** none; the owner answered in conversation
**Needed by:** 2026-10-16
**Written after the answer:** the owner answered in conversation on 2026-10-16; left out of the acceptance rate (DEC-0042).

## 1. What this is about

A run of P-03 that is given back leaves its branch `taktus/issue-<n>`. Since ADR-0099 the next run for the same task stops before it spends while that branch is not its own. The attempt of 2026-10-16 for #256 left one again, after DEC-0204 had deleted the earlier one.

## 2. Why you are being asked

Deleting is the owner's (CLAUDE.md §9). DEC-0204 named three branches, not a rule.

**Sources checked:** CLAUDE.md §9, DEC-0196, DEC-0197, DEC-0204, ADR-0097, ADR-0099; none deletes a branch left later.

## 3. What you must decide

Whether a session may delete such a branch without asking each time.

## 4. What you need to know to decide

The issue keeps the attempt's record: Taktus's comment giving the claim back names the reason. Without the rule every retry waits for a question.

## 5. Options

### Option A — a standing rule (recommended)

When a task is handed to Taktus again, the session may delete the branch Taktus's app left from an earlier attempt, if Taktus gave the claim back and no open pull request comes from that branch.

### Option B — ask for every branch

## 6. What is blocked

#256's next handover.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-10-16
**Answer:** Option A. "Ja, Regel passt, lösch den Branch und übergib #256 neu." (the owner's words: yes, the rule is fine, delete the branch and hand #256 over again).
**Reasoning given:** none.
**What it changes:** a session handing a task to Taktus again deletes the branch of its given-back attempt under the two conditions above; it deletes `taktus/issue-256` now and hands #256 over again.
**Recorded in:** this pull request
