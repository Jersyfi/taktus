# DEC-0053 — The budget of the next live run

**Category:** NON-BLOCKING
**Raised in:** [#59](https://github.com/Jersyfi/taktus/pull/59), while building the backlog: the live run that proves the budget is a task, and its cost exceeds what a session may spend alone
**Issue:** [#60](https://github.com/Jersyfi/taktus/issues/60)
**Needed by:** 2026-10-20

## 1. What this is about

Three mechanisms were built after the last live run and have never met a real service: the budget
with its safety margin, a halt when a run reaches its limit, and two that need the deployed
instance. `docs/runs/README.md` lists what the next live run must measure. Two of its rows can be
measured now, on the owner's machine, with the credentials the owner already provided:

- **the budget under the new margin** — one full run of P-03 Implementation on a small ready
  issue: per step the estimate, the amount reserved, and what was actually used;
- **a halt at a boundary** — a second run of P-03 with its token limit set below what the first
  used. It must stop at the next step boundary with the limit as the cause, and continue from
  there when resumed with the old limit.

Those runs spend money on the coding agent's key. The first live run's coding step cost between
$0.45 and $1.08 an attempt (`docs/runs/first-run.md`), and the cost of the same work varied by a
factor of 2.4. A session may spend up to USD 1 per task on the owner's credentials without asking
(M2.8). These runs need more.

## 2. Why you are being asked

Entry M3.10 of `docs/decisions/anchors.taktus.md`: "Raising or lowering a limit: a budget, a
quota, a compute bound, a safety margin." The budget of a run is a limit, and M2.8 caps what a
session may spend alone at USD 1 per task; beyond that it is a request.

**Sources checked:** the vision (principle 8, cost control), the ADRs (ADR-0005 on budgets, which
says how a budget is enforced, not how large one is), both anchor pages (M2.8 caps a session at
USD 1 per task; M3.10 keeps every larger limit with the owner) and the register (DEC-0049 set the
cap; NTC-0018 spent under a cent; no record sets the budget of a live run).

## 3. What you must decide

How much the next live run on the owner's machine may spend in total, across its runs.

## 4. What you need to know to decide

- **What is spent.** Only the coding agent's key (NEED-0001, renewed under NEED-0005). The model
  step of P-02 costs under a cent. The repository's calls cost nothing.
- **The estimate.** One full P-03 run: $0.45 to $1.08, by the first run's eight attempts. The
  halted run stops early and costs less. Its resume finishes the work. In total about two full
  attempts: $1 to $2.20, and up to about $3 if this issue's change is larger than the first
  run's.
- **How the limit is held.** The run is started with the amount as its budget. The coding worker
  receives its share as its limits and halts at its next boundary before crossing them; money
  that the worker reports only at the end can overrun by at most the one step during which the
  line was crossed (ADR-0005, third amendment).
- **What it buys.** The first real evidence that the margin of DEC-0034 and DEC-0043 holds, and
  that a halt on a real reservation stops and resumes cleanly. Without it, both stay proven
  against fakes only.

## 5. Options

### Option A — USD 3 in total (recommended)

- **Meaning:** the session runs both rows, under a budget of USD 3 across all their runs, and
  records the actual cost in the run's record.
- **Consequence:** both rows are measured, with room for the variance the first run showed.
- **Effort:** half a day of a session, and the reading of one run record.
- **Reversibility:** money spent is spent; the cap bounds it.
- **Why recommended:** it covers both rows at the first run's worst case, and the budget itself is
  the mechanism under test.

### Option B — USD 1.50 in total

- **Meaning:** one full run only; the halt row waits for another budget.
- **Consequence:** the margin is measured; the halt on a real reservation stays unproven.
- **Effort:** a quarter of a day.
- **Reversibility:** as above.

### Option C — nothing now

- **Meaning:** the budget rows wait for the deployed instance and its own budget.
- **Consequence:** the mechanisms built on 2026-09-30 stay unproven against a real service at
  least until the deployment is installed.
- **Effort:** none.
- **Reversibility:** cheap.

## 6. What is blocked

The budget half of the next live run (its backlog issue names this request). Nothing else: the
deployment, the gates and every other task continue. Without an answer by 2026-10-20 the
provisional answer stands, and the rows are measured on the deployed instance instead, which
waits for NEED-0007 and NEED-0009.

## 7. How to answer

"DEC-0053: Option A.", "DEC-0053: Option B." or "DEC-0053: Option C." in the issue. A free-text
answer is read back as an interpretation and confirmed before it is acted on.

## Outcome

**Decided:** 2026-10-08
**Answer:** Option A: USD 3 in total for the runs of the next live run's budget half.
**Reasoning given:** none beyond accepting the recommendation; the recommendation's reason was
that USD 3 covers both rows at the first run's worst case.
**Recorded in:** [#97](https://github.com/Jersyfi/taktus/pull/97); backlog issue
[#74](https://github.com/Jersyfi/taktus/issues/74) is no longer blocked.
