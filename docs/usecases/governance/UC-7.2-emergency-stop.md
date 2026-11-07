---
id: UC-7.2
title: Emergency stop
component: governance
epic: E7
serves: [P10, P12]
state: building
version: 0.5.0
tests: [tests/components/run/test_engine.py::test_a_stop_mid_step_lands_on_the_worker_s_boundary_and_resume_duplicates_nothing, tests/components/run/test_engine.py::test_a_stop_requested_between_steps_takes_effect_at_the_next_boundary, tests/components/run/test_adapter_stop.py::test_a_stop_of_one_worker_halts_every_run_it_serves_and_the_others_go_on, tests/components/run/test_adapter_stop.py::test_a_held_stop_hands_no_step_to_its_adapter_until_it_is_lifted, tests/components/run/test_adapter_stop.py::test_a_stop_that_found_no_run_is_confirmed_and_says_so, tests/components/run/test_adapter_stop.py::test_a_stop_of_an_adapter_no_step_is_halted_at_is_refused, tests/components/run/test_runner.py::test_a_stop_of_an_adapter_reaches_the_runner_at_its_renewal_and_others_go_on, tests/components/run/test_adapter_stop_calls.py::test_a_stop_of_one_connector_halts_the_runs_that_would_call_it_and_others_go_on, tests/components/run/test_adapter_stop_calls.py::test_a_wait_on_a_stopped_connector_stops_between_two_checks_and_resumes_its_count, tests/components/run/test_adapter_stop_calls.py::test_a_stop_of_one_model_halts_every_run_that_would_ask_it_and_the_others_go_on, tests/components/run/test_adapter_stop_calls.py::test_a_step_whose_chain_moves_to_a_stopped_model_halts_there, tests/components/run/test_adapter_stop_calls.py::test_a_stop_may_name_every_configured_worker_connector_and_model, tests/components/run/test_open_work.py::test_a_stopped_connector_is_not_called_for_a_count_and_the_run_waits, tests/governance/test_result_defects.py::test_each_criterion_on_its_own_triggers_what_the_shipped_rule_says, tests/governance/test_result_defects.py::test_a_criterion_may_be_added_and_a_threshold_changed, tests/governance/test_result_defects.py::test_a_configuration_that_empties_the_set_is_refused, tests/components/run/test_scoped_stop.py::test_a_stop_of_a_process_halts_its_run_at_the_worker_s_boundary_and_others_go_on, tests/components/run/test_scoped_stop.py::test_a_held_stop_of_a_process_hands_no_step_on_until_a_person_lifts_it, tests/components/run/test_scoped_stop.py::test_a_person_stops_the_tenant_at_every_level_without_a_reason, tests/components/run/test_scoped_stop.py::test_a_stop_of_the_instance_is_a_stop_of_each_tenant_it_serves, tests/components/run/test_scoped_stop.py::test_a_rule_s_stop_names_the_rule_and_the_incident_and_no_person, tests/governance/test_result_defects.py::test_a_rule_that_decides_stop_stops_the_process_and_records_the_rule_and_the_facts, tests/governance/test_result_defects.py::test_a_verdict_short_of_stop_stops_nothing]
adrs: {ADR-0004: ffdb1f1537f5, ADR-0005: 0ea928e2016b, ADR-0008: e6a4e033abd4, ADR-0023: 949c6f4e13af, ADR-0138: a950b2e0b871, ADR-0153: f720e5930f42, ADR-0256: ca2fe7d86cac}
supersedes: null
---

# UC-7.2 — Emergency stop

## 1. What must be achieved

Something is going wrong at a speed or scale where the next step must not run: a detected result
defect in a billing run, a partner file with a changed shape feeding twenty processes, an operator
who has seen enough. Taktus stops.

A stop takes effect at the next step boundary of every affected run — never in the middle of a
step, so that at most one step of work is lost (ADR-0005) — and is recorded in the ledger with its
cause. Its scope is global, a tenant, a process, a run, or an adapter. A stop scoped to an adapter
stops every step that adapter serves, in every run, and nothing else: runs on other adapters go
on. An adapter is the agent a business sees acting — a worker, a connector or a model.

A stop is confirmed once it holds: when every affected run has reached its boundary. The
confirmation goes to whoever requested the stop, and names the runs it stopped. A stop that found
no run to stop is confirmed as well, and says so.

There are two triggers:

- **A person**, at any time, without having to give a reason.
- **A rule**, automatically, never a probabilistic method (ADR-0023). The rule reads few,
  measurable, documented criteria — the size of the error window, the exactness class affected,
  whether data has left the system, whether a legal anchor lies downstream, the business relevance
  of the process — and yields `continue`, `escalate` or `stop`. The thresholds are tenant
  configuration.

