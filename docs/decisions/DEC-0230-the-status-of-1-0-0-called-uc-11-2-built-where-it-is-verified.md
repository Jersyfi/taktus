# DEC-0230 — The status of 1.0.0 called UC-11.2 built where it is verified

**Category:** DEFECT
**Raised in:** the pull request of release 1.0 (DEC-0228), area platform
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

`docs/status/1.0.0.md` named the data-protection requests as UC-11.2 `built`. The use case's
own file says `verified`, and `make gate-usecases` runs its named tests green. A reader of the
status was told less than the repository holds.

## 2. Why you are being asked

You are not. The repository contradicted itself: entry M1.4.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

The use case's file is what the gate holds; the status restates it and now says `verified`.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0230" in an issue.

## Outcome

**Corrected:** 2026-11-07
**What was wrong:** the status entry of #657 said UC-11.2 `built`.
**Why it was wrong:** the entry was written before the use case's state was raised, and was not carried along.
**What it now says:** UC-11.2 `verified`.
**What changed in substance:** nothing.
**Recorded in:** the pull request of release 1.0 (DEC-0228)
