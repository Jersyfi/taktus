# DEC-0242 — Every destination is shown in the navigation, none folded away

**Category:** NON-BLOCKING
**Mode entry:** M3 (what the product's interface shows), DEC-0239 item 3
**Raised in:** the session of 2026-11-15, by the owner's message in conversation
**Issue:** none; the owner answered in conversation
**Needed by:** 2026-11-15
**Written after the answer:** the owner stated it in conversation on 2026-11-15; left out of the acceptance rate (DEC-0042).

## 1. What this is about

ADR-0321 §1 showed the first entries of each navigation band and folded the rest of the band
under *More*.

## 2. Why you are being asked

How the web app is found one's way in was the owner's review of DEC-0239 item 3.

**Sources checked:** DEC-0239, ADR-0178, ADR-0321, UC-13.7. None decides whether entries are
folded.

## 3. What you must decide

Whether some entries of a band stay folded.

## 4. What you need to know to decide

The fold held ten of the 25 entries, chosen per band.

## 5. Options

### Option A — every entry shown (recommended)

### Option B — the fold as ADR-0321 built it

## 6. What is blocked

Nothing.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-11-15
**Answer:** Option A, in the owner's words: "Im der vertikalen Navigation hast du \"More...\"
eingeführt und bestimmte Menüpunkte damit raus gelassen. Das folgt keinem Muster und sollte dort
nicht vorhanden sein. Zeige alle Menüpunkte an."
**Reasoning given:** the fold follows no pattern.
**What it changes:** every destination is shown in its band; the fold is removed from
`web/src/lib/navigation.ts` and the frame; ADR-0321 §1 is amended.
**Recorded in:** this pull request
