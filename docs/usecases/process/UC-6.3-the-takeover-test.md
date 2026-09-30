---
id: UC-6.3
title: The takeover test
component: process
epic: E6
serves: [P6, P12, P13]
state: specified
version: 0.5.0
tests: []
adrs: {ADR-0013: c5a0288ea618, ADR-0029: 37c061ef032a}
supersedes: null
---

# UC-6.3 — The takeover test

## 1. What must be achieved

For every process Taktus runs there are maintained instructions with which a person can run the
process without Taktus: the sequence, the expertise each part needs, the systems involved, and
where the credentials are — by reference, never their values. The test passes when a person can
run the process from those instructions alone.

Dependence on Taktus is then a choice an organisation can undo at any time, not a risk it
carries.

## 2. How it is verified

- Every registered process version carries takeover instructions; a version without them does not
  register.
- The instructions belong to the version: changing a step changes its instructions in the same
  version, and a version whose instructions describe a step it does not have, or omit one it has,
  does not register.
- For every step the instructions name the system to act in, what to do there, the expertise it
  needs, each credential by its parameter and where an authorised person finds it, and how to tell
  that the step is done. A test reads the instructions of every example and blueprint bundle and
  finds all five for every step, and no reference to a Taktus identifier a person could not look
  up.
- The test is carried out: a person runs the process by hand from the instructions alone, and the
  record of that trial — the role that ran it, when, and what was missing — is kept with the
  process version. A process at autonomy level 3 or 4 without a passed trial on its current version
  is listed as such wherever its autonomy level is shown.

## 3. Where the boundary lies

**Not as fast.** A person running the process by hand may take far longer; the test is that they
can. **Not training.** The instructions assume the expertise they name; they do not teach it.
**Not the credentials themselves.** The instructions point at them; the credential register holds
what each is (principle 6). **Not repairing Taktus.** Restoring an earlier version of Taktus
without Taktus is a separate procedure (ADR-0013 C).

## 4. What it rests on

Requirement B of ADR-0013; the process version (`process`), where ADR-0029 files it because the
instructions are part of the version; `CREDENTIALS.md` and its parameters; UC-4.12, whose
remediation plan is held to the same shape. Definition `UC-6.3`. The version is `0.5.0`, where the
roadmap automates the takeover test.
