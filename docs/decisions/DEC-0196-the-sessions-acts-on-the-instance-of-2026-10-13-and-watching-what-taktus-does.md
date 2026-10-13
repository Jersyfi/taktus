# DEC-0196 — The session's acts on the instance of 2026-10-13, and watching what Taktus does

**Category:** NON-BLOCKING
**Mode entry:** M3.10, M4 (the instance's state and the owner's money)
**Raised in:** the session that took up the milestones `0.1.0` to `0.3.0`, on 2026-10-13; recorded in the pull request of its own that records the answers
**Issue:** none; the owner answered in conversation, and this record is the questions with the answers
**Needed by:** 2026-10-13
**Written after the answer:** the owner answered in conversation on 2026-10-13; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

The session's report of 2026-10-13 put five things to the owner beside DEC-0192 and DEC-0193:

1. Failed P-03 runs on the instance left Taktus's app's claim, the label `in-progress`, on
   issues nobody works on. Other sessions pass them over. Removing labels on issues other
   sessions wrote was refused to the session by its own permission check.
2. The instance's stored `p03-implementation@6` was overwritten with later content (#377). The
   runs of 2026-10-12/13 that name it ran the content of commit a67a040. Writing that back is a
   restore, which CLAUDE.md §9 keeps with the owner.
3. #74 still needs its second run: P-03 with its token limit below what the first used, which
   halts at a boundary and resumes. DEC-0053 capped the live runs of #74 at USD 3.
4. How the owner sees what Taktus does on its own instance, now that it takes up tasks itself.

## 2. Why you are being asked

A restore and the instance's state are the owner's (CLAUDE.md §9, DEC-0179 for the instance);
money beyond DEC-0053's cap is a limit (M3.10).

**Sources checked:** CLAUDE.md §9, DEC-0053, DEC-0174, DEC-0179, DEC-0184; none covers these.

## 3. What you must decide

Whether the session may remove the stale claims, restore the version, and spend for #74; and
how what Taktus does is watched.

## 4. What you need to know to decide

Stated in the session's report of 2026-10-13 and in #377 and #74.

## 5. Options

### Option A — allow the three acts; the session proposes how to watch (recommended)

- **Meaning:** the session acts on the three; it proposes a routine for watching Taktus.
- **Why recommended:** each act repairs what a failed run or a defect left behind.

### Option B — the owner acts himself

- **Meaning:** the owner removes the labels, restores the version and runs #74's second run.

## 6. What is blocked

Other sessions pass over the claimed issues; the records of two runs name a version they did
not run; #74 cannot close.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-10-13
**Answer:** in the owner's words, translated:
1. "You may remove the bot's stale in-progress labels."
2. "You may reset p03-implementation@6 to the state of a67a040."
3. "Yes" to up to USD 3 more for #74, with the remark that Taktus has already caused further
   costs, which another session is looking into.
4. "I have no problem with Taktus trying to work on tasks itself, but we must watch the
   progress with a routine here in Claude, for example, so that we can always check what works
   and what does not. If you have another proposal, propose it."

**Reasoning given:** the owner's: Taktus may try tasks itself, as long as its progress is watched.
**What it changes:** the session removes the `in-progress` labels that Taktus's app set and no
run or pull request now carries; it writes the content of a67a040 back into the instance's
stored `p03-implementation@6`, recording what it replaced; it may spend up to USD 3 more on
#74's second run. Taktus may take up ready tasks on its own instance (#87) while its progress
is watched; how it is watched is proposed to the owner, and answered in a record of its own.
**What it does not change:** merging stays a person's (#87). The instance's spending outside
#74 is the other session's inquiry.
**Recorded in:** this pull request
