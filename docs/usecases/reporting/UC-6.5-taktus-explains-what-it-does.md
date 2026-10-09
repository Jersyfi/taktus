---
id: UC-6.5
title: Taktus explains what it does
component: reporting
epic: E6
serves: [P2, P7]
state: specified
version: 0.3.0
tests: []
adrs: {ADR-0004: ffdb1f1537f5, ADR-0006: 4ef70c98354b, ADR-0021: 202e0442e7ec, ADR-0029: 37c061ef032a}
supersedes: null
---

# UC-6.5 — Taktus explains what it does

## 1. What must be achieved

Taktus tells people about its own work in a form people understand — privately ("I did your three daily
jobs today; one needed a second attempt") as well as in business ("process X ran 47 times, quality
99.2 %, cost EUR 3.80, one escalation to team Y").

It is no black box. For every decision Taktus took, a reason a person can understand can be had on
request. Language and depth follow the reader's role.

## 2. How it is verified

- For every step of every run a reader may see, an explanation can be requested. It states what was
  done, by which method and why that method (the reason the step carries), which alternatives were
  rejected, what the step consumed, and what came out — read from the process version, the ledger and
  the provenance record (ADR-0021).
- An explanation states only what the records hold. Where a language model phrases it, every figure,
  method and reason in it is taken from the records, and a test fails an explanation that contains a
  figure the records do not.
- A summary of a period — what Taktus did, how often, at what quality and cost, with which escalations
  — is computed from the same records, with the definitions every view uses (ADR-0029).
- The depth of an explanation follows the reader's role, and so does its language: the same question
  asked by two roles gets the same facts, each at the depth configured for that role. Nothing is left
  out of a short explanation that would change its meaning.
- An explanation shows only what its reader may see (UC-6.4).
- No explanation names a person as the cause of a figure (principle 14).

## 3. Where the boundary lies

**Not why a model produced a particular text.** The explanation gives the reason the method was chosen
and what the step was given and returned; the inside of a language model is not explained.
**Not a report**, which is UC-6.2. **Not the live representation**, UC-6.10, which places the
explanation as text at the element it explains.

## 4. What it rests on

The method, reason, alternatives and fallback every step carries (`docs/architecture/methods.md`,
ADR-0004); the ledger and the provenance record (ADR-0006, ADR-0021); views and who may see what
(UC-6.4); the `reporting` component, which owns the explanation given on request (ADR-0029). Definition
`UC-6.5`. The roadmap names no version; `0.3.0`, with the web app and its live representation, is the
session's proposal.
