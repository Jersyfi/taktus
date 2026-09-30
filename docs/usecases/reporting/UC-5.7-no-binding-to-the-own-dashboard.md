---
id: UC-5.7
title: No binding to Taktus's own dashboard
component: reporting
epic: E5
serves: [P1, P7, P13]
state: specified
version: 0.5.0
tests: []
adrs: {ADR-0029: 37c061ef032a}
supersedes: null
---

# UC-5.7 — No binding to Taktus's own dashboard

## 1. What must be achieved

Taktus's own dashboard shows all of its data — operation, cost, value, the audit record. And every
one of those figures also leaves Taktus, without exception, to the business-intelligence tool the
organisation already uses, by export, by interface or pushed as it changes. In the other direction,
figures in that tool can be read by Taktus as a source of knowledge or as a trigger.

Nobody is bound to the Taktus dashboard. It is a convenience, never an obligation.

## 2. How it is verified

- For every figure any view shows, an automated test finds the same figure, with the same
  definition and the same value, in the export. A figure added to a view without being exported
  fails the test.
- A figure has one definition, whether it is shown or exported (ADR-0029): there are never two
  numbers for the same thing.
- The export respects visibility: a figure a role may not see in a view is not in that role's
  export (UC-6.4).
- Every process can be operated, watched and taken over without the dashboard: every action the
  dashboard offers is available through another channel or the interface.
- A figure from the organisation's business-intelligence tool can be read through a connector and
  used as an input or a trigger; the connection is read-only unless writing is granted for it
  explicitly.

## 3. Where the boundary lies

**No business-intelligence tool is shipped** and none is preferred. **Not real time** unless the
chosen transport is. **Not the formats.** Which open formats and interfaces the export uses is
architecture, decided when it is built. **Not the organisation's own data warehouse**, whose
connection is a separate use case (definition `UC-5.6`).

## 4. What it rests on

The `reporting` component and its rule that it owns no figure (ADR-0029); the views of UC-6.4;
connectors. Definition `UC-5.7`; the roadmap places the export in `0.5.0`.
