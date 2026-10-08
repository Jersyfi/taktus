---
id: UC-4.3
title: Taktus changes a process within the frame
component: process
epic: E4
serves: [P2, P10, P12]
state: specified
version: 0.4.0
tests: []
adrs: {ADR-0004: ffdb1f1537f5, ADR-0008: e6a4e033abd4, ADR-0011: f25413d512b9, ADR-0013: 0f303f78a7a0, ADR-0014: 6611f7833deb, ADR-0026: ccc4bd1f5423}
supersedes: null
---

# UC-4.3 — Taktus changes a process within the frame

## 1. What must be achieved

A process meets small changes in its surroundings: an interface it calls changed its shape, a
step became mandatory. Taktus makes such a change itself, as long as the change lies within the
frame the process's owner set. Every change it makes is versioned, documented, and can be rolled
back. A change outside the frame is not made: Taktus proposes it instead, and a person decides.

## 2. How it is verified

- A change Taktus makes is a new process version. The version it replaces stays registered and
  unchanged, and the runs of the old version keep their history.
- Every such version records what changed against its predecessor, why, and the observation that
  led to it — the failure, the changed interface, the run.
- Rolling back is one act: it makes the predecessor current again as a new version, and it is
  available to a person at any time.
- The new version passes the same registration as one a person writes, its takeover instructions
  included (UC-6.3); a version that does not pass is not registered and the change becomes a
  proposal.
- A change outside the frame is never applied. It is raised as a proposal with the change, the
  reason and the evidence, and nothing of it runs before a person accepts it.
- These changes are always outside the frame, whatever the frame says: raising the process's
  autonomy level (ADR-0026), changing a step's method kind (ADR-0004), loosening a step's
  exactness class (ADR-0014), removing or narrowing an anchor (ADR-0008), and widening what a
  step may reach or which credentials it receives (UC-7.3). A test asks Taktus for each of them as
  a change within the frame and finds a proposal, never a new version.

## 3. Where the boundary lies

**Not a change of what the process is for.** A change that alters the outcome the process
delivers is a new process, built under UC-4.1. **Not editing by a person.** Changing a process by
hand, with rollback, is pair editing (roadmap `0.3.0`); this use case is the change Taktus makes on
its own. **Not repair of a result.** A wrong result is handled by UC-4.10 to UC-4.12; changing the
process that produced it may follow, under this use case. **Not maturation of the method.** Moving
a step to a cheaper method is a proposal under ADR-0004, never a change made here.

## 4. What it rests on

The process version and its bundle (ADR-0011); the takeover instructions that belong to every
version (UC-6.3, ADR-0013 B); the autonomy statement, which Taktus never raises itself (ADR-0026);
method selection, where a method change is a proposal (ADR-0004); exactness classes (ADR-0014);
anchors (ADR-0008); least privilege (UC-7.3). What counts as the frame is the owner's
configuration of the process; the frame exists from `0.2.0`, and the version is `0.4.0`, where the
roadmap places change proposals. Definition `UC-4.3`.
