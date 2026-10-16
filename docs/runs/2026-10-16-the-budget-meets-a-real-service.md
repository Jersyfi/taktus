# The budget meets a real service — 2026-10-16

The live run of #74: the first two rows of *What the next live run must measure*
(`docs/runs/README.md`). It ran on the instance, under a budget of USD 5 the owner set for it
(DEC-0206, in place of DEC-0053's USD 3). It spent **USD 4.69**.

## Row 1 — the budget under the margin

Measured on a full run of P-03 version 13 on the instance, the run for #256 (`run_8b017d0cc963727029de`, 2026-10-16). It finished, and its pull request #470 was merged.

| Step | Estimate | Reservation | Actual | Inside |
|---|---|---|---|---|
| `implement` (coding worker) | USD 1.00 | calibrated from the worker's history: USD 4.12 (the figure the next run's admission named) | USD 0.62 | yes |
| `create-branch` | 64 quota units | 64 | 12 | yes |
| `wait-for-pipeline` | 162 units, its worst case | 162 | 26 | yes |
| `open-pr` | 3 units | 3 | 2 | yes |

The run used 60 quota units and USD 0.6212 in all (`taktusctl cost`). Every actual stayed inside its reservation. The margin was wide:

- the coding step reserved about 6.6 times what it used;
- the wait reserved 6.2 times what it used.

The second of these made the next run for #472 halt one unit short of its wait. P-03 version 14 polls once a minute and halves that reservation (#489).

## Row 2 — a halt at a boundary on a real reservation

`run_d59db1876a4b8641c65c`, process `p03-limit-check@1`, a copy of P-03 version 14 with no trigger and a money limit of USD 0.30, on #481. The row asked for a token limit, "so that the halt does not depend on the worker reporting money only at the end". Since DEC-0202 the coding worker prices every step and halts on money at its next boundary (ADR-0005, seventh amendment). So the halt was taken on money, the limit P-03 actually runs under.

1. **At USD 0.30 the coding step was refused at admission**: its estimate of USD 1.00 did not fit. The run halted with cause `limit` before the step started.
2. **The limit was raised to USD 1.05** with `taktusctl resume --run … --raise 0.75 --reason …` (#458). The ledger shows:
   - a second `budget.set`, whose statement holds the limit before and the reason;
   - no version registered;
   - the step admitted with a `capped` reservation, the run's remaining money.
3. **The coding worker halted at its boundary.** The step ended `stopped` with its checkpoint, having used USD 1.0506 against USD 1.05. The overshoot of USD 0.0006 is the one step ADR-0005 allows. The run halted with cause `limit`. This is the worker's `assignment.finished` with `limit`, and the work of the step was kept.
4. **The limit was raised to USD 5**, the limit P-03 runs under, and the run resumed. The step was admitted again after `step.waited halted_at_limit` and continued from its checkpoint: the resumed assignment started from the same workspace and session.
5. **The continued step failed on its unit's wall clock**, not on its money: "the execution unit was killed: the wall-clock limit of 3600s was exceeded". It had used USD 3.64 more, with 4.6 million tokens read from the cache against 1,075 written. The agent spent its hour mostly reading the output of what it ran. That is a finding of its own (#493), not of the budget: the halt, the raise and the resume did what they promise.

The run's ledger chain is intact; `taktusctl cost` read it whole.

## What is not measured here

- **Admission against real free capacity** and **the rehearsal**: rows 3 and 4, part 2 of the live run.
- **A resumed step that finishes.** The resumed step of row 2 failed on the wall clock before it finished. The resume itself, from the checkpoint, is shown by the ledger; a finished step after a resume is still to be seen on a real service.

## Spend

| What | USD |
|---|---|
| `run_797eaf7d2abec09b62f0`, refused by the provider's workspace limit (NEED-0030) | 0.00 |
| `run_d59db1876a4b8641c65c` until the halt at its boundary | 1.05 |
| the same run after the resume, until the wall clock | 3.64 |
| **total, of the USD 5 DEC-0206 set** | **4.69** |
