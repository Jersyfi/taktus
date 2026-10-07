# DEC-0043 — DEC-0034's readings, confirmed and extended

**Category:** NON-BLOCKING
**Raised in:** the report of #51, 2026-10-01, which asked the owner in a sentence to confirm two readings — a request written as a note, the fifth instance of the pattern; recorded in [#52](https://github.com/Jersyfi/taktus/pull/52)
**Issue:** none; the owner decided before a request was written, and this record is the question with his answer
**Needed by:** 2026-10-01
**Written after the answer:** the owner answered in the audit's brief of 2026-10-01; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

DEC-0034 answered how much a worker without calibration history reserves: its estimate plus
100 %. Building it, the session read two further points into the answer and asked the owner, in
a sentence of a report, to confirm them: the margin narrows with every observation, and a
stopped step is no calibration history. A question asked in a report sentence is a request
written as a note.

## 2. Why you are being asked

A safety margin is the owner's (M3.10); DEC-0034 is his answer, and its readings are his to
confirm.

## 3. What you must decide

Whether the two readings hold, and what more the margin needs.

## 4. What you need to know to decide

- **The first reading.** After n observations the margin is 1/(n+1) of the initial 100 %, and a
  worker whose measured error is larger reserves that instead.
- **The second reading.** A stopped step used part of its estimate; read as history it would
  look like an overestimate.

## 5. Options

### Option A — confirm both, and extend (recommended)

- **Meaning:** both readings hold; the margin never falls below 10 %; a worker's history resets
  when its model version changes.
- **Consequence:** the reservation stays cautious with a new model.
- **Effort:** the budget's rules and their tests.
- **Reversibility:** cheap.
- **Why recommended:** the owner's answer, below.

### Option B — confirm both as they are

- **Meaning:** no floor, no reset.
- **Consequence:** after many observations the margin approaches nothing, and a model change
  keeps a calibration that says nothing about the new model.
- **Effort:** none.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing.

## 7. How to answer

"DEC-0043: Option A." or "DEC-0043: Option B."

## Outcome

**Decided:** 2026-10-01
**Answer:** Option A, as the owner gave it. Confirmed: the margin narrows to 1/(n+1) of the
initial 100 % after n observations, and a larger measured error still wins. Confirmed: stopped
steps do not count as history. Added: the margin never falls below 10 %. Added: a worker's
history resets when its model version changes.
**Reasoning given:** a calibration for one model says nothing about the next. The request for
confirmation had been written as a sentence in a report — the fifth instance of a request
written as a note — and is recorded here properly.
**Recorded in:** [#52](https://github.com/Jersyfi/taktus/pull/52):
`src/taktus/components/run/domain/service/budget.py` (the floor, the reset), ADR-0005 third
amendment point 6, `anchors.taktus.md`. As built, observations never narrow the margin below
10 %; an operator who sets `TAKTUS_BUDGET_UNCALIBRATED_MARGIN` itself below 10 % has set a
smaller limit and it holds, because that setting is itself a limit (M3.10). The model version is
the one the step's estimate names, else the one the worker last reported; an observation that
names no model is no evidence of a change.
