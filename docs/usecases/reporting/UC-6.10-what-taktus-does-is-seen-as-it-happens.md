---
id: UC-6.10
title: What Taktus does is seen as it happens
component: reporting
epic: E6
serves: [P2, P7, P9, P14]
state: building
version: 0.3.0
tests: [tests/components/reporting/test_visual_vocabulary.py::test_a_reproducible_kind_is_drawn_apart_from_a_variable_one, tests/components/reporting/test_visual_vocabulary.py::test_a_persons_step_and_a_waiting_step_differ_from_both_and_from_each_other, tests/components/reporting/test_visual_vocabulary.py::test_exact_is_marked_and_no_other_class_carries_its_mark, tests/components/reporting/test_visual_vocabulary.py::test_no_token_is_a_colour, tests/components/reporting/test_visual_vocabulary.py::test_an_idle_system_draws_no_motion, tests/components/reporting/test_visual_vocabulary.py::test_without_motion_nothing_moves_and_nothing_is_lost, tests/components/reporting/test_visual_vocabulary.py::test_every_element_has_a_text_equivalent_with_its_method_class_and_state, tests/components/reporting/test_visual_vocabulary.py::test_a_representation_that_draws_an_llm_step_as_reproducible_fails, tests/integration/test_live_changes.py::test_changes_recorded_through_another_process_arrive_within_5_seconds, tests/integration/test_live_changes.py::test_with_the_notification_dropped_changes_arrive_within_the_same_bound, tests/integration/test_live_changes.py::test_a_reader_that_reconnects_to_another_replica_misses_nothing_and_sees_nothing_twice]
adrs: {ADR-0015: 3a42705e5561, ADR-0021: 202e0442e7ec, ADR-0026: ccc4bd1f5423, ADR-0029: 37c061ef032a, ADR-0055: 3fe20ea459f6, ADR-0059: 77fcc243cd82}
supersedes: null
---

# UC-6.10 — What Taktus does is seen as it happens

## 1. What must be achieved

A person who wants to know what Taktus is doing sees it, instead of reading it. Whatever Taktus
runs or manages has a **live representation**: a graph or a flow drawn from the records as they
are now, which moves when the work moves. A person can start from the whole and go down to a
single step, and back, without leaving the representation.

There are four levels, from the whole to the detail:

- **the overview** — the areas a reader may look into, the processes in each, and how busy each
  one is right now;
- **the process** — the steps of a process version as a graph, each step showing how it works;
- **the run** — where one run of that process stands: what is done, what is under way, what waits
  and on whom, and what it has consumed so far;
- **the origin of a result** — the path from a result back through the steps and inputs that
  produced it.

The intended impression is of a system one can watch at work, closer to a mind than to a machine
room. That impression is the design intent, not a claim about how Taktus works. The conditions
below define what it means. One of them matters most: the representation shows which steps are
reproducible and which are not, so that the impression never suggests that everything in Taktus
is a language model.

An **explanation** — why Taktus did something — is not required to be a picture. It is text,
placed at the element of the representation it explains.

## 2. How it is verified

- **Every level exists.** For every process version a reader may see, there is a representation of
  each of the four levels. A test registers a process, starts a run and completes a step with a
  result, and finds the overview, the process graph, the run and the origin of the result.
- **Drawn from the records, never by hand.** Every representation is produced from the records of
  the component that owns them (ADR-0029). No drawing is stored. A test registers a new process
  version and finds its graph changed with nothing else edited.
- **Live.** A change of a run's state — a step started, completed, failed or halted, a decision
  awaited — reaches every open representation of that run within 5 seconds, without the reader
  reloading.
- **Motion means something.** Every moving or pulsing element corresponds to work recorded at that
  moment. A test with no activity in the records finds no activity drawn: an idle system looks
  idle.
- **One visual vocabulary.** How a method kind, an exactness class and a state are drawn is defined
  once and used by every representation. A test fails a representation that draws them any other
  way.
