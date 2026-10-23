---
id: UC-1.10
title: A proposed version is rehearsed from the plan dialogue
component: command
epic: E1
serves: [P2, P7, P10]
state: building
version: 0.4.0
tests: [tests/composition/test_proposals.py::test_a_rehearsal_runs_the_proposal_as_no_version_and_acts_on_nothing_outside, tests/composition/test_proposals.py::test_only_a_proposal_whose_rehearsal_finished_is_commissioned]
adrs: {ADR-0030: 232318604b2d, ADR-0108: 5807c686953c, ADR-0091: 22e6c748bb90}
supersedes: null
---

# UC-1.10 — A proposed version is rehearsed from the plan dialogue

## 1. What must be achieved

A person who has worked out a change with Taktus, and so holds a plan that ends in a new process
version, can try that version before commissioning it. The trial is a rehearsal: it runs the
version as any run does and acts on nothing outside the system. The person sees what the rehearsal
did, and commissions only after it has run through. The first run of a new version loses its
fear.

## 2. How it is verified

- **The plan offers the rehearsal.** A plan that ends in a new process version, shown to the
  person in the web app or in the chat, offers the rehearsal as an act of its own, before it
  offers commissioning. A test shows a proposal without a rehearsal and finds the act, and finds
  no commissioning.
- **The run is a rehearsal and acts on nothing outside.** The run that the act starts is marked
  as a rehearsal wherever it is shown, and every outward operation in it answers from the
  recording of its last real call (ADR-0030). A test finds the mark on the run, and no outward
  call made.
- **The person sees what the rehearsal did.** The plan shows, beside the proposal, that this was
  a rehearsal, how far its run is, and each step with its state. A rehearsal that stopped says at
  which step and why, naming an outward operation that was never called for real as the reason
  when that is the reason. A test stops a rehearsal at such an operation and finds both.
- **Commissioning waits for a rehearsal that ran through.** Commissioning is offered only once
  the rehearsal's run has finished. A rehearsal that has not finished, or that stopped, offers
  none.

## 3. Where the boundary lies

**Not a change to the proposal flow.** A proposal, its rehearsal, its commissioning and the
rollback are as ADR-0091 and UC-4.15 define them; this use case adds what the person is offered
and shown on the way. **Not the plan record.** The plan with its four parts, its estimates and
its re-commissioning is UC-1.2; the plan this use case speaks of is the proposal for one change.
**Not a rehearsal that is better than its recordings.** An operation with no recording makes the
rehearsal stop, and the person is told so; it does not pass. **Not anchors shown as halting.** A
rehearsal asks no step boundary of autonomy or anchors; showing where a real run would halt is
left out here.

## 4. What it rests on

The rehearsal (ADR-0030, ADR-0108); the proposal, its rehearsal and its commissioning (ADR-0091,
UC-4.15); the run level the web app reads (UC-6.10); planning in dialogue (UC-1.2). The owner
accepted offering the rehearsal in the plan dialogue as part of the product outlook (DEC-0190,
idea F9; market review, `docs/research/2026-10-12-market-review.md`, idea F). Written as a
`restoration` notice (NTC-0221).

## 5. What is proven so far

Built by #329. By the named tests:

- A proposal's rehearsal is a run marked as a rehearsal that counts as no version and acts on
  nothing outside, and only a proposal whose rehearsal finished is commissioned.

Also checked by `web/src/lib/change.test.ts`, which the gate does not run: the page offers the
rehearsal of a proposal that has none, shows a rehearsal step by step with its summary, says
where a stopped one stopped, and offers commissioning only once the rehearsal's run has finished.
The chat already offers the act in its phrasebook.
