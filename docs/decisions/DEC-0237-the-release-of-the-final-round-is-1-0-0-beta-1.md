# DEC-0237 — The release of the final round is `1.0.0-beta.1`, and what only operation proves moves to a milestone of its own

**Category:** NON-BLOCKING
**Mode entry:** M3.3 (which version a requirement belongs to), M3.6 (preparing a release)
**Raised in:** the session of 2026-11-13, area of the final round (DEC-0236)
**Issue:** none; the owner answered in conversation
**Needed by:** 2026-11-13
**Written after the answer:** asked and answered in conversation on 2026-11-13.

## 1. What this is about

Two questions of the final round. Every tag so far was `v0.2.0-rc.N`, the last `rc.37`; `1.0.0`
itself waits for the licence (DEC-0236). And some open issues cannot be closed by a session,
because they need real operation, a person or elapsed time: #218, #405, #445, #87, #511, #393,
and parts of #402 and #440.

## 2. Why you are being asked

Naming a release is preparing it (M3.6); which milestone an item belongs to is M3.3.

**Sources checked:** DEC-0222 (the beta before 1.0.0), DEC-0228, `docs/roadmap.md` (*The road
to 1.0.0*), both anchor pages. None names the tag of the release before `1.0.0`, nor where items
proven only in operation go.

## 3. What you must decide

The tag of the release, and where the items go that only operation proves.

## 4. What you need to know to decide

A tag with a pre-release suffix is ordered before `1.0.0` by semantic versioning; the instance's
upgrade path accepts it.

## 5. Options

### Option A — `v1.0.0-beta.1`, and a milestone `beta-operation` (recommended)

The release is a pre-release named `v1.0.0-beta.1`; later ones count on. The issues that only
operation, a person or time can close move to a new milestone `beta-operation`, so that `1.0.0`
and `introduction` count as built.

### Option B — `v1.0.0-rc.1`, the issues stay in their milestones

### Option C — `v0.2.0-rc.38`, the issues closed with a reason

## 6. What is blocked

Nothing.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-11-13
**Answer:** Option A, as recommended, chosen by the owner in conversation: "v1.0.0-beta.1
(Empfohlen)" and "Neuer Meilenstein 'beta' (Empfohlen)".
**Reasoning given:** none beyond the recommendation.
**What it changes:**

1. **The release of the final round is tagged `v1.0.0-beta.1`** and published as a pre-release.
2. **A milestone `beta-operation` holds every issue whose remainder only operation, a person or
   time can give.** Each such issue states what was built and what operation must prove.

**Recorded in:** this pull request
