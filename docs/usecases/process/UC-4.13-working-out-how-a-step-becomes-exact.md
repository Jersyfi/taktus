---
id: UC-4.13
title: Working out how a step becomes exact
component: process
epic: E4
serves: [P2, P8, P12]
state: specified
version: 0.5.0
tests: []
adrs: {ADR-0004: ffdb1f1537f5, ADR-0014: 6611f7833deb, ADR-0018: 17c99e0eaa3c}
supersedes: null
---

# UC-4.13 — Working out how a step becomes exact

## 1. What must be achieved

A person designs a process, or Taktus proposes one, and a step should be `exact`: a booking amount,
a payment, a tax code, a headcount. The class is not a switch that makes the value right. It is a
claim that a machine check makes it right, and the check has to exist and has to fit the business
(ADR-0014).

For every step that should be `exact`, before the process version is registered, Taktus works
through with the user how that is achievable, and proposes checks from a fixed catalogue. Each
proposal names the check, what it covers, what it does not cover, and what it needs:

| Check | What it covers | What it does not cover | Needs |
|---|---|---|---|
| **Reconciliation against a total** | the parts sum to a total another source holds: the invoice total, the bank statement, the payroll sum | a part wrong by an amount another part is wrong by in the other direction; a total that is itself wrong | a source for the total, read through a connector at the moment of the check |
| **Agreement with a second system** | the value equals what an independent system holds for the same thing | both systems wrong the same way; a second system fed from the first | a connector to the second system; a rule that says which one is the reference |
| **Plausibility bounds** | the value lies within bounds a rule states: a range, a sign, an order of magnitude, a ratio to the last period | a wrong value inside the bounds | the bounds, stated by the user or derived by a statistic from earlier results (UC-4.10) |
| **Approval above a threshold** | a value above a threshold is confirmed by a person before it counts | a wrong value below the threshold; a person who confirms without looking | a threshold and a decider — a `human` step, which produces no result of its own (ADR-0018) |
| **Sampling** | a stated share of results is checked by a person after the fact, and the error rate is measured | any single wrong result that was not in the sample | a share, a decider, and the value ledger to hold the rate |

The user chooses what fits their business. That is their reporting and approval regime, not
Taktus's: an organisation that reconciles against the bank statement daily and samples the rest has
made a choice Taktus records and enforces, not one it overrides. Where the user finds that no check
from the catalogue fits, the step is not `exact`; it goes to a person (`human`), or to `sourced`
with the check that does fit, and Taktus says which and why.

The outcome is written into the process version: the chosen checks, as `check` declarations on the
step (UC-4.10), and the exactness statement (UC-6.9).

## 2. How it is verified

- A bundle with an `exact` step and no check does not register, and the finding names the
  catalogue. Taktus refuses this one thing only: a step classed `exact` with no check at all is a
  promise without a mechanism.
- Every check in the catalogue has a fixture that passes and one that fails.
- A check's "does not cover" is exercised: a test slips a wrong value through the check and finds the
  residual risk stated (`tests/exactness`).
- Taktus never classes a step `exact` on its own: the class is the user's choice, recorded.
- No language model chooses the check. The catalogue is fixed, the choice is the user's, and the
  check itself is a `rule` or a `statistics` step.
- A check is never presented as covering more than its row says.

## 3. Where the boundary lies

**Not a guarantee.** A step with a check is as exact as the check, and the check's row says where it
ends; that is what the exactness statement (UC-6.9) carries to the reader. **Not an open
catalogue.** A check outside the five rows is a change of the catalogue, not a choice of the user.
**Not the conversation's channel.** When Taktus proposes the process, the conversation is a decision
request of class `domain` (`docs/architecture/governance.md` §3.1); when a person writes the bundle
by hand, it is a validation finding with the same content.

## 4. What it rests on

ADR-0014 and its boundary — `exact` means machine-checkable, and where no check can be formulated
`exact` is unreachable; ADR-0018 for steps that produce no result; method selection for the check's
own method (ADR-0004); the check declaration on a step (UC-4.10); connectors for reconciliation and
agreement; the decision request mechanism (UC-7.4, `0.2.0`); the catalogue as a fixed vocabulary in
the shared kernel. Written first in `UC-4-exactness-statement.md` on 2026-09-21, moved into this
format in the migration's second step; the requirement is unchanged. No version of the definition
has this use case. An earlier proposal called it `UC-4.8` (`NUMBERING.md`).
