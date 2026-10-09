---
id: UC-9.4
title: Discovering processes nobody wrote down
component: value
epic: E9
serves: [P6, P10, P14]
state: specified
version: 0.6.0
tests: []
adrs: {}
supersedes: null
---

# UC-9.4 — Discovering processes nobody wrote down

## 1. What must be achieved

Much of what an organisation or a household does runs by hand, undefined or unnoticed — "she always
does that on Fridays". Taktus helps people without special knowledge, as well as experts such as
controllers, to bring these processes to light and into a world that is steered digitally: by a guided
interview — "tell me what you do every week" — by patterns in the connected tools — recurring tickets,
messages, appointments — and by the recurring requests people make of Taktus itself.

An implicit process is first made explicit — documented, given an owner, valued with its balance
(UC-9.3) — and only then automated, step by step, starting at a conservative autonomy level. Nothing is
automated that was not understood and documented first. Digitalising in this way makes the bus factor
larger, not smaller.

## 2. How it is verified

- Every discovered process passes five stages in order: made visible, documented, valued, decided by
  a person, automated. Each stage is a ledger entry, and no stage can be reached without the one
  before it.
- The decision to automate is a person's, recorded as such; Taktus never takes it.
- A discovered process enters automation at autonomy level 1 or 2 (UC-7.1), and with takeover
  instructions from its first version (UC-6.3).
- A pattern found in a person's own tools or requests is shown to that person first. It becomes a
  proposal to anyone else only when the person agrees, and then as a procedure of the organisation,
  never as a description of how the named person works (principle 14).
- The interview reaches the same documented process for a person without special knowledge as for an
  expert: a test runs one process through both and compares the result (UC-13.1).

## 3. Where the boundary lies

**Not observation of people.** Taktus reads the tools it is connected to under their rights; it does
not watch screens, keystrokes or working hours. **Not automation without a decision.** Discovery ends
at a proposal; building the process is UC-4.1. **Not the coach.** Hints from a person's own use are
UC-13.3, which leads into this use case.

## 4. What it rests on

The process from a description (UC-4.1) and proposals (UC-4.4); the value balance (UC-9.3); the
takeover instructions (UC-6.3); the autonomy range (UC-7.1); the guided and the expert mode (UC-13.1)
and the automation coach (UC-13.3); principle 14, which forbids describing how a named person works.
Definition `UC-9.4`. The roadmap names no version; `0.6.0`, with the coach and the skill lifecycle, is
the session's proposal.
