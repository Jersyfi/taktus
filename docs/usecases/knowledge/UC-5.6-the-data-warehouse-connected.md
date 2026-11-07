---
id: UC-5.6
title: The data warehouse connected
component: knowledge
epic: E5
serves: [P1, P7, P12]
state: verified
version: 0.7.0
tests: [tests/components/governance/test_connection_grants.py::test_a_new_connection_reads_only, tests/components/governance/test_connection_grants.py::test_the_owner_grants_writing_and_withdraws_it_and_each_act_is_recorded, tests/components/governance/test_connection_grants.py::test_anyone_but_a_person_with_the_right_is_refused_and_the_refusal_recorded, tests/components/run/test_warehouse.py::test_a_write_without_a_grant_is_refused_before_it_reaches_the_warehouse, tests/components/run/test_warehouse.py::test_a_write_on_a_granted_connection_reaches_the_warehouse_once, tests/components/run/test_warehouse.py::test_every_query_is_recorded_with_its_step_by_reference_and_its_text_kept_whole, tests/adapters/rest/test_connections.py::test_a_steps_queries_are_read_with_their_text_where_the_run_is_seen, tests/components/run/test_warehouse.py::test_two_identities_ask_the_same_question_and_each_is_answered_as_the_warehouse_limits_it, tests/adapters/connectors/test_warehouse_connector.py::test_two_identities_ask_the_same_question_and_each_reads_what_the_warehouse_shows_it, tests/components/process/test_queries.py::test_a_query_fixed_in_the_version_may_feed_an_exact_step, tests/components/process/test_queries.py::test_a_query_a_model_wrote_feeds_no_exact_or_sourced_step, tests/components/process/test_queries.py::test_a_query_given_as_an_input_may_feed_sourced_but_not_exact, tests/components/process/test_queries.py::test_registration_refuses_a_version_whose_model_written_query_feeds_a_sourced_step, tests/composition/test_warehouse_signals.py::test_a_warehouse_figure_below_its_threshold_escalates_with_the_reading_on_record, tests/composition/test_warehouse_signals.py::test_every_warehouse_figure_a_view_or_a_report_shows_is_in_the_export, tests/components/reporting/test_warehouse_figures.py::test_a_judged_warehouse_reading_is_a_figure_with_its_query_by_reference, tests/components/reporting/test_warehouse_figures.py::test_a_signal_not_measured_is_withheld_with_why_never_zero, tests/adapters/rest/test_figures.py::test_every_warehouse_figure_the_signals_view_shows_is_in_the_export]
adrs: {ADR-0006: a5960785aee4, ADR-0014: 6611f7833deb, ADR-0021: dc801ddd1c47, ADR-0024: 52ba89e4adec}
supersedes: null
---

# UC-5.6 — The data warehouse connected

## 1. What must be achieved

Above all for larger and data-led organisations: Taktus connects to the data warehouse or lakehouse
where the organisation keeps its consolidated data. It can query that data in natural language, use it
in processes — "escalate when figure X falls below threshold Y" — and feed it into reports and
controlling views.

Reading is the safe default. Writing is granted explicitly, per connection. Every query Taktus
generates can be seen and is recorded. The warehouse's own permissions, down to rows and columns, are
passed through and never bypassed.

## 2. How it is verified

- A new connection reads only. Writing is a grant on that connection, made by a person with the right
  to make it, and recorded; a write attempted without the grant is refused before it reaches the
  warehouse.
- Every query Taktus sends is recorded with the step that sent it, by reference in the ledger
  (ADR-0006), and a person entitled to the step can read the query text.
- The warehouse is queried with the identity of the person or process on whose behalf Taktus acts, so
  that row-level and column-level security apply. A test with two identities whose warehouse
  permissions differ sends the same question and finds each answer limited as the warehouse limits it.
- A figure that feeds a step of class `exact` comes from a query that is fixed in the process version
  and was reviewed when the version was registered. A query a language model writes during a run may
  feed only a step of class `tolerant` or `free` (ADR-0014).
- A threshold over a warehouse figure can start or escalate a process, and the reading that triggered
  it is in the step's provenance record (ADR-0021).
- Every warehouse figure shown in a view or a report is in the export (UC-5.7).

## 3. Where the boundary lies

**Not a warehouse.** Taktus keeps no copy of the organisation's data beyond what a step consumed
(principle 1). **Not a business-intelligence tool**: the views are UC-6.4, and the organisation's own
tool is UC-5.7. **Not the warehouse's governance.** Who may read what in the warehouse is decided
there; Taktus respects it and does not administer it.

## 4. What it rests on

Connectors and their effect classes (ADR-0024); exactness classes and which methods may produce an
`exact` value (ADR-0014); the content-free ledger (ADR-0006) and the provenance record (ADR-0021); the
export without a figure left behind (UC-5.7); rights and least privilege (UC-7.3). Definition `UC-5.6`.
The roadmap names no version; `0.7.0`, with the breadth of connectors the second domain brings, is
the session's proposal.

## 5. What is proven so far

Every condition of section 2. A warehouse figure is a signal over a step that queries the
warehouse; the export carries it as `signal.warehouse` with its definition, its method and the
query by reference (ADR-0291 §3). That every warehouse figure the signals view and the daily
report show is in the export is proven over the warehouse connector
(`tests/composition/test_warehouse_signals.py`) and at `GET /figures`
(`tests/adapters/rest/test_figures.py`).
