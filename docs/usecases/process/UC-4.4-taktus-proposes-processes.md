---
id: UC-4.4
title: Taktus proposes processes
component: process
epic: E4
serves: [P2, P9, P14]
state: specified
version: 0.6.0
tests: []
adrs: {ADR-0004: ffdb1f1537f5, ADR-0015: 3a42705e5561}
supersedes: null
---

# UC-4.4 — Taktus proposes processes

## 1. What must be achieved

Taktus advises. It notices where work could be automated and says so, unasked: "you do this by
hand every week — shall I take it over?" Its proposals are short, ordered by priority, and each can
be accepted on its own. A way of working that recurs in what was proposed and in what people
corrected becomes a draft skill, which enters the skill lifecycle like any other.

## 2. How it is verified

- A proposal states the work it would take over, what it would cost to run, and why it is
  proposed now, and nothing else.
- Proposals are delivered as a list ordered by priority, and the reason for the order is shown.
- Each proposal is accepted or declined on its own. Accepting one starts building a process from
  it (UC-4.1); nothing runs for real before the person commissions it.
- A procedure that recurs in accepted proposals and in corrections people made becomes a draft
  skill. A draft skill never reaches production directly: it enters the skill lifecycle, and only
  passed evaluations take it further (UC-14.2).
- A proposal drawn from a person's own work is shown to that person only. Nothing about a person's
  behaviour enters a skill: a draft skill describes a procedure of a process, never how a named
  person works (principle 14).

## 3. Where the boundary lies

**Not a change of an existing process.** Changing a process that runs is UC-4.3; proposing a
cheaper method for a step is ADR-0004's maturation. **Not process discovery from the
organisation's systems.** Finding processes in data nobody described is definition `UC-9.4`.
**Not the automation coach.** Helping a person learn to use automation is `UC-13.3`, which may draw
on these proposals. **No obligation.** A declined proposal costs nothing and changes nothing.

## 4. What it rests on

UC-4.1, which builds a process from an accepted proposal; the skill lifecycle (`UC-14.2`, migrated
in step 3, roadmap `0.6.0`); method selection (ADR-0004); the protective rule that what concerns a
person belongs to that person (ADR-0015, principle 14). The version is `0.6.0`, where the skill
lifecycle arrives; proposals without draft skills could come earlier, and the roadmap does not name
them. Definition `UC-4.4`.
