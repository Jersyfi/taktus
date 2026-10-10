---
id: UC-4.14
title: A process starts on what happens in a tool
component: process
epic: E4
serves: [P1, P4, P8, P12]
state: built
version: 0.2.0
tests: [tests/composition/test_reactions.py::test_a_labelled_issue_starts_the_process_its_trigger_names_without_a_person, tests/composition/test_reactions.py::test_a_redelivery_starts_nothing_twice, tests/composition/test_reactions.py::test_a_reaction_interrupted_before_it_was_published_completes_nothing_twice, tests/composition/test_reactions.py::test_one_event_starts_each_process_once, tests/composition/test_reactions.py::test_a_condition_that_does_not_hold_makes_the_reaction_wait_not_vanish, tests/composition/test_reactions.py::test_an_event_received_before_the_version_was_registered_starts_nothing, tests/composition/test_reactions.py::test_an_unplaced_sender_starts_nothing, tests/integration/test_event_reactions.py::test_an_event_starts_exactly_one_run_whoever_reacts, tests/components/process/test_event_triggers.py::test_every_entry_must_hold_and_each_holds_for_any_of_its_values, tests/components/process/test_event_triggers.py::test_registration_refuses_what_the_contract_refuses_with_every_finding_at_once]
adrs: {ADR-0035: 070012ed0fb2, ADR-0040: af5a6cdb5889, ADR-0048: da64f1fa1ccb}
supersedes: null
---

# UC-4.14 — A process starts on what happens in a tool

## 1. What must be achieved

When something happens in a tool the organisation works in — an issue is opened or labelled, a
pipeline completes, a branch is pushed, a message mentions Taktus — the process set up to react
to it starts by itself. No person starts it, and nobody has to watch the tool for it.

Which happening starts which process is declared in the process version, beside its schedule. A
run started this way is held to everything a run started by hand is held to: its budget, its
autonomy, its anchors, its ledger. Whether it starts is as reproducible as the run itself.

## 2. How it is verified

- A delivery the intake accepts, whose sender is placed, and which matches a trigger of a
  process's active version starts one run of that process, with the inputs the trigger declares,
  on the automation role's next pass. No person runs a command for it.
- The same delivery received twice, or reacted to by two instances, starts the process once. An
  instance stopped between accepting the delivery and starting the run starts it after its
  restart, once.
- An event that matches triggers of two processes starts one run of each. An event that matches
  two triggers of one process starts that process once.
- Whether a trigger matches is decided by a rule over the event alone: the same event and the
  same version give the same answer every time. No language model or other probabilistic method
  decides whether a run starts.
- A trigger whose condition does not hold makes its event wait, not vanish: the run starts on the
  first pass after the condition holds.
- An event whose sender the identity component cannot place starts nothing (UC-1.7). A run an
  event started acts for the identity its sender was placed as.
- An event received before the process's active version was registered does not start it.
- A version is refused at registration when an event trigger names a kind outside the events
  contract's catalogue, a condition outside its list, or leaves a declared input without a
  value.
- Every run an event started says in the ledger which trigger and which event started it,
  without the event's content.

## 3. Where the boundary lies

**Not delivery by the tool.** An event that never reaches the intake — sent while no instance
received it and not sent again — starts nothing. Taktus does not ask a tool what it missed; a
process that must not miss anything carries a schedule trigger too. **No judgement in a
trigger.** A process that must judge whether there is work does so in its first step, under that
step's method. **Not authorisation.** Who may cause which event to start which process is
UC-7.3. **Not Taktus's own events.** An anchor hit or a milestone reached happen inside Taktus;
reacting to them is not required here. **Not the decoupled mode** of UC-5.2 as a whole, which
rests on this use case and asks more of it.

## 4. What it rests on

The events contract, `contracts/events/v1`, which names the kinds, the filter and the condition;
ADR-0048, which states how one delivery starts each process once; ADR-0035, its counterpart for
time triggers; ADR-0040, by which a command acts for its sender. UC-1.1 ends where an input is a
command; this use case starts there. UC-5.2 rests on it. The roadmap's `0.2.0` names event
reactions (#76), and P-02 and P-03 of the dev-orchestration blueprint are its first users (#87).
Not in the definition: written by the session that made #76 buildable, and put to the owner in
DEC-0124.

## 5. What is proven so far

Every condition of section 2, by the named tests, over the memory stores and against PostgreSQL:

- A labelled issue whose sender is placed starts one run of the process its trigger names, with
  the declared inputs, on the automation role's next pass, acting for the sender; nobody runs a
  command.
- A redelivery, an entry a stopped leader left unpublished, and two automation roles start the
  process once, and complete the intake once.
- One event starts each of two processes once, and a process with two matching triggers once.
- A filter is a rule over the event alone: every entry must hold, each any of its values.
- A condition that does not hold leaves the reaction waiting; it starts once the condition holds.
- An unplaced sender and an event older than the active version start nothing.
- Registration refuses a kind outside the catalogue, an unknown condition and an input left
  without a value, with every finding at once.
- Every run an event started carries `run.triggered` with the outcome `event`.

Not proven against the real repository service: the connector's kinds are held to recorded
deliveries. No installed instance runs the automation role yet.
