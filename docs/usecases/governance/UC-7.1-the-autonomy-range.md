---
id: UC-7.1
title: The autonomy range, per process, action and risk class
component: governance
epic: E7
serves: [P10, P11, P12]
state: building
version: 0.6.0
tests: [tests/components/process/test_bundle_parsing.py::test_autonomy_without_its_reason_is_refused]
adrs: {ADR-0008: e6a4e033abd4, ADR-0022: 69572977f46b, ADR-0023: 949c6f4e13af, ADR-0026: ccc4bd1f5423}
supersedes: null
---

# UC-7.1 — The autonomy range, per process, action and risk class

## 1. What must be achieved

How much Taktus does without a person is chosen, not fixed. Four levels are named by the role a
person plays in the decision loop:

| Level | Name | The person |
|---|---|---|
| 1 | Observe and propose (AI in the loop) | decides and executes; Taktus supplies analyses, proposals and estimates of effort |
| 2 | Execute after approval (human in the loop) | confirms every step before it runs |
| 3 | Autonomous under supervision (human on the loop) | watches through reports and samples, and can step in at any time |
| 4 | Virtual agent business (human out of the loop) | sets frame and goals, and is drawn in only when the frame is exceeded |

At level 4 whole chains of processes run unattended as closed loops (UC-4.6). A private person automates small daily jobs with a
check at level 2 or 3; a corporation runs whole chains at level 4; both with the same system.

## 2. How it is verified

- A level can be set per process, per tool action and per risk class. Where more than one applies to
  an action, the lowest of them holds. A test sets a process to level 4 and one of its actions to
  level 2, and finds that action waiting for approval while the rest runs.
- Every process carries its level with the reason for it and with what is missing to go one level
  higher, or what forbids it (ADR-0026). A process with a bare level does not register.
- Raising a level needs an explicit approval by a person and a demonstrated quality history — a
  number of runs without a failure or a result defect, configurable per process. Taktus may
  propose a raise with the evidence; it never applies one (ADR-0026). A raise without both is
  refused and recorded.
- At every level, including 4, the emergency stop (UC-7.2), the reports (UC-6.2) and the duty to
  escalate (UC-4.5) apply without exception. No configuration switches any of them off for a
  level.
- At every level, an act under an anchor stays with a person: a legal or strategic anchor
  (ADR-0008, UC-15.5) and the correction of a result that has left the system (ADR-0022). A test
  runs a level-4 process into each and finds it halted at the step boundary with a decision request.
- No level is reserved for a size or kind of organisation: a tenant of one person can set level 4.
- A process at level 3 or above uses only adapters — workers, connectors, models — whose maturity
  is *verified* or above: the conformance suite and the removal test both passed. A step of such a
  process that only an adapter below *verified* could serve is not run on it, and the finding
  names the step and the adapter.

## 3. Where the boundary lies

**Not a promise that level 4 fits every process.** The direction is always towards level 4 and never
forced; a process whose requirements do not allow it stays where it is, and its statement says why
(principle 10). **Not the definition of the risk classes.** Which classes a tenant has is the
tenant's configuration. **Not the anchors themselves.** Which acts are anchored is the tenant's set
(UC-15.5, ADR-0008); this use case says only that no level overrides one.

## 4. What it rests on

The autonomy statement (ADR-0026, `contracts/shared/v1/Autonomy.json`), built and checked at
registration; anchors (ADR-0008) and the correction anchor (ADR-0022); the emergency stop and its
rule (UC-7.2, ADR-0023); `docs/architecture/governance.md` §1; maturity and its threshold from level 3
(`docs/architecture/contracts.md` §3, definition chapter 5.3; NTC-0051). Levels 1 to 3 per process and per
action class are on the roadmap's `0.2.0`, level 4 on `0.6.0`, which is this use case's version.
Definition `UC-7.1`.

**What the accepted decisions supersede in the definition's text.** The definition describes level
4 as running fully on its own — execute, measure, correct itself. Correcting a result that has left
the system is anchored to a person at every level (ADR-0022), and so are legal and strategic acts
(ADR-0008). Level 4 is therefore *unattended in execution, anchored in direction and in outward
correction*; the definition's unqualified "corrects itself" does not hold for what has left.

## 5. What is proven so far

A process with a bare level does not register, by the named test. Levels per
action and per risk class, the approval with a quality history, the maturity threshold from level 3,
and level 4 itself are not built.
