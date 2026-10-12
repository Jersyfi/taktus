# DEC-0192 — The quota of P-01 on the instance

**Category:** NON-BLOCKING
**Mode entry:** M3.10
**Raised in:** [#364](https://github.com/Jersyfi/taktus/pull/364), from the work on issue #75
**Issue:** [#363](https://github.com/Jersyfi/taktus/issues/363)
**Needed by:** before #87's observation window starts, in which the instance runs P-01 daily on its own
**Provisional answer:** none is applied. P-01 keeps its quota of 40 units, and every P-01 run on the instance halts at its second step until you answer.

## 1. What this is about

P-01 is the process that compares the roadmap with the backlog and reports the difference
as a comment on issue #129. It runs daily on the installed instance. Its budget is a
**quota**: a count of calls to the repository service, in units. The bundle gives it 40
units (`blueprints/dev-orchestration/processes/P-01-roadmap-control.yaml`, `limits`).

On 2026-10-13 the instance ran P-01 for real for the first time. The run read the roadmap,
then halted at its second step: "does not fit the remaining budget: 40.0 quota units needed,
37.0 left". It will halt there every time.

The reason is arithmetic. The step `read-issues` estimates 20 units: up to twenty pages of
issues. A step that has never run on the instance is not yet **calibrated**: the engine
reserves its estimate plus 100 % (this tenant's rule, M3.10 of the anchor page). So the step
alone reserves 40 units, the whole quota, and the first step already used 3. The quota was set
to 40 in NTC-0048 by adding up the estimates (2 + 20 + 2 + 3 = 27). The reserve for an
uncalibrated step was decided later and was not added. Because the step never runs, it
never becomes calibrated either.

## 2. Why you are being asked

Entry M3.10 of `docs/decisions/anchors.taktus.md`: "Raising or lowering a limit: a budget, a
quota, a compute bound, a safety margin". Raising P-01's quota is raising a limit.

**Sources checked:** the vision (`docs/vision/`) — principle 8 (repeatability and cost
control) asks for limits, not for a number. The anchor pages: both keep limits with you
(M3.10). ADR-0005 sets how reservations and the margin work, not the quota of a process.
NTC-0048 set the 40 units, as an addition of estimates; DEC-0034 set the default margin.
No earlier decision sets P-01's quota against the reserve for an uncalibrated step.

## 3. What you must decide

Which quota P-01 gets: 60 units, 80 units, or 40 units with a lower estimate for
`read-issues`.

## 4. What you need to know to decide

- **What a unit costs.** A unit is one call to the repository service under the app's own
  rate limit. It costs no money. The app may make thousands of calls per hour; P-01 makes a
  few dozen per day at most.
- **What P-01 actually used.** `read-roadmap` used 3 units. In P-03 on the same instance,
  reading every open issue used 1 unit, because one page holds them all today.
- **What the run needs at its worst.** 3 for the roadmap, 40 reserved for the issues (then
  about 1 used), 4 reserved for the records, 6 reserved for the comment. The peak is 43, at
  the moment `read-issues` is admitted. Once each step has run a few times its reserve
  shrinks (1/(n+1) of the estimate after n observations), and the run needs about 30.
- **What it changes.** Only P-01's bundle. A new version is registered on the instance. Past
  runs keep the budget they ran with.

## 5. Options

### Option A — 60 units (recommended)

- **Meaning:** P-01's quota becomes 60 units.
- **Consequence:** the first runs fit with 17 units to spare; later runs use about half.
- **Effort:** a one-line change of the bundle, and a new version on the instance.
- **Reversibility:** cheap: a later version lowers it again.
- **Why recommended:** it is the smallest round number above the worst case. It keeps the
  quota a real bound: a P-01 that reads twenty pages of issues and more would still be
  stopped.

### Option B — 80 units

- **Meaning:** P-01's quota becomes 80 units.
- **Consequence:** fits even if the roadmap and the records are read twice over.
- **Effort and reversibility:** as A.

### Option C — 40 units, and `read-issues` estimates 10 units

- **Meaning:** the quota stays; the step's estimate drops to ten pages.
- **Consequence:** it fits (3 + 20 reserved). A backlog of more than 1 000 open issues would
  no longer be read whole within the estimate.
- **Effort:** a one-line change. The estimate is not a limit, but it decides what the limit
  admits, so it is asked together.
- **Reversibility:** cheap.

## 6. What is blocked

P-01 on the instance. Every daily run halts at `read-issues` and is recorded as halted with
cause `limit`. Issue #87 needs P-01 to run there on its own.

## 7. How to answer

"DEC-0192: Option A.", "DEC-0192: Option B." or "DEC-0192: Option C." — in issue
[#363](https://github.com/Jersyfi/taktus/issues/363). A free-text answer is read back as an
interpretation and confirmed before it is acted on.
