---
id: UC-9.6
title: Introduced into a running operation in stages, each opened on evidence
component: value
serves: [P6, P10, P12, P14]
state: specified
version: 0.5.0
tests: []
adrs: {ADR-0026: ccc4bd1f5423}
supersedes: null
---

# UC-9.6 — Introduced into a running operation in stages, each opened on evidence

## 1. What must be achieved

No business switches its operation over to Taktus in one step. It runs today, with people and
tools, and it must keep running while Taktus takes over. The safe way is in stages: first Taktus
only watches and reports, then it carries the routine without handwork, then it speaks to
customers, then it releases, then it develops, and at last the business runs without staff in
normal operation.

Taktus carries that path. A tenant declares its stages: which processes each adds, at which
level, and the condition under which the stage holds. A stage opens only when the previous one
measurably holds. A stage that stops holding is reported, and what it raised falls back by
rule. The business sees at any time which stage it is in, what the next one needs, and what is
missing.

## 2. How it is verified

- A tenant can declare an ordered list of stages. Each names the processes and levels it adds,
  and its holding condition as a rule over the ledger: runs, weeks, missed runs, correction
  rates, incidents.
- A process that belongs to a stage not yet open cannot be raised above level 2. A test tries
  and finds it refused, naming the stage and its unmet condition.
- Opening a stage needs both: its predecessor's condition holds, and a person approves. Taktus
  proposes the opening with the figures; it never opens a stage by itself.
- A stage whose condition stops holding is reported to the tenant's responsible role. The
  processes it raised fall back by rule as UC-7.5 says, and the stage is shown as no longer
  holding.
- The stage view shows, per stage, its condition, the figures it reads, and what is missing,
  computed from the ledger, never entered by hand.
- A holding condition can be made stricter by the tenant and is never looser than the blueprint
  it comes from says.
- Throughout, every process can be taken over by a person (UC-6.3). A stage is never opened while
  a process it adds has no current takeover instructions.
- Stages, conditions and figures name processes and roles, never a person (principle 14).

## 3. Where the boundary lies

**Not change management.** How people are brought along is the business's (UC-9.2). **Not the
stages' content.** Which processes a business introduces when is its decision; the blueprint
proposes an order (UC-03 §5). **Not a promise of the last stage.** A business may stay at any
stage, and the view says why.

## 4. What it rests on

The path in six stages of the catalogue behind UC-03, and the owner's answer that Taktus covers
"den Übergang" (DEC-0199); UC-03 §5; NTC-0210. Steering the transformation (UC-9.2); the
autonomy range and its raise (UC-7.1, ADR-0026); corrections and the fall by rule (UC-7.5); the
takeover test (UC-6.3).
