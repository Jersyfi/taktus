# ADR-0009 — Adapters in the main repository until 1.0.0

**Status:** accepted

## Context
The goal is many adapters from a community. Separate repositories are right for that in the long
run, and harmful during the design phase: while the contract still moves, every split turns into a
compatibility matrix instead of progress.

## Decision
Until `1.0.0` the contracts, the conformance suite and the reference adapters live in the main
repository and move together. From `1.0.0` the contract is frozen and versioned; community adapters
move to their own repositories and the main one keeps the references and the suite.

## Alternatives
- **Split immediately** — looks more open, creates compatibility work for a contract nobody uses yet.
- **Monorepo forever** — every adapter pull request then touches the core repository and carries its
  review burden.

## Consequences
- The moment of the split is a milestone, not an oversight.
- `1.0.0` gains a hard meaning: the contract is stable enough for strangers to build on.

## Where this promise ends

"Move together until 1.0.0" is a promise about this repository, not about anyone else's: a
third party that builds an adapter against `v1` before 1.0.0 builds against a contract that may
still move (ADR-0019), and the freeze is a milestone with its own check (roadmap, *The road to
1.0.0*), not a date. After the split, the references and the suite stay here. A community
adapter's quality is its own; the suite says whether it conforms, not whether it is good.
