# DEC-0054 — A need's check claimed more than it shows

**Category:** DEFECT
**Raised in:** [#96](https://github.com/Jersyfi/taktus/pull/96), while confirming NEED-0006
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

Section 7 of NEED-0002 and NEED-0006 says how the owner and a session confirm the repository
token without revealing it: read this repository with the token, and `200` "means the token
reaches the repository". A wrong token is refused with `401`, so the check does catch an invalid
token. But the repository is public: any token the service accepts reads it, whichever
repositories the token is scoped to. A valid token for another repository answers `200` too.

## 2. Why you are being asked

You are not. The repository says something that is not so, which is entry M1.4 of
`docs/decisions/anchors.taktus.md`.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

- Both sections now say what the `200` shows — the service accepts the token — and that whether
  it reaches this repository is the scope check in the service's token settings, which only the
  owner can see.
- The confirmation of 2026-09-23 under NEED-0002 holds: the first run wrote to the repository
  with the token. NEED-0006 was confirmed on 2026-10-08 with the authenticated rate limit and the
  repository permissions the read returned.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0054" in an issue.

## Outcome

**Corrected:** 2026-10-08
**What was wrong:** the token check said that `200` means the token reaches the repository; on a
public repository it means only that the token is valid.
**Why it was wrong:** the sentence was written without the repository's visibility in mind.
**What it now says:** `200` means the service accepts the token; whether it reaches this
repository is the scope check in the token's settings.
**What changed in substance:** nothing in the software; the confirmation step of two records.
**Recorded in:** [#96](https://github.com/Jersyfi/taktus/pull/96)
