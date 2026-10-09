---
id: UC-6.6
title: The proof of value
component: value
epic: E6
serves: [P7, P8, P14]
state: specified
version: 0.5.0
tests: []
adrs: {ADR-0006: 4ef70c98354b, ADR-0010: 6b161e3f6831, ADR-0015: 3a42705e5561, ADR-0021: 202e0442e7ec, ADR-0029: 37c061ef032a}
supersedes: null
---

# UC-6.6 — The proof of value

## 1. What must be achieved

Management, the executive and investors can see from the data what Taktus is worth to the
organisation: working time saved, errors avoided, the cost of an automated case against the cost of
the same case done by hand, and when the investment pays for itself.

The figures are methodically traceable. They are not marketing figures. They can be exported for a
board report.

## 2. How it is verified

- Every figure of the proof of value names its method and its data basis: which runs, which period,
  which cost rates, which comparison. A reader can follow it from the figure to the records it was
  computed from.
- A figure is computed from records — the ledger, consumption and the value ledger — never typed in.
  Where a figure rests on an assumption, such as the time a case took by hand before automation, the
  assumption is shown beside it with who set it and when, and the figure is marked as resting on it.
- Time saved and cost by hand are computed from the revert analysis of each process (UC-9.3), the same
  figures the value balance shows; there is one definition of each (ADR-0029).
- An error avoided is counted only where a check that ran found it, or a result defect was caught
  before it left the system (ADR-0021); an error that merely could have happened is not counted.
- Every figure of the proof of value is in the export (UC-5.7), with its method and data basis.
- No figure is broken down by named person (principle 14). Personnel cost rates are rates per role,
  never per person.

## 3. Where the boundary lies

**Not a forecast.** The proof of value says what happened; what a change would bring is the value
balance's revert analysis and the marginal value of ADR-0015. **Not an audit opinion.** The figures
are traceable so that an auditor can check them; Taktus does not certify them. **Not the view.** Who
sees the proof of value is UC-6.4; ADR-0029 files the figures here and the view with them.

## 4. What it rests on

The `value` component, which owns the value ledger (`docs/architecture/project-structure.md` §1), and
ADR-0029, which files the proof of value with its figures; the value balance and its revert analysis
(UC-9.3); the ledger as the single source of every metric (ADR-0006); consumption in Takt and money
(ADR-0010); result defects caught before they leave (ADR-0021); export (UC-5.7). Definition `UC-6.6`.
The roadmap's `0.5.0`, *value and dependency measurable*.
