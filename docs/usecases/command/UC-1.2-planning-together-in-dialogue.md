---
id: UC-1.2
title: Planning together in dialogue
component: command
epic: E1
serves: [P2, P10]
state: building
version: 0.3.0
tests: [tests/components/command/test_commission.py::test_commissioning_is_a_recorded_act]
adrs: {ADR-0005: c28377b9027e, ADR-0026: ccc4bd1f5423}
supersedes: null
---

# UC-1.2 — Planning together in dialogue

## 1. What must be achieved

A person and Taktus work out a plan together, back and forth: for a new process, a project or a
chain of tools. Taktus brings proposals, alternatives and estimates of effort. The plan that
results says what is done, with what, by when and at which autonomy level. The person then
commissions it, and commissioning is an explicit act of its own: no plan slides into execution
because someone approved one step too many.

## 2. How it is verified

- A plan is a record that names what is to be done, the processes, methods and capabilities it
  uses, the date it is due, and the autonomy level with its reason (ADR-0026). A plan that lacks
  one of the four cannot be commissioned, and the refusal names what is missing.
- Every estimate of effort in a plan names what it was computed from. An estimate without a basis
  is shown as a guess, never as a figure.
- Commissioning is a ledger entry naming the plan's version and the identity that commissioned it.
  Nothing runs from a plan that was not commissioned. Approving a step at autonomy level 2 is not
  commissioning a plan.
- A plan changed after it was commissioned runs only after it is commissioned again.
- A plan ends in one of two things: a one-off run, or a new process version that is registered like
  any other.
- Work that runs long is broken into steps at planning, each ending at a boundary where its result
  is persisted. A plan with a step that cannot be estimated before it starts is refused before
  anything runs (ADR-0005).

**Proven so far:** commissioning is a recorded act, by the named test. The plan as a record with its
four parts, the estimates and their basis, and re-commissioning a changed plan are not built.

## 3. Where the boundary lies

**Not building the process.** Turning a description into a process, testing it and registering it
is UC-4.1; this use case ends at the commissioned plan. **Not the session.** A persistent
conversation over the project's knowledge is UC-1.8, and it may end in a plan. **Not configuring
tools.** Carrying out the configuration a plan calls for is UC-1.3. **Not a guarantee that an
estimate is right**: it names its basis, and the budget holds the run (ADR-0005).

## 4. What it rests on

The plan of `docs/architecture/control-plane.md` §3; commissioning as a recorded act in the
`command` component; the autonomy statement (ADR-0026); estimation before admission and the
decomposition of long work (ADR-0005, and definition `UC-8.10`, which asks for the decomposition at
planning). Definition `UC-1.2`. The version is `0.3.0`, where a process is created, changed and
rolled back from the web app and from chat.
