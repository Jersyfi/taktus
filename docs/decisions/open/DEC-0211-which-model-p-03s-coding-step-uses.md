# DEC-0211 — Which model P-03's coding step uses

**Category:** NON-BLOCKING
**Mode entry:** DEC-0200 (a model is chosen on a comparison, by the owner)
**Raised in:** the pull request that records the calibration of 2026-10-17
**Issue:** [#512](https://github.com/Jersyfi/taktus/issues/512)
**Needed by:** 2026-10-20
**Provisional answer:** none. The instance keeps the agent's default, Opus 5.5, until the answer.

## 1. What this is about

Stage 0 spends about USD 5.70 per merged pull request against USD 3 (DEC-0207, #511), so stage 1 cannot start and `0.2.0` cannot complete. P-03's coding step uses the agent's default model, Opus 5.5. The calibration DEC-0200 allowed ran on one fixed case on 2026-10-17 (`docs/runs/2026-10-17-the-coding-model-calibrated-on-one-fixed-case.md`). All three models solved the case, passed every check and test it touches, and tested the new step:

- Opus 5.5: USD 1.84;
- Sonnet 5.5: USD 0.47;
- Haiku 5.5: USD 0.33, reading three times what Sonnet read.

## 2. Why you are being asked

DEC-0200: a model is introduced or changed only on a comparison, and the choice is the owner's.

**Sources checked:**

- the vision: principle 8 (repeatability and cost control) asks for the cheaper method where it does the same job, and does not choose;
- the ADRs: ADR-0089 says where the coding agent's provider is configured, not which model;
- both anchor pages;
- the register: DEC-0200, DEC-0203, DEC-0207.

## 3. What you must decide

Which model P-03's coding step uses on the instance.

## 4. What you need to know to decide

- **Where the money goes.** It is mostly cached tokens read again at every call of the agent. Opus 5.5 and Sonnet 5.5 cost the same per such token, so Sonnet saves by needing fewer, and by its cheaper cache writes.
- **What one case does not show.** It is one case. A larger task may separate the models more. Haiku already needed three times the reading for this one.
- **How a choice is held.** It is set in the instance's unit environment (`CODING_AGENT_MODEL`), reversible in minutes. The worker's conformance and removal test run again after each change.

## 5. Options

### Option A — Sonnet 5.5, measured over the next ten tasks (recommended)

- **Meaning:** P-03 codes with Sonnet 5.5. Stage 0's money is measured again over the next ten handed tasks, against USD 3. Opus comes back for a task Sonnet fails twice.
- **Consequence:** about a quarter of the money per coding step on the case measured, with the same result.
- **Reversibility:** one setting.
- **Why recommended:** the same quality at a quarter of the price on the case measured, and the fewest tokens read.

### Option B — Haiku 5.5

- **Meaning:** P-03 codes with Haiku 5.5, measured the same way.
- **Consequence:** the cheapest per call, but the most calls; on larger tasks the reading grows with them.

### Option C — keep Opus 5.5

- **Meaning:** nothing changes; #511 is met another way, a slimmer brief (#407) first.
- **Consequence:** stage 0 stays above USD 3 until that lands.

## 6. What is blocked

Nothing is blocked; the instance runs on Opus meanwhile. Stage 0's money measure waits for the answer.

## 7. How to answer

In #512: "DEC-0211: Option A", "Option B" or "Option C".
