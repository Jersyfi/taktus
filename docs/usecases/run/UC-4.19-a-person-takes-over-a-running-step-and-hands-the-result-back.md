---
id: UC-4.19
title: A person takes over a running step and hands the result back
component: run
epic: E4
serves: [P6, P10, P14]
state: specified
version: 0.5.0
tests: []
adrs: {ADR-0013: 1da224cdeaf4, ADR-0021: dc801ddd1c47}
supersedes: null
---

# UC-4.19 — A person takes over a running step and hands the result back

## 1. What must be achieved

A person can take a step out of Taktus's hands while it runs. They receive what the step had
reached, work it in their own tool, and hand the result back. The result then counts as the
person's, with the same record of its origin as any step has. Nobody works the step twice:
neither two people, nor a person and Taktus.

## 2. How it is verified

- The web app, the chat and the MCP surface offer "take over" on a running step.
- While a person holds the step, no runner executes it, even after a runner's lease has passed.
  A second take-over of the same run is refused.
- The step's worker stops at its next boundary. The state it reached reaches the person as an
  artifact: what the step was asked, what the worker produced so far, and its checkpoint.
- Handing back records the result as a step of method `human`. Its provenance names what the
  step read, and the ledger entry of the hand-back, which names the person, as its origin.
- A take-over that is not handed back in its time gives the step back to Taktus, which continues
  it from its checkpoint. A hand-back after that is refused and changes nothing.
- No measure is computed from take-overs per person.
- The automated takeover test of `0.5.0` exercises this path.

## 3. Where the boundary lies

**Not every method.** A step whose worker signals no inner boundary stops only at its own end.
A step that ends before it stops is not taken over. **Not the worker's own handover.** What a
worker hands over beyond its checkpoint is the worker contract's (#403). **Not a check of the
result.** The person is the authority for what they hand back. **Not the whole process.** Running
a process by hand without Taktus is UC-6.3.

## 4. What it rests on

Requirement B of ADR-0013; provenance per step (ADR-0021); the takeover instructions of UC-6.3;
steering a run (UC-1.5). The owner accepted it as W3 of DEC-0195, and issue #404 carries it. The
version is `0.5.0`, the milestone DEC-0195 places it in.
