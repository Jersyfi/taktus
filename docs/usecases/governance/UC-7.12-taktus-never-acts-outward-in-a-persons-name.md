---
id: UC-7.12
title: Taktus never acts outward in a person's name
component: governance
serves: [P7, P14]
state: verified
version: 1.0.0
tests: [tests/components/run/test_on_behalf.py::test_an_outward_act_on_behalf_of_a_person_is_refused_before_any_call, tests/components/process/test_frame.py::test_a_step_on_behalf_of_a_person_that_declares_a_message_does_not_register, tests/components/run/test_on_behalf.py::test_a_call_on_behalf_is_served_with_the_persons_own_credential]
adrs: {ADR-0033: eb18bea6bfb4, ADR-0264: f0a92b7811e3, ADR-0332: baec32603639}
supersedes: null
---

# UC-7.12 — Taktus never acts outward in a person's name

## 1. What must be achieved

Whoever receives a message from Taktus, or finds a record it wrote, must be able to tell that
Taktus acted, not a person. Taktus may read with a person's own credential, so that it sees no
more than that person may see. It never uses that credential to send, post or write anything
that leaves the system. What Taktus does outward, it does as an identity of its own.

## 2. How it is verified

- A step that acts on behalf of a person and calls an operation whose effect leaves the system —
  a write or a delivery — fails before the connector is called. Nothing is written or sent,
  even where the person has a credential of their own for the target. A test finds no call at
  the connector and no record written.
- A process version whose step acts on behalf of a person and declares a message or its
  recipients does not register; the finding names the step.
- A step that acts on behalf of a person and only reads is still served with that person's own
  credential, in place of the one the step names.

## 3. Where the boundary lies

**Not what Taktus's own identity is called** at a service — an app, a service account, a mailbox
of its own; that is the operator's configuration. **Not a worker's own credentials**: what a
worker does with a credential an operator handed it directly is outside this rule. **Not a
connector's honesty**: an operation a connector declares as a read is taken as one.

## 4. What it rests on

ADR-0033 (Taktus acts as an identity of its own), ADR-0264 (a step on behalf of a person reads
with that person's credential), ADR-0332 (nothing leaves the system in a person's name), and
UC-1.7 §3. UC-7.6 labels a message a model wrote; this case makes sure the sender it shows is
Taktus. DEC-0239 (the second tenant's template covers what always stays with a person), NTC-0295.
Its version is `1.0.0`.

## 5. What is proven so far

Every condition of §2 is proven by the named tests: an outward call on behalf of a person with an
own credential is refused before the connector, which records no call and no record; a version
declaring recipients or a message on such a step does not register; a reading on behalf of a
person carries the person's own credential.
