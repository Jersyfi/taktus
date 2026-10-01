# DEC-0038 — The first run's output token figures may be undercounted

**Category:** DEFECT
**Raised in:** PR_LINK, where the coding worker's token accounting was found and corrected
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

The record of the first live run (`docs/runs/first-run.md` §2) says the coding worker's output
estimate was too high by 30 to 70 times: it estimated 6,000 output tokens and measured 84 to 195.
The measurement came from the coding worker's own accounting, and that accounting had a fault.
The agent sends one message as several lines that share a message identifier. The worker counted
a message's usage once, on its first line. When that line carried only text, the tokens were
attached to no step, and the following line, with the tool call, was already counted and gave
nothing. Against the fake agent the worker reported zero tokens for every step.

The live run still reported 206,000 input tokens, so the real agent's stream differs in part. But
any message whose text came before its tool call was undercounted, and output is counted from the
first line only. The output figures of the record, and the claim drawn from them, may be too low.

## 2. Why you are being asked

You are not. The record states a measurement as true that may not be, which is entry M1.4 of
`docs/decisions/anchors.taktus.md`.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

- The worker now attributes a message's tokens to the next tool call, and a closing message that
  calls no tool to the step that reports; a test against the fake agent holds it.
- The record of the first run is not rewritten: it says what was measured then. It now carries a
  note beside the figures, pointing here.
- The seed calibration starts from (ADR-0005, third amendment) uses the input and money figures,
  which the fault touched less; for output it never scales below the estimate.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing. The next live run measures with the corrected accounting.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0038" in an issue.

## Outcome

**Corrected:** 2026-09-30
**What was wrong:** the first run's record states output token figures, and an estimate 30 to 70
times too high, measured by an accounting that counted a message's tokens once, on its first line.
**Why it was wrong:** the worker read the agent's stream as one line per message.
**What it now says:** the record marks the output figures as possibly undercounted and points
here; the worker's accounting is corrected.
**What changed in substance:** the coding worker's token accounting.
**Recorded in:** PR_LINK
