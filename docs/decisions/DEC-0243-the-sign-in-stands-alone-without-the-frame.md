# DEC-0243 — The sign-in stands alone, without the frame

**Category:** NON-BLOCKING
**Mode entry:** M3 (what the product's interface shows), DEC-0239 item 3
**Raised in:** the session of 2026-11-15, by the owner's message in conversation
**Issue:** none; the owner answered in conversation
**Needed by:** 2026-11-15
**Written after the answer:** the owner stated it in conversation on 2026-11-15; left out of the acceptance rate (DEC-0042).

## 1. What this is about

A reader without a session saw the sign-in form inside the frame: the bar, the navigation column
and, on a phone, the bottom bar stood around it, although none of their destinations could be read.

## 2. Why you are being asked

How the web app presents itself was the owner's review of DEC-0239 item 3.

**Sources checked:** DEC-0239, ADR-0119 (the sign-in), ADR-0321, UC-13.7. None decides whether the
frame stands around the sign-in.

## 3. What you must decide

Whether the sign-in is shown inside the frame or alone.

## 4. What you need to know to decide

Every page shows the same form where the surface answers that the reader has no session.

## 5. Options

### Option A — the sign-in alone (recommended)

### Option B — the sign-in inside the frame, as built

## 6. What is blocked

Nothing.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-11-15
**Answer:** Option A, in the owner's words: "Der Signin sollte alleinstehend sein ohne, dass man
schon in der Applikation ist. Aktuell sieht man die Navigationsleiste Vertikal/Horizontal."
**Reasoning given:** a reader who is not signed in is not yet in the application.
**What it changes:** while a sign-in form is shown, the frame draws no bar, no navigation, no tabs
and no bottom bar; after signing in, the page and its frame return.
**Recorded in:** this pull request
