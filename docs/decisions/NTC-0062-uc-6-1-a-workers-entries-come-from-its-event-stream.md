# NTC-0062 — UC-6.1: a worker's entries come from its event stream

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-09
**Raised in:** [#136](https://github.com/Jersyfi/taktus/pull/136)
**How it follows:** the owner's project definition, version 2, UC-6.1: the activity log is "fed from the event stream of the workers (UC-14.1)". The amendment writes that as a condition of UC-6.1 and adds nothing beyond it; the shape of the entries it names is the one the use case already requires of every entry.

## 1. What was decided

`docs/usecases/ledger/UC-6.1-the-complete-activity-log.md` gains a requirement. Section 1 says that
what a worker does is recorded from the stream of events the worker reports as it works. Section 2
gains the condition: for a step a worker runs, the entries of what the worker did are fed from the
worker's event stream (UC-14.1), in the shape every other entry has — identifiers, tokens and
digests, no text. "Proven so far" says that no named test proves it yet. Section 4 names the worker
interface.

## 2. The evidence

- Definition version 2, UC-6.1, as quoted above. Version 2 added the event stream and the export as
  a telemetry signal; the export was restored on 2026-10-01 (NTC-0015), the event stream was not.
- The worker contract already streams events (`contracts/worker/v1`, ADR-0007), and UC-14.1 requires
  it of every worker.
- The migration's fourth step re-read every use case of `ledger` and `reporting` against version 2
  (issue #63).

## 3. What was considered

- **Leaving it to UC-14.1.** Rejected: UC-14.1 requires that a worker streams events; nothing required
  that the log is fed from them, which is what the definition asks of the log.
- **Asking it in DEC-0087.** Rejected: the condition adds nothing the definition does not ask.
  DEC-0041 makes restoring the session's.

## 4. Which entry permits it

M2.7, *"Bringing a use case up to the owner's own definition: an amendment of what a use case
requires that only restores what `docs/vision/` and the owner's project definition already
require."* The amendment restores definition UC-6.1 and adds nothing beyond it.
