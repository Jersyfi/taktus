---
id: UC-5.7
title: No binding to Taktus's own dashboard
component: reporting
epic: E5
serves: [P1, P7, P13]
state: verified
version: 0.5.0
tests: [tests/adapters/rest/test_figures.py::test_every_figure_a_view_shows_is_in_the_export_with_the_same_definition_and_value, tests/adapters/rest/test_figures.py::test_a_figure_reaches_only_the_roles_entitled_to_it_and_a_view_never_widens_that, tests/adapters/rest/test_figures.py::test_the_csv_export_carries_the_rows_of_the_json_export, tests/adapters/rest/test_figures.py::test_every_path_the_web_app_calls_is_a_route_of_the_surface, tests/adapters/connectors/test_business_intelligence_connector.py::test_the_rows_of_a_query_are_read_with_their_blanks, tests/adapters/connectors/test_business_intelligence_connector.py::test_it_declares_no_write, tests/composition/test_figures_as_input.py::test_a_figure_read_through_the_connector_is_the_next_step_s_input]
adrs: {ADR-0029: 37c061ef032a, ADR-0241: 7ef4e139d151}
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

## 5. What is proven so far

Built (ADR-0241). By the named tests: every figure any view shows is in `GET /figures` with the
same identifier, definition and value, for every reader; a figure a role is not entitled to is in
neither its views nor its export; the CSV export carries the rows of the JSON one; every path the
web app calls is a route of the HTTP surface, so nothing is bound to the dashboard; a figure of
the business-intelligence tool is read through `bi.figures.query`, which declares no write, and
becomes the next step's input. The export is read on request; nothing pushes it.
