---
id: UC-9.2
title: Steering the digital transformation
component: value
epic: E9
serves: [P7, P10]
state: specified
version: 0.7.0
tests: []
adrs: {ADR-0026: ccc4bd1f5423}
supersedes: null
---

# UC-9.2 — Steering the digital transformation

## 1. What must be achieved

For an organisation in change, Taktus offers a view of the transformation: how mature automation is in
each department, a backlog of potential — what could be automated next, and with what benefit — the
progress against a plan, and the dependencies between them. The executive leads the transformation on
real operating data instead of estimates, and progress is linked to the proof of value.

## 2. How it is verified

- The maturity of a department is computed from its processes as they run: their autonomy levels, the
  method kinds of their steps, and whether their takeover and removal tests passed (UC-6.7). It is
  never entered by hand.
- Every entry of the potential backlog comes from a recorded source — a proposal (UC-4.4), a
  discovered process (UC-9.4), or one a person entered — and names its expected benefit with the basis
  of that figure, marked as an expectation until the process runs.
- Progress is measured against a plan the organisation sets, and every step of progress links to the
  change in the proof of value it brought (UC-6.6).
- The bus-factor index is part of the view (UC-6.7).
- Departments, teams and processes are the units; no figure is broken down by named person
  (principle 14).

## 3. Where the boundary lies

**Not a project management tool.** The plan is a set of targets, not a task list; tasks stay in the
organisation's own tools (UC-5.3). **Not change management.** How people are brought along is the
organisation's work; Taktus supplies the figures. **Not a decision.** What to automate next stays with
people: the backlog proposes, it does not start anything.

## 4. What it rests on

The organisation's structure (UC-1.4); proposals (UC-4.4) and process discovery (UC-9.4); the proof of
value (UC-6.6) and the bus-factor index (UC-6.7); the autonomy statement (ADR-0026). Definition
`UC-9.2`. The roadmap names no version; `0.7.0`, when a second domain makes departments comparable, is
the session's proposal.
