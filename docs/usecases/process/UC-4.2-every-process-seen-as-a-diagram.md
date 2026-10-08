---
id: UC-4.2
title: Every process seen as a diagram
component: process
epic: E4
serves: [P6, P7]
state: specified
version: 0.3.0
tests: []
adrs: {ADR-0011: f25413d512b9, ADR-0029: 37c061ef032a}
supersedes: null
---

# UC-4.2 — Every process seen as a diagram

## 1. What must be achieved

Every process, and every step inside it, can be seen as a diagram. What the diagram shows and
what runs are the same thing. There is one source, the process version, and both the run and the
diagram are taken from it. A diagram that shows one thing while the run does another cannot
exist.

## 2. How it is verified

- For every registered process version there is a diagram that shows every step of the version,
  in its order and with its branches, and no step the version does not have. A test draws the
  diagram of every example and blueprint bundle and finds each step exactly once.
- The diagram is derived from the process version and stored nowhere else. A diagram cannot be
  changed except by registering a new version, and registering one changes its diagram with
  nothing else edited.
- A run shows the diagram of the version it executes, not of the newest one. A test registers a
  second version while a run of the first is in progress, and finds the run's diagram unchanged.

## 3. Where the boundary lies

**Not a builder.** A process is built from a description (UC-4.1) and changed as a new version
(UC-4.3); the diagram is never the way to edit it. **Not the live view.** How the diagram is
drawn, how a run moves through it, and what each method kind looks like is UC-6.10, which draws
from the same version. **Not the inside of a worker.** A step a worker executes is one step in the
diagram; what the worker does inside it is the worker's.

## 4. What it rests on

The process version and the bundle format (ADR-0011); the views of the `reporting` component,
which own no figure and draw from the component that owns it (ADR-0029); UC-6.10, which draws the
process level of its live representation from this diagram. The roadmap's `0.3.0` names the
process diagram. Definition `UC-4.2`.
