---
id: UC-0.0
title: <the outcome, in a few words>
component: <the component folder this file lives in>
serves: [<P1 to P14, at least one>]
state: specified
version: <the milestone that implements it, x.y.z>
tests: []
adrs: {}
supersedes: null
---

<!--
Copy this file to docs/usecases/<component>/UC-<area>.<case>-<slug>.md. The number follows
NUMBERING.md. Replace every <placeholder>; `make gate-usecases` fails on any that remains.
Sections 1 to 3 are the requirement (mode 3, the owner's); section 4 and the front matter are
the description (mode 1). Every ADR the file names goes into `adrs` with its digest:
`uv run tools/check_usecases.py --digest ADR-NNNN` prints it. Optional: `epic: E<n>`.
Never write or change sections 1 to 3 in the pull request that implements the use case.
-->

# UC-0.0 — <title>

## 1. What must be achieved

<The outcome, not the route. One or two paragraphs. If a mechanism appears here, it belongs in
`docs/architecture/` instead.>

## 2. How it is verified

<The condition that must hold, stated so that it cannot be met by interpretation. Name the
observable thing, the threshold where there is one, and what a failure looks like. What the use
case must never do is a condition too.>

## 3. Where the boundary lies

<What is explicitly not required. What a reader might reasonably expect here and will not find,
and why.>

## 4. What it rests on

<Other use cases, ADRs, contracts, the milestone; where the definition's text said it.>
