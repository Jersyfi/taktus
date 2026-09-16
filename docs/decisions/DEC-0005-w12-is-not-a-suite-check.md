# DEC-0005 — W-12 is not a check the suite can run

**Category:** DEFECT
**Raised in:** the pull request that adds the conformance suite for the worker contract (branch `claude/worker-conformance-suite-01d67a`)
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

The worker contract — how Taktus hands work to an external program and receives its progress —
ends with a table of twelve numbered checks, W-01 to W-12, under the heading "Conformance", and
the command that runs them. A reader takes the table as the list of what that command checks.

Eleven of the twelve are things a program can observe by talking to one worker over the network:
does it number its events without gaps, does it refuse a tool it was not allowed, does it reject
an assignment it cannot afford. The twelfth, W-12, is different. It says: taking this worker out
of a running Taktus breaks no process. That cannot be observed by talking to the worker. It needs
a Taktus with processes in it, from which the worker is removed, and processes do not exist yet
— they belong to the part of the control plane that is still to be built.

The same document, one paragraph below the table, says that maturity *verified* needs "a passed
suite plus a passed removal test". So the text lists the removal test as a check of the suite and,
in the next breath, as something in addition to the suite. Both cannot be true.

## 2. Why you are being asked

You are not. No row of `anchors.md` §1 applies: nothing here changes what a conformant worker must
do, what the suite checks, a version, a gate or anything public. This is row D6 of §2 — a
statement in the repository's own documents that contradicts itself — and is corrected and
recorded in the same pull request.

## 3. What you must decide

Nothing. The record exists so that the next reader of the table knows why W-12 says *pending*
and does not read the suite's output as a claim that the removal test passed.

## 4. What you need to know to decide

- **Conformance suite.** The program `taktusctl conformance run`, which talks to a live worker
  and reports, per check, whether the worker did what the contract requires.
- **Removal test.** Taking an integration out of a running Taktus and showing that processes
  still run, only at different quality or cost. It is the check that "interchangeable" is true,
  and it needs processes to exist.
- **Maturity.** Adapters are graded `experimental`, `verified` or `reference`. *Verified* needs
  the suite and the removal test both passed. Production processes at autonomy level 3 and above
  may only use *verified* adapters.
- **Why this is a defect and not a decision.** Whichever way the table is read, nothing a worker
  does changes, and nothing the suite can observe changes. Only the description of what the
  suite covers was wrong.

## 5. Options

None for the owner. What the session did: W-12 stays in the table, because the twelve checks are
the whole of what *verified* rests on and the numbering is referenced from fixtures and tests;
the table now says that the suite runs W-01 to W-11 and reports W-12 as *pending* until the
removal test exists; the suite's report carries the same statement, so that no run of it can be
mistaken for a claim about the removal test.

## 6. What is blocked

Nothing. The suite reports the eleven checks it can run and the one it cannot, and says which
half of *verified* it proves.

## 7. How to answer

Nothing to answer. To object to the correction: "Reopen DEC-0005" in an issue, with the reading
you hold.

## Outcome

**Corrected:** 2026-09-16
**What was wrong:** `contracts/worker/v1/README.md` §7 listed W-12, the removal test, in the
table of checks that `taktusctl conformance run` performs, and then described the removal test as
something that comes *in addition to* a passed suite. `docs/architecture/contracts.md` §3 said the
same. A suite that talks to one endpoint cannot remove an adapter from processes, and no process
exists yet.
**Why it was wrong:** the table was written as the complete list of what *verified* rests on,
and the command above it was read as running the whole table. Two readers would have taken two
different things from one paragraph; the second would have read a green suite as a passed
removal test.
**What it now says:** the suite runs W-01 to W-11 against a live worker and reports W-12 as
*pending*; a passed suite plus a passed removal test is *verified*; the report states which half
it proves (`contracts/worker/v1/README.md` §7, `docs/architecture/contracts.md` §3,
`contracts/worker/v1/CONFORMANCE.md` §7).
**What changed in substance:** nothing. No check was added, removed or weakened; no worker is
marked *verified*; the removal test still has to be built and passed before any adapter is.
**Recorded in:** the pull request that adds the conformance suite for the worker contract
(branch `claude/worker-conformance-suite-01d67a`)
