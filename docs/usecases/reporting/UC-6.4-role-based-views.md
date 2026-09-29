---
id: UC-6.4
title: Role-based views
component: reporting
epic: E6
serves: [P7, P14]
state: specified
version: 0.5.0
tests: []
adrs: {ADR-0015: 420aac4db0cc, ADR-0029: bae4b0c28ab4}
supersedes: null
---

# UC-6.4 — Role-based views

## 1. What must be achieved

Every position sees what matters to it, from the operational detail to the strategic figure: an
employee what Taktus did today and what waits for them; a team lead throughput, waiting and
escalations; management cost, predictability, quality and risk; the executive the contribution
and the progress of the transformation; an investor the demonstrable value. Complete transparency
does not mean that everyone sees everything. It means that nobody is denied what they are entitled
to see, and nobody sees what they are not.

Which role sees what is configured by the organisation. A person can hold several roles and then
sees each of their views.

## 2. How it is verified

- A view is defined for a role. Which roles hold which view is configuration, and follows the
  organisation's structure. A person with two roles sees the union of the two, and nothing more.
- For every figure a view shows, the roles entitled to it are declared. A test fails when a figure
  reaches a role that is not entitled to it, and when a role that is entitled does not find it.
- A figure shown in two views has one definition and one value; it is read from the component that
  owns it (ADR-0029).
- No view has a named person as the subject of a figure: aggregation is by role, team or
  department. A view definition that groups a figure by person is refused. The two exceptions
  belong to the person themselves — their own view of what Taktus took off them (UC-13.5), and a
  decider's own response times (ADR-0015) — and are visible only to that person by default.
- A figure that exists in a view can be exported (UC-5.7).

## 3. Where the boundary lies

**The views of the definition are examples.** Which views ship, and when, is the roadmap's; this
use case requires that a view can be defined per role, not that a given set exists. **Not access
control for the source systems.** What a person may read in a connected system is that system's
rule, which Taktus respects and does not replace. **Not a report.** Delivering a view's content to
a reader on a schedule is UC-6.2.

## 4. What it rests on

The `reporting` component (ADR-0029), which owns views and no figure; the organisation structure
and roles of the identity component (definition `UC-1.4`); the protective rule of ADR-0015 for
response times. Definition `UC-6.4`; the roadmap places role-based views in `0.5.0`.
