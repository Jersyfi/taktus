---
id: UC-7.5
title: Corrections are counted, and a level falls by rule
component: governance
serves: [P10, P12, P14]
state: specified
version: 0.4.0
tests: []
adrs: {ADR-0023: 949c6f4e13af, ADR-0026: ccc4bd1f5423, ADR-0039: c716494667e5}
supersedes: null
---

# UC-7.5 — Corrections are counted, and a level falls by rule

## 1. What must be achieved

At levels 1 and 2 a person sees every proposal before it acts. When the person changes it, that
change is the most precise evidence there is of how good the process is. It is lost if nobody
counts it.

Taktus counts it. Every proposal a person released unchanged, changed or rejected is recorded
as such, per process and per action class. The **correction rate** over 7 and 28 days is the
evidence a raise of level rests on (UC-7.1). Taktus proposes a raise when the tenant's
conditions are met: a number of runs, a span of weeks, a correction rate below a limit.

The way down needs no person. A process falls one level by rule on a breach of an anchor, or
when its correction rate rises beyond the tenant's limit. Lowering autonomy makes the system
safer, so it is never held for an approval.

## 2. How it is verified

- Every decision on a proposal records one of `released`, `corrected` or `rejected`, the
  process, the step, the action class and the time. A `corrected` decision keeps the proposal
  and the version the person released, so that the change can be seen.
- The correction rate per process and action class over 7 and 28 days is computed from these
  records by a rule, and is reproducible from the ledger.
- When the tenant's conditions for a raise hold, Taktus proposes the raise with the figures
  (ADR-0026). It never applies one (UC-7.1).
- A breach of an anchor by a process lowers that process one level at the next step boundary,
  raises an incident, and records the rule and the facts. A test makes a level-3 process breach
  an anchor and finds it at level 2 before its next step.
- A correction rate above the tenant's limit over its window lowers the process or the action
  class one level in the same way.
- The decision to lower is a rule over the records, never a model (ADR-0023). A level lowered
  by rule rises again only through UC-7.1: evidence and a person's approval.
- No figure names the person who corrected. Corrections are counted per process and action
  class, never per person, and no view ranks the people who released or corrected
  (principle 14).

## 3. Where the boundary lies

**Not the raise itself.** Raising stays with a person and with UC-7.1. **Not the quality of a
model.** Whether a model got worse is UC-4.18. **Not a judgement of a correction.** A person's
correction is taken as right; Taktus does not argue with it.

## 4. What it rests on

Requirement 2 of the catalogue behind UC-03 and its rule for rising and falling; UC-03 §3,
B-4.03, B-11.05; DEC-0199; NTC-0210. The autonomy range and the raise (UC-7.1, ADR-0026);
levels enforced at the step boundary (ADR-0039); a rule decides, never a probabilistic method
(ADR-0023). Its version is `0.4.0`, because the second tenant's first proposals are decided at
level 1–2 from that milestone, and their corrections must be counted from the first.
