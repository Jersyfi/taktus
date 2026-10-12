# DEC-0184 — The session tags release candidates until the milestones close

**Category:** NON-BLOCKING
**Mode entry:** M3.6
**Raised in:** the session that takes up the milestones `0.1.0` to `0.3.0`, on 2026-10-12; recorded in the pull request of its own that records the answer
**Issue:** none; the owner answered in conversation before a request was written, and this record is the question with the answer
**Needed by:** 2026-10-12
**Written after the answer:** the owner answered in conversation on 2026-10-12; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

DEC-0174 let the session tag one release candidate, `v0.2.0-rc.4`, which carried the backup.
The installed instance then showed two things that need a release to reach it: the backup's
first seconds refused by the database (#266), and a worker's own service unreachable through
the egress proxy (the coding agent's provider). Each fix reaches the instance only with a tag.

## 2. Why you are being asked

Preparing a release is the owner's (M3.6); DEC-0174 allowed one tag.

**Sources checked:** M3.6 of both anchor pages, DEC-0174, DEC-0179, ADR-0013 D. None allows a
second tag.

## 3. What you must decide

May the session tag further release candidates while it works through the milestones?

## 4. What you need to know to decide

- A tag builds and pushes the release images; it deploys nothing (ADR-0013 D). Putting it into
  operation is DEC-0179's, with the deployment identity.
- A release candidate is not a release: `0.2.0` itself stays the owner's.

## 5. Options

### Option A — yes, release candidates, until the milestones close (recommended)

- **Meaning:** the session tags `v0.2.0-rc.5` and later candidates on `main` when a merged fix
  must reach the instance.
- **Why recommended:** without it every fix the instance needs waits for the owner.

### Option B — no; each tag stays the owner's

## 6. What is blocked

The fixes of #266 and of the worker's service hosts on the instance.

## 7. How to answer

"DEC-0184: Option A.", "DEC-0184: Option B." or the owner's own wording.

## Outcome

**Decided:** 2026-10-12
**Answer:** Option A. "You may tag rc.5 and further release candidates yourself." (the owner's words, translated).
**Reasoning given:** the owner's: the session is to work on until the milestones are done without needing the owner.
**What it does not change:** a release that is not a candidate — `v0.2.0` — stays the owner's (M3.6).
**Recorded in:** this pull request
