---
id: UC-6.7
title: The bus-factor index
component: value
epic: E6
serves: [P6, P13, P14]
state: specified
version: 0.5.0
tests: []
adrs: {ADR-0013: 1da224cdeaf4, ADR-0029: 37c061ef032a, ADR-0030: 9d551b889a39}
supersedes: null
---

# UC-6.7 — The bus-factor index

## 1. What must be achieved

Principle 6, no bus factor of zero, becomes a figure. Taktus computes continuously how many processes
would stand still without Taktus, because their takeover test has not passed, and how many would stand
still without a given role or a given supplier, because their removal test has not passed. It shows the
trend and the graph of dependencies.

The index appears in the views of management, the executive and compliance, and feeds the view of the
transformation (UC-9.2). It is computed from real test results, never estimated. It is about roles and
processes, never about named people. Every deterioration produces a proposal of what to do.

## 2. How it is verified

- The index is computed from recorded results only: the takeover test of each process (UC-6.3) and the
  removal test of each integration (`removal.tested` in the ledger, UC-8.9). A test with one process
  whose takeover test is recorded as failed and one integration whose removal test is *broke* finds
  both counted, and changing either record changes the index with nothing else touched.
- A process with no result, or with a result recorded for an earlier version of the process or under
  an earlier configuration, counts as not passed. A removal test that is *untested* is shown as unknown,
  never as passed.
- Three counts are shown, each with the processes behind it: without Taktus, per role, and per
  supplier. A role counts where a process's takeover instructions require it; a supplier counts where
  its removal broke a process.
- The trend is kept over time, and the dependency graph links each process to Taktus, to the roles and
  to the suppliers it depends on.
- The index is also shown per domain (UC-15.5).
- No figure of the index names a person or can be traced to one. A role held by a single person is
  still shown as the role (principle 14).
- A deterioration — a process or a dependency that passed and no longer does — produces a proposal
  (UC-4.4) naming the test that failed and the step that would restore it.

## 3. Where the boundary lies

**Not running the tests.** The takeover test is UC-6.3 and the removal test is S-01 of
`blueprints/self-operation/`; this use case reads their results. **Not an assessment of people.** That
a role is a dependency says nothing about the people who hold it. **Not a guarantee.** A passed test
says that a person or a replacement carried the process once, under the recorded configuration.

## 4. What it rests on

The takeover test (UC-6.3, ADR-0013 B); the removal test and its four verdicts (UC-8.9, ADR-0030,
`blueprints/self-operation/`); the responsibility anchor, which shows per domain whether both tests
passed (UC-15.5); proposals (UC-4.4); views (UC-6.4) and the transformation view (UC-9.2). Filed in
`value` as a figure computed from test results, which the views show (ADR-0029). Definition `UC-6.7`,
new in version 2. The roadmap's `0.5.0`: principles 6 and 13 measured rather than asserted.
