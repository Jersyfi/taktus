---
id: UC-7.4
title: The decision request
component: decision
epic: E7
serves: [P9, P10, P11, P14]
state: built
version: 0.2.0
tests: [tests/governance/test_anchors.py::test_no_autonomy_level_overrides_an_anchor, tests/governance/test_anchors.py::test_the_halt_is_at_the_boundary_and_the_rest_of_the_run_continues, tests/governance/test_anchors.py::test_the_request_holds_every_part_of_the_one_shape, tests/governance/test_anchors.py::test_a_request_missing_a_part_is_not_raised, tests/governance/test_anchors.py::test_an_anchored_step_whose_request_is_not_raised_fails_without_its_act, tests/governance/test_anchors.py::test_a_free_text_answer_is_not_acted_on_until_its_reading_is_confirmed, tests/governance/test_anchors.py::test_an_answer_no_option_can_be_read_from_changes_nothing, tests/governance/test_anchors.py::test_an_answered_request_is_an_entry_in_the_register_linked_to_run_and_request, tests/governance/test_anchors.py::test_waiting_work_is_in_the_run_s_history_and_the_decider_s_list_overdue_shown, tests/governance/test_anchors.py::test_another_identity_cannot_read_a_decider_s_response_time_under_their_name, tests/governance/test_anchors.py::test_response_times_are_aggregated_by_role_and_department_over_two_deciders, tests/adapters/rest/test_decisions.py::test_nobody_reads_a_deciders_response_time_under_their_name]
adrs: {ADR-0008: e6a4e033abd4, ADR-0015: 420aac4db0cc, ADR-0017: c932691e9072, ADR-0042: bfc76a4a3797}
supersedes: null
---

# UC-7.4 — The decision request

## 1. What must be achieved

A process runs unattended while its direction stays with a person. When a run reaches an act that
is a person's — under an anchor, or a question the process cannot answer itself — it halts at the
step boundary and asks. The question is not an alarm: it is a planned, expected question in normal
operation, with a worked answer proposed, and the person can decide it without having followed the
run. Their answer is never acted on before it is understood: Taktus says how it read the answer,
and acts only once the person has confirmed it. Every answer becomes a record that later cases can
be judged by.

## 2. How it is verified

- A decision request has one shape in every process and every channel: the situation, exactly what
  must be decided, the options with their consequences and one recommended with its reason, what is
  blocked, and the date an answer is needed by (ADR-0008, `docs/architecture/governance.md` §3.1).
  A request without a part is not raised.
- Raising one halts the run at a step boundary, never inside a step and never after the act it asks
  about; the run waits in `waiting_human` and resumes at that boundary.
- A free-text answer is not acted on. It is read, its interpretation is sent back in one message,
  and only the confirmed interpretation takes effect. A test answers in free text and finds the run
  still waiting until the confirmation arrives.
- Every answered request produces an entry in the decision register, linked to the run and the
  request.
- Work that waits on an answer is visible in the decider's view and in the run's history; a request
  past its date is shown as such. An unanswered request is never a silent stall.
- How long a decider takes to answer is visible to that decider only by default, and aggregated for
  anyone else by role or department, never by person (ADR-0015).

## 3. Where the boundary lies

**Not escalation.** A fault with a situation package is UC-4.5; a decision request carries options,
not a report of damage (`docs/architecture/governance.md` §3.3). **Not which acts are anchored.**
The anchor set is the tenant's (UC-15.5, ADR-0008). **Not rules from precedent.** Turning a
consistent pattern in the register into a rule, on the person's acceptance, is the roadmap's
`0.6.0`. **Not the repository's register.** How this project asks its owner is ADR-0017, which
applies the same shape by hand; this use case is the product's mechanism.

## 4. What it rests on

ADR-0008, which makes the decision request a domain object beside the strategic anchor; the
contract `contracts/shared/v1/DecisionRequest.json`, which exists; the `decision` component, which
holds requests and the register; the anchors at step boundaries of `0.2.0`, built by ADR-0042;
the protective rule for response times (ADR-0015). This repository already works this way by hand
under ADR-0017 — the register under `docs/decisions/`, the gate on its shape — and that is the
mechanism's first use, not its implementation in the product. Numbered after version 2 of the
definition, in conversation (`NUMBERING.md`); no version of the definition has this use case. Filed
under `decision`, the component that owns decision requests (DEC-0070).

## 5. What is proven so far

Built by ADR-0042 (issue #79) and proven by the named tests. An anchored act halts the run at the
step boundary before anything of its step starts, at each of levels 1 to 3, and the steps that do
not depend on it run on; the run waits in `waiting_human` and continues from that boundary once
the decision took effect. Every request has the one shape, its recommended option with its
reason; one missing a part is not raised, and its act is not performed. A free-text answer is
read by a rule, sent back in one message, and leaves the run waiting until the reading is
confirmed; an answer from which no single option can be read changes nothing. Every applied
request is an entry in the register, linked to the run, the step and the request. Waiting work is
in the run's reason and ledger and in the decider's list, overdue shown. A decider reads their own
response times; anyone else reads them aggregated by role or department over at least two
deciders, never under the decider's name. Not built: the request in a chat (#85), the decider's
page in the web app (`0.3.0`), rules from precedent (`0.6.0`).
