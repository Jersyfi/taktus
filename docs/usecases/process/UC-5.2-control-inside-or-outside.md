---
id: UC-5.2
title: Control inside or outside Taktus, per process
component: process
epic: E5
serves: [P1, P5]
state: built
version: 0.2.0
tests: [tests/composition/test_control_mode.py::test_the_same_steps_give_the_same_results_ledger_and_provenance_in_either_mode, tests/composition/test_control_mode.py::test_a_task_the_tool_withdraws_is_not_continued_past_the_next_boundary, tests/composition/test_control_mode.py::test_a_decoupled_version_names_where_its_task_is_read_and_a_coupled_one_does_not, tests/composition/test_control_mode.py::test_moving_between_the_modes_is_a_new_version_outside_any_frame]
adrs: {ADR-0011: f25413d512b9, ADR-0024: 52ba89e4adec, ADR-0272: 0532cbc63139}
supersedes: null
---

# UC-5.2 — Control inside or outside Taktus, per process

## 1. What must be achieved

An organisation decides per process where its control sits. Either Taktus controls it — it decides
the order and the timing of the steps, and the organisation's tools are sources and destinations
(coupled). Or the control stays where it already is — a workflow in the ticket system decides what
happens next, and Taktus is the worker that takes a task, does it, and writes the result back
(decoupled). Both are equal, both can be chosen for each process, and both can be mixed within one
organisation and within one chain of processes.

An organisation does not have to move a working process into Taktus to have Taktus work on it.

## 2. How it is verified

- A process version declares which of the two it is. The same steps run in either mode produce the
  same results, the same ledger entries and the same provenance, except for how the run was started
  and where its state is reported.
- In the decoupled mode the external tool's state is the authority. Taktus changes it only through
  what its own steps do, and a task the external tool withdraws is not continued past the next step
  boundary.
- Every capability Taktus offers a process is available in both modes: anchors, budgets, the
  removal test, the takeover instructions, the ledger and provenance apply the same way. A test
  runs one process in both modes and finds each of them.
- Moving a process from one mode to the other is a new process version, not a migration: its
  history stays, and no run in progress changes mode.
- The external tool is named by its capability, never by product (principle 4).

## 3. Where the boundary lies

**No copy of the external workflow.** Taktus does not model the ticket system's workflow; it reads
and writes what its steps need. **No general synchronisation** between the external state and
Taktus beyond that. **No particular tool.** Which ticket systems can hold control depends on which
connectors exist; this use case requires that any tool with a connector can.

## 4. What it rests on

The connector contract in both directions (ADR-0024); triggers from a bundle and event reactions
(`0.2.0`), the latter required by UC-4.14; the bundle format, where ADR-0011 applies the same coupled-or-decoupled logic to storage.
P-02 and P-03 of the dev-orchestration blueprint already work this way by hand — the issue tracker
holds the state, Taktus refines and implements and writes back — without a declared mode.
Definition `UC-5.1` (coupled) and `UC-5.2` (decoupled), filed as one use case because principle 5
is the choice between them.

## 5. What is proven so far

A version declares its control, `coupled` or `decoupled`, and a decoupled one the read that
answers its task's state in the external tool, by capability (ADR-0272). The same steps run in
either mode give the same results, ledger entries and provenance. A task the tool withdraws is
not continued past the next step boundary, and the run says why; a coupled run never asks the
tool. A move between the modes is a new version, and the earlier one stays — by the named tests.
Not built: the test that runs one process in both modes and finds anchors, budgets, the removal
test and the takeover instructions applied the same way; the two above are shown, and the engine
applies the others to either mode without asking which, which is why the state is `built`.
