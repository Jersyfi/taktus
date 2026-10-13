# DEC-0193 — The coding agent's limit of turns on the instance

**Category:** NON-BLOCKING
**Mode entry:** M3.10
**Raised in:** the pull request that raises this request, from the instance's P-03 runs of 2026-10-13
**Issue:** [#384](https://github.com/Jersyfi/taktus/issues/384)
**Needed by:** before #87's observation window starts, in which the instance implements the backlog on its own
**Provisional answer:** none is applied. The coding agent keeps its limit of 50 turns, and most P-03 runs on the instance fail at `implement`.

## 1. What this is about

P-03 is the process that turns a ready issue into a pull request. Its coding step hands the
issue to a coding agent in an isolated workspace. The worker starts the agent with a limit of
**turns**: how many times the agent may call the model, each time reading the workspace and
acting once. The limit is 50 (`workers/claudecode/worker.py`, `--max-turns`), and the instance
does not set another.

On 2026-10-12/13 the instance ran P-03 four times through to the coding step. One run, for #278,
finished within the limit and became pull request #373. Three ended on it: #282, #279 and #277,
each after 3.4 to 3.7 million input tokens and some 50 changes, "the agent ended with
error_max_turns after 51 turn(s)". The work they did up to there was lost: the step failed and
the run escalated. The run's money limit was never near: P-03 allows USD 5 per run, and the
successful run used USD 1.26 for its coding step.

## 2. Why you are being asked

Entry M3.10 of `docs/decisions/anchors.taktus.md`: "Raising or lowering a limit: a budget, a
quota, a compute bound, a safety margin". A limit of turns bounds compute.

**Sources checked:** the vision (`docs/vision/`) — principle 8 (repeatability and cost
control) asks for limits that hold, not for a number. The anchor pages keep limits with you
(M3.10). ADR-0005 makes the run's budget the limit that holds money; the limit of turns is
the agent's own and no ADR sets it. DEC-0019 chose the model, not the turns. No earlier
decision sets the agent's turns.

## 3. What you must decide

Whether the instance's coding agent gets more turns, or keeps 50 and stops at its last
boundary instead of failing (#380, not built yet).

## 4. What you need to know to decide

- **What a turn costs.** The three failed runs used about 70 000 input tokens per turn, most of
  them read from the provider's cache, and a few output tokens. With the model of DEC-0019 that
  is a few cents per turn; the successful run's 2.3 million tokens cost USD 1.26.
- **What still bounds the money.** The run's budget of USD 5, and the coding step's
  reservation, which the worker must stay inside: it halts at its next boundary before it
  would cross it (ADR-0005, W-14). More turns cannot spend more than that.
- **What changes.** A setting of the coding worker's unit on the instance, through the
  operator's values (`execution.defaults.unitEnv`, ADR-0090), once the worker reads its limit
  from there. That reading is a small change the session builds; the number is yours.
- **#380** makes a run that reaches the limit stop at its last boundary and halt, so that a
  person resumes it with another 50 turns. It keeps the limit and costs a person's resume per
  50 turns.

## 5. Options

### Option A — 150 turns (recommended)

- **Meaning:** the instance's coding agent may take up to 150 turns per assignment.
- **Consequence:** the three issues that failed would very likely have finished; the money
  stays held by the run's budget.
- **Effort:** a setting the session builds, and one line in the operator's values.
- **Reversibility:** cheap: a later value lowers it.
- **Why recommended:** the budget already holds the money; a second, lower bound on turns only
  turns finished work into lost work.

### Option B — 50 turns, and #380 first

- **Meaning:** the limit stays; a run that reaches it stops at its boundary and waits for a
  person to resume it.
- **Consequence:** no work is lost, but every 50 turns needs a person.
- **Effort:** #380 is a change of the worker and possibly of its contract.
- **Reversibility:** cheap.

### Option C — 100 turns, and #380 later

- **Meaning:** a middle value now.
- **Consequence:** fewer failures than today, more than with A.
- **Effort and reversibility:** as A.

## 6. What is blocked

Most of P-03 on the instance: three of its four coding steps ended on the limit. Issue #87's
two weeks, in which the instance implements the backlog on its own, cannot start well before.

## 7. How to answer

"DEC-0193: Option A.", "DEC-0193: Option B." or "DEC-0193: Option C." — in issue
[#384](https://github.com/Jersyfi/taktus/issues/384). A free-text answer is read back as an
interpretation and confirmed before it is acted on.

## Outcome

**Decided:** 2026-10-13
**Answer:** Option A. "DEC-0193: Option A." (the owner's words, in conversation).
**Reasoning given:** none beyond the recommendation.
**What it changes:** the instance's coding agent may take up to 150 turns per assignment. The coding worker reads its limit from a setting of its unit, which the operator sets through `execution.defaults.unitEnv` (ADR-0090); the product's default stays 50.
**Recorded in:** this pull request