- **Reproducible and variable are told apart.** The four reproducible method kinds (`rule`,
  `statistics`, `ml`, `neural`) are drawn differently from the variable ones (`llm`, `worker`). A
  person's step (`human`) and a waiting step (`wait`) each look different from both. A step of
  class `exact` is marked as such. The difference is carried by form and motion, never by colour
  alone.
- **The autonomy statement is shown with the process** (ADR-0026): the level it runs at, and why.
- **Calm on request.** The reader can stop all motion. The system setting for reduced motion is
  respected from the first moment. Without motion, the same information is still shown.
- **Every representation has a text equivalent** carrying the same figures and states. It serves a
  reader who cannot see the representation, and a person taking a process over (UC-6.3).
- **Playful about the work, never about people.** No score, rank, badge or comparison has a named
  person as its subject. The two exceptions of UC-6.4 — a person's own contribution (UC-13.5) and a
  decider's own response times (ADR-0015) — stay visible only to that person by default.
- **Only what the reader is entitled to.** An element the reader may not see (UC-6.4) is absent
  from the representation. It is not greyed out, and it is not counted.
- **The same figures as everywhere.** Every figure in a representation has one definition and one
  value, read from the component that owns it, and is in the export (UC-5.7).
- **Beyond the web app.** A channel that can show a live representation receives it. A channel
  that cannot receives the text equivalent and a link to the live representation.

## 3. Where the boundary lies

**Not a builder.** A representation shows and explains; processes are not assembled by dragging
blocks (non-goals: *not a visual block builder as the primary interface*). Changing a process
stays with the plan and with pair editing. **Not a literal picture of a brain.** The intended
impression is a direction for design, not a motif to be drawn. **No technology, style or palette
is required.** Which library draws, which transport carries the changes and what it looks like are
architecture and design, decided when the web app is built; the transport needs an ADR. **Not
real time** below the 5 seconds of section 2. **Not a replay** of past runs as motion; a past run
is shown in its final state. **Not the role-based views themselves**: who may see which figure is
UC-6.4, and this use case draws within it. **Not a business-intelligence tool**, and nobody is bound
to it (UC-5.7). **Not the inside of a connected system**: a representation ends where Taktus hands
work to a worker or a connector, and shows what came back.

## 4. What it rests on

The `reporting` component, which owns views and no figure (ADR-0029); role-based views (UC-6.4);
the export and the rule that no figure exists only in a view (UC-5.7); a person's own view
(UC-13.5) and the protective rule for response times (ADR-0015); the activity log (UC-6.1) and the
provenance chain (ADR-0021) as the records the run and the origin are drawn from; the process as a
directed graph of steps with method, reason and exactness class (`docs/architecture/control-plane.md`
§4, `docs/architecture/methods.md`); the autonomy statement (ADR-0026); the takeover test (UC-6.3).
Live changes need a way for the control plane to send state changes to a reader as they happen:
ADR-0055 decides it — Server-Sent Events read from the ledger, resumable by position, visible
only where the reader is entitled — before its code.

The roadmap's `0.3.0`, *visibility*, names a dashboard and a process diagram; blueprint UC-01 asks
for "process diagrams with their data" (`AF-01-dev-orchestration.md` §5). Neither version of the
project definition has this use case. The owner stated it on 2026-10-08 and accepted it as
written the same day (DEC-0055).

## 5. What is proven so far

The visual vocabulary is built, in the `reporting` component (ADR-0059). Nothing that draws is
built yet. By the named tests:

- The four reproducible method kinds share a straight edge and a regular pulse; `llm` and
  `worker` share a wavering edge and an irregular shimmer. A person's step and a waiting step
  each have an edge and a motion of their own. Each method kind has its own outline.
- `exact` carries a mark no other exactness class carries. No token of the vocabulary is a
  colour.
- Only a running step moves; a waiting step and every run never do, so an idle system draws no
  motion.
- Without motion, every motion is replaced by a still mark of its own, and nothing else changes.
- Every step and every run has a text that names its method kind, exactness class and state.
- A representation that draws an element another way than the vocabulary fails the check.

Not yet: the four levels, the live changes and the web app (#105, #183); the forms of a decision
request and of a result's origin, which arrive with the level that draws them.
