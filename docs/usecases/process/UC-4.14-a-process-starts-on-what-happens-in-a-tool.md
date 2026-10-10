---
id: UC-4.14
title: A process starts on what happens in a tool
component: process
epic: E4
serves: [P1, P4, P8, P12]
state: specified
version: 0.2.0
tests: []
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
