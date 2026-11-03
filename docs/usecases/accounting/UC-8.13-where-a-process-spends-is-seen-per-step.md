---
id: UC-8.13
title: Where a process spends is seen per step, and two runs side by side
component: accounting
epic: E8
serves: [P7, P8, P14]
state: built
version: 0.4.0
tests: [tests/components/accounting/test_spend.py::test_the_meter_of_a_step_keeps_its_price_kinds_turns_and_compression_apart, tests/components/accounting/test_spend.py::test_a_run_shows_its_spend_per_step_at_its_own_table, tests/components/accounting/test_spend.py::test_two_runs_of_the_same_task_are_shown_side_by_side, tests/components/accounting/test_spend.py::test_a_process_shows_its_spend_per_step_over_a_window, tests/components/accounting/test_takt.py::test_the_takte_of_each_step_add_up_to_the_run_s, tests/adapters/rest/test_spend_and_trials.py::test_a_run_s_spend_is_read_by_step_and_another_set_beside_it, tests/adapters/rest/test_spend_and_trials.py::test_a_run_of_another_tenant_has_no_spend_to_show, tests/adapters/rest/test_spend_and_trials.py::test_a_process_s_spend_is_summed_per_step_over_a_window, tests/composition/test_spend_in_channel.py::test_a_run_s_spend_is_answered_step_by_step_with_its_link, tests/composition/test_spend_in_channel.py::test_two_runs_are_answered_side_by_side_with_whether_each_result_is_the_same, tests/composition/test_spend_in_channel.py::test_only_the_owner_and_whom_they_named_are_shown_runs_they_may_see]
adrs: {ADR-0005: 0ea928e2016b, ADR-0010: e381de241d4a, ADR-0045: e1fcb1254c71, ADR-0055: 6ea439834b2c, ADR-0148: 4ba172a497c9}
supersedes: null
---

# UC-8.13 — Where a process spends is seen per step, and two runs side by side

## 1. What must be achieved

A person sees from the records where a process spends: money, Takte, and for each step on a
model or a worker the tokens by what they cost — plain input, cache writes, cache reads, output
— the turns, and what a compression saved. They see it per step, for one run and for a process
over a window, quickly understandable, as a chart where it helps, in the web app and in the
owner's channel. Two runs of the same task — with and without a change such as a compression or
another model — are set side by side, cost and result, so that a change is adopted only when it
is shown to be better.

## 2. How it is verified

- Per step of a run, the figures are read from the ledger's records of that step and priced at
  the run's own price table and weighting table, never at today's. The steps' money together is
  the run's money, and the steps' Takte together are the run's Takte.
- What cannot be priced is named as not priced. It is never shown, charted or counted as zero.
- A process's spend over a window sums every run whose steps finished in it, per step, the
  money per currency.
- Two runs set side by side show both runs' figures per step, the difference, and whether each
  step produced the same result. Where the runs are of different processes or were priced at
  different tables, the view says so.
- The web app draws money per step and tokens per step by price kind as charts, one measure per
  axis, and holds the same figures as text. The owner's channel answers a request for a run, two
  runs or a process with the same figures and the link to the web app's view.
- A run a person may not see is answered as one that does not exist, on every surface.
- No figure assesses a named person (principle 14): a run, a step and a process are measured.

## 3. Where the boundary lies

- Not the value ledger of `0.5.0`: what a step was worth is not measured here.
- No figure a worker did not report is estimated: a worker that reports no turns shows none.
- Taktus does not compress on its own here; a compression is shown where a worker reported one.
- The owner's channel reads a process over one fixed window; choosing another is the web app's.

## 4. What it rests on

ADR-0148 (spend per step and two runs side by side) and its amendment of 2026-10-28; ADR-0005
and ADR-0010 (the price and weighting tables a run is held to); ADR-0045 (the owner's channel);
ADR-0055 §5 (one visibility predicate). Issue #449, DEC-0200 answer 3. UC-8.5 records and
prices every step's consumption; this case shows it per step.

## 5. What is proven so far

The named tests prove the meter per step with its price kinds, turns and compression, the spend
of a run at its own table, two runs side by side, a process over a window, the Takte per step,
the HTTP surface with its visibility, and the owner's channel. The web app's charts are proven by
`web/src/lib/spend.test.ts`.
