---
id: UC-6.14
title: The work inside a step is seen as it happens, and shared by role
component: reporting
epic: E6
serves: [P2, P6, P7, P14]
state: building
version: 0.5.0
tests: [tests/adapters/rest/test_step_trace.py::test_every_event_is_shown_with_its_sentence_masked_and_the_ledger_holds_none, tests/adapters/rest/test_step_trace.py::test_the_trace_is_shown_to_the_owner_and_a_role_it_is_shared_with_and_nobody_else, tests/adapters/rest/test_step_trace.py::test_a_share_names_a_role_never_a_person, tests/adapters/rest/test_step_trace.py::test_a_trace_of_another_tenant_a_withheld_run_or_no_workers_step_is_none, tests/adapters/rest/test_step_trace.py::test_an_event_reaches_a_reader_who_asks_again_within_5_seconds, tests/components/reporting/test_step_traces.py::test_a_line_past_the_default_retention_is_erased_and_a_newer_one_kept, tests/components/reporting/test_step_traces.py::test_a_retention_the_tenant_sets_is_recorded_and_erases_by_it, tests/components/reporting/test_step_traces.py::test_the_scheduler_erases_once_an_interval_for_every_tenant_it_serves, tests/adapters/persistence/test_trace_store.py::test_lines_take_the_next_position_once_each_and_read_after_one, tests/adapters/persistence/test_trace_store.py::test_a_line_recorded_before_the_cut_is_erased_and_a_later_one_kept, tests/adapters/persistence/test_trace_store.py::test_a_trace_is_shared_with_roles_and_a_share_withdrawn, tests/adapters/persistence/test_trace_store.py::test_the_retention_is_the_default_until_the_tenant_sets_one, tests/adapters/persistence/test_trace_store.py::test_another_tenant_sees_no_line_and_no_share]
adrs: {ADR-0007: 26804369941b, ADR-0015: 3a42705e5561, ADR-0029: 37c061ef032a, ADR-0055: 182c84e9cdbd, ADR-0063: c36342b4637a, ADR-0119: 535c88b02054, ADR-0135: 882b538e072f}
supersedes: null
---

# UC-6.14 — The work inside a step is seen as it happens, and shared by role

## 1. What must be achieved

A worker reports what it does while it works a step: the steps of its own plan, its progress,
every tool it called or refused, the choices it made and why, what it used, what it produced,
and how it ended. This record is the step's **trace**. A person who looks at a run sees the trace
of each of its worker steps, as it grows, at the step it belongs to. A person who wants someone
else to look at it shares it with a role.

The trace is content: it holds the worker's own words. The ledger holds no content, so the trace
is kept outside it, for as long as the tenant decides, and then deleted.

## 2. How it is verified

- **Shown at the step.** The run level shows, for every step a worker runs, the events of its
  trace in the order the worker reported them. Each event names its type and what the worker
  contract carries for it (`contracts/worker/v1`, ADR-0007).
- **Live.** An event the worker reports reaches every open representation of its step within
  5 seconds, without the reader reloading. A test has a worker report events while a reader
  follows the step, and measures the bound.
- **Only what the reader is entitled to.** A trace of a run the reader may not see (UC-6.4) is
  answered exactly as one that does not exist.
- **Shared by role.** A person who may see a trace shares it with a role. The share gives a link
  to the step in the web app. The link opens the trace only for a signed-in identity that holds
  the role and may see the run. Without an identity, the link opens nothing. Sharing and
  withdrawing a share are ledger entries that name the role. A share never names a person as its
  receiver, and it never widens what the role may see of runs.
- **No person assessed.** No figure in a trace or in a share has a named person as its subject,
  and no measure is computed from traces per person (principle 14).
- **The ledger stays content-free.** The ledger records no text of a trace. A test reads every
  ledger entry of a run whose worker reported text, and finds none of that text.
- **Kept for the tenant's retention, then deleted.** Each tenant sets how long a trace is kept;
  a tenant that set nothing holds a default the architecture names. Setting it is a ledger entry.
  A trace whose retention has ended is deleted. A test shows a trace past its retention gone and
  one within it kept.
- **Secrets masked.** No secret value the instance holds is shown, shared or stored in a trace.
  A test has a worker report one and finds it masked.

## 3. Where the boundary lies

**Not more than the worker reports.** The trace holds the events of the worker contract. A tool's
arguments arrive as a digest and stay one (W-09). A diff appears as the artifact the worker
produced, by kind and digest. **Not steering.** Watching a step does not change it; steering a
worker inside its step is W2 of DEC-0195 (#403). **Not other methods.** A step on a model, a
rule or a person has no trace here; its record is the run level of UC-6.10. **Not an open
link.** A share is to a role, and an identity opens it. **Not an archive.** Nothing of a trace is
kept past its retention, in the ledger or elsewhere. **Not a replay.** A past step's trace is
shown as it was recorded, without motion.

## 4. What it rests on

The run level of UC-6.10 and the stream of changes (ADR-0055); what each role sees (UC-6.4); the
worker contract's events (ADR-0007, `contracts/worker/v1`) and the rule that a worker's activity
is fed from them (UC-6.1); the rule that no figure assesses a named person (ADR-0015); the
web app's sign-in (ADR-0119); the `reporting` component, which owns views and no figure
(ADR-0029). The owner accepted it as W8 of DEC-0195, with the transcript as an artifact with a
retention period and the ledger content-free (`docs/research/2026-10-13-warp-review.md` §4,
question 4). Issue #409 carries it. The version is `0.5.0`, the milestone DEC-0195 places it in.

## 5. What is proven so far

Every event a worker reports is kept as a line of its step's trace outside the ledger (ADR-0135)
and shown in order, with its text masked; the ledger of the run holds none of that text. The
trace is shown to the owner and to a role it is shared with, and to nobody else; a share names a
role and refuses a person. A trace of another tenant, of a run the reader may not see, or of a
step no worker runs is answered as none. An event reaches a reader who asks again within
5 seconds. A line past the tenant's retention is erased and a newer one kept; setting the
retention is recorded; the scheduler erases for every tenant it serves — by the named tests. The
web app's trace panel is tested in `web/src/lib/trace.test.ts`. That the link opens nothing
without an identity rests on the web app's sign-in and is not proven by a test named here.
