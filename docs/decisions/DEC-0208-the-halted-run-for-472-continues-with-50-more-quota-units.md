# DEC-0208 — The halted run for #472 continues with 50 more quota units

**Category:** NON-BLOCKING
**Mode entry:** M3.10 (raising a limit)
**Raised in:** the session that took up the milestones `0.1.0` to `0.3.0`, on 2026-10-16
**Issue:** none; the owner answered in conversation
**Needed by:** 2026-10-17
**Written after the answer:** the owner answered in conversation on 2026-10-16; left out of the acceptance rate (DEC-0042).

## 1. What this is about

P-03's run for #472 (`run_d2b27d6c6da10cd91e77`, version 13) halted with cause `limit` before it waited for its pipeline:

- its branch took 26 quota units to write instead of the usual 12;
- the wait then reserved 162 units, its worst case, with 161 left of the run's 200.

P-03 version 14 halves that reservation (#489), but this run stays on version 13.

## 2. Why you are being asked

Raising a limit is the owner's (M3.10). DEC-0202 leaves the continuation of a halted run to a person each time.

**Sources checked:** DEC-0202, DEC-0203 (P-03's USD 5, money only), #458 (raises money only), M3.10.

## 3. What you must decide

Whether the run continues with its quota raised, or is left and #472 handed over again.

## 4. What you need to know to decide

Quota units are calls to the repository host's interface; they cost no money. The run has done its coding step, about USD 1, and pushed its branch.

## 5. Options

### Option A — raise the run's quota by 50 units and continue it (recommended)

`taktusctl resume` gains `--raise-quota`, held to a ceiling as `--raise` is.

### Option B — leave it, give its claim back, hand #472 over again

The coding step is paid a second time.

## 6. What is blocked

#472.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-10-16
**Answer:** Option A. "#472 Option A, mach weiter" (the owner's words: #472 Option A, go on).
**Reasoning given:** none beyond the recommendation.
**What it changes:**

- `taktusctl resume` gains `--raise-quota UNITS`, held to `TAKTUS_RAISE_CEILING_QUOTA`.
- The session raises the run's quota by 50 units and continues it.

**Recorded in:** this pull request
