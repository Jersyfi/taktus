# DEC-0050 — DEC-0037's Option A waits for its trigger

**Category:** NON-BLOCKING
**Raised in:** the description of [#52](https://github.com/Jersyfi/taktus/pull/52), which stated that DEC-0037's chosen option is not built and comes with `0.2.0`; recorded in PRNUM
**Issue:** none; the owner answered in the brief of 2026-10-07 before a request was written, and this record is the question with the answer
**Needed by:** 2026-10-07
**Written after the answer:** the owner answered in the brief of 2026-10-07; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

Every pull request description ends with a section a program generates. When Taktus opens a pull
request, that section is an input to the run today, supplied by the command a person uses to start
it. DEC-0037 settled where the section will come from once runs start on their own: the worker
runs the program after its change. The pull request that recorded it did not build that, and said
it would come with the automatic start of `0.2.0`.

## 2. Why you are being asked

When a feature lands is the session's (M1.7 of `anchors.taktus.md`). The deferral was stated in a
description, not decided in a record; the owner chose to confirm it.

**Sources checked:** the vision, the ADRs, both anchor pages (M1.7, M1.11) and the register
(DEC-0037). They make the timing the session's; this record carries the owner's confirmation.

## 3. What you must decide

Whether DEC-0037's Option A is built now or with the automatic start.

## 4. What you need to know to decide

- **The trigger.** A run that starts on an event — an issue marked ready — instead of a command.
  It does not exist yet; it is part of `0.2.0`.
- **Without the trigger** the manual command supplies the section, and the built option would
  serve nothing.

## 5. Options

### Option A — the deferral stands (recommended)

- **Meaning:** Option A of DEC-0037 is built with the automatic start of `0.2.0`.
- **Consequence:** nothing is built that nothing uses.
- **Effort:** none now.
- **Reversibility:** cheap.
- **Why recommended:** the owner's answer, below.

### Option B — build it now

- **Meaning:** the worker contract gains its command after the work before any run needs it.
- **Consequence:** about a day spent on code no run exercises.
- **Effort:** about a day.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing.

## 7. How to answer

"DEC-0050: Option A." or "DEC-0050: Option B."

## Outcome

**Decided:** 2026-10-07
**Answer:** Option A, as the owner gave it: the deferral stands. It stays listed for `0.2.0`.
**Reasoning given:** there is no trigger yet for the generator to serve.
**Recorded in:** PRNUM: the backlog issue BACKLOG_DEC37, milestone `0.2.0`, blocked by the issue
for event reactions.
