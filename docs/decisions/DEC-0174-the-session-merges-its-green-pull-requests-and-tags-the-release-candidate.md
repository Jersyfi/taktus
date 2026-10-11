# DEC-0174 — The session merges its green pull requests and tags the release candidate

**Category:** NON-BLOCKING
**Mode entry:** M3.6
**Raised in:** the session of 2026-10-11 that takes up the milestones `0.1.0` to `0.3.0`; recorded in the pull request that records the owner's answers of that evening
**Issue:** none; the owner answered in conversation before a request was written, and this record is the question with the answer
**Needed by:** 2026-10-11
**Written after the answer:** the owner answered in conversation on 2026-10-11; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

The owner asked the session to bring the milestones `0.1.0`, `0.2.0` and `0.3.0` as far as it
can by the evening of 2026-10-12, working overnight without the owner. Several tasks build on
each other: the backup (#67) must be in a release before the instance can run it, and the
install's last check (#66) comes before the live run on the instance (#75) and before Taktus runs
its own processes there (#87). The standing brief stops at a green pull request, because merging
is the owner's (`docs/process/next-task.md` §4), and preparing a release is the owner's (M3.6).
A session that may do neither waits for the owner at every step.

## 2. Why you are being asked

Merging and tagging a release are the owner's under the brief and under M3.6. Only the owner can
set that aside, and a brief that sets a rule aside says so (CLAUDE.md §9).

**Sources checked:** the standing brief §4 (merging is the owner's), M3.6 of both anchor pages
(preparing a release), ADR-0013 D (Taktus does not put itself into production — a version is
deployed by a person or another instance), and DEC-0051. None lets a session merge or tag.

## 3. What you must decide

May the session merge its own pull requests once every check is green, and tag the next release
candidate itself?

## 4. What you need to know to decide

- A merged pull request is on `main`; reverting it is a new pull request. A tag on `main` makes
  the image workflow build and push the release images; nothing is deployed by it (ADR-0013 D).
- Every gate and every check still runs; a pull request that is not green is not merged.
- Several merges in a row each start the whole pipeline; too many open at once make each wait.

## 5. Options

### Option A — for this push through the milestones, yes (recommended)

- **Meaning:** the session merges each of its pull requests for the milestones `0.1.0` to `0.3.0`
  once every check is green, keeps few open at once so that CI does not hold it up, and tags the
  release candidate that carries the backup image itself, this once.
- **Consequence:** the owner reviews after the merge instead of before; the brief is set aside
  for this work and stands otherwise.
- **Why recommended:** it lets the work continue unattended while every check still holds, and it is bounded to this work.

### Option B — no; the pull requests wait for the owner

### Option C — the owner's own wording

## 6. What is blocked

Without it, every task that needs another's merge or a release waits for the owner.

## 7. How to answer

"DEC-0174: Option A.", "DEC-0174: Option B." or the owner's own wording.

## Outcome

**Decided:** 2026-10-11
**Answer:** Option A. "This time you may create the tag for me." "You may merge green pull requests on your own. Make sure not too much runs in parallel, so that the CI runs do not block you." (the owner's words, translated).
**Reasoning given:** the owner's: the session is to work through the night and the next day for as long as it takes without needing the owner.
**What it does not change:** deploying a version stays a person's act or one the owner permits for the occasion (ADR-0013 D); the tag is this once; the brief's rule that merging is the owner's stands for every other task.
**Recorded in:** this pull request