A stop is followed by a situation package to the on-call role and by an incident (UC-6.8).
Resuming is a person's act; the run continues at the boundary it stopped at.

## 2. How it is verified

- A stop requested in the middle of a step lands on the worker's boundary; a stop requested
  between steps takes effect at the next boundary; a resume repeats nothing that had completed.
- A stop by a person is available at every autonomy level, in every scope, and asks for no reason.
- A stop of one worker adapter halts every run it serves at its boundary, and runs on other
  adapters go on.
- The person who requested a stop receives a confirmation once it holds, naming the runs it
  stopped.
- Each criterion of ADR-0023 §2, on its own, triggers what the default rule says.
- A criterion may be added and a threshold changed; a configuration that empties the set — under
  which nothing leads to `escalate` — is refused.
- A decision to stop is recorded with the rule and the facts it read (`tests/governance`).
- No language model, classifier or statistical estimate decides to stop. A model may write the
  narrative afterwards, and the narrative names the rule and the facts.
- A running step is never aborted.

## 3. Where the boundary lies

**Not escalation.** Bringing a person in about a failure, with a situation package, is UC-4.5; the
definition's `UC-7.2` named both, and the repository keeps the emergency stop here
(`NUMBERING.md`). **Not detection.** A result defect no check found fires no rule (UC-4.10).
**Not the resume.** Whether and when a stopped run continues is a person's decision.

## 4. What it rests on

The run engine's stop at the boundary, built (ADR-0005); the rule and its criteria (ADR-0023), as
tenant configuration from `0.2.0`; UC-4.10 and UC-4.11 for the facts the rule reads, `0.5.0`;
method selection applied to governance itself — the decision is a rule, the narrative may be a
model (ADR-0004); a set that is reducible and never empty, as for anchors (ADR-0008). A stop by a
person arrives in `0.2.0` across scopes, the automatic trigger in `0.5.0`, which is this use case's
version. The adapter scope and the confirmation come from the catalogue of the second tenant —
"a stop per agent and global, with confirmation" (UC-03 B-11.04 and §7 row 6) — which the owner
accepted as a requirement in DEC-0199; added on 2026-10-23 (NTC-0233). Written first in
`UC-4-result-defects.md` on 2026-09-17, moved into this format in the migration's second step,
which left the requirement unchanged. Definition `UC-7.2`, escalation and
intervention: its emergency stop "at any time, globally and per process" is here; its escalation
"on uncertainty, failures or exceeding the frame" is UC-4.5, with UC-4.6, which escalates instead
of healing where it is unsure.

## 5. What is proven so far

The first condition, for a single run stopped by a person, by the named tests.

The adapter scope and the confirmation, by the named tests in `test_adapter_stop.py`,
`test_adapter_stop_calls.py`, `test_runner.py` and `test_open_work.py` (ADR-0138). A stop of one
worker halts every run inside a step on it at the worker's boundary and hands it no new step; a
stop of one connector or one model halts every run whose next call would go to it, before the
call, including a wait between two checks and a step whose model chain moves to it; runs on
other adapters go on. The stop is confirmed once it holds, addressed to whoever requested it and
naming the runs it halted; a stop that found none is confirmed and says so. A stop by a person
asks for no reason; it is offered on the command line only, not yet over the HTTP surface, the
web app, chat or MCP.

Stopping globally, by tenant and by process, by the named tests in `test_scoped_stop.py`
(ADR-0256): a stop of a process halts its run inside a worker step at the worker's boundary and
hands no further step on, while a run of another process goes on; a stop of the tenant halts
every run at levels 1 to 4 and asks for no reason; a stop of the instance is a stop of each
tenant it serves, confirmed in each. Offered on the command line (`taktusctl stop process`,
`tenant`, `global`).

The rule of ADR-0023 decides over a result reported wrong (ADR-0153): each criterion on its
own triggers what the shipped rule says, a criterion may be added and a threshold changed, and
a configuration under which nothing escalates is refused — by the named tests in
`tests/governance/test_result_defects.py`. Where it decides `stop`, it stops the process of the
reported result before the incident is written; the stop names the rule and the incident, the
incident the facts the rule read, its thresholds and the stop, and no person is its actor; a
verdict short of `stop` stops nothing (ADR-0256 §3). Not built: an incident and a situation
package after a stop a person requested; a run waiting for a person halts only when it would
next hand a step on.
