---
id: UC-4.1
title: A process from a description
component: process
epic: E4
serves: [P2, P8]
state: specified
version: 0.3.0
tests: []
adrs: {ADR-0004: ffdb1f1537f5, ADR-0011: f25413d512b9, ADR-0014: 6611f7833deb, ADR-0018: 17c99e0eaa3c, ADR-0026: ccc4bd1f5423}
supersedes: null
---

# UC-4.1 — A process from a description

## 1. What must be achieved

A person describes in their own words what should happen. Taktus builds the process from that
description, tries it out, and puts it into operation once the person has commissioned it. Nobody
assembles blocks by hand. The structural thinking — which steps, in which order, by which method
— is Taktus's; the person decides whether the result is what they meant.

Any function that can be described can be composed this way.

## 2. How it is verified

- From a description, Taktus produces a process version that passes the same validation as one a
  person writes by hand: every step carries its method, the reason for it, the methods rejected,
  a fallback where the method varies, and — where it produces a result — an exactness class
  (ADR-0004, ADR-0014, ADR-0018); the process carries its autonomy level with its reason and what
  is missing to go higher (ADR-0026).
- A step for which no method admissible under its exactness class fits is not filled with a
  guess: it becomes a `human` step, or the proposal names the gap and does not register.
- Before the person commissions it, the proposal runs as a rehearsal in which nothing leaves the
  system, and the person sees what the rehearsal did, step by step, and what it would have sent
  out.
- Commissioning is the person's explicit act and is recorded; before it, nothing of the proposal
  runs for real.
- The proposal is a process bundle in the open format of ADR-0011: the person can read it, change
  it and keep it without Taktus.

## 3. Where the boundary lies

**Not a visual builder.** A diagram of the process is for understanding it (definition `UC-4.2`),
never the way to build it. **Not process discovery.** Finding processes nobody has described yet
is `UC-9.4`. **Not a promise that the first proposal is right.** The rehearsal and the person's
commissioning are the check; a wrong proposal that is not commissioned has cost a rehearsal.
**Not method maturation.** Moving a step to a cheaper method once it has run long enough is
ADR-0004's, over time, not at the moment of building.

## 4. What it rests on

Method selection (ADR-0004, `docs/architecture/methods.md` §5, where Taktus proposes a process);
exactness classes (ADR-0014, ADR-0018); the bundle format (ADR-0011, `0.3.0`); autonomy with its
reason (ADR-0026); the removal test's rehearsal mode, which runs a process with nothing leaving.
Definition `UC-4.1`. The version is `0.3.0`, where the roadmap requires that a process can be
created from the web app and from chat.
