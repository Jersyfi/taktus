---
id: UC-7.10
title: Recurring decisions become rules on proposal
component: decision
epic: E7
serves: [P8, P10, P14]
state: built
version: 0.6.0
tests: [tests/governance/test_rules_from_precedent.py::test_a_consistent_pattern_is_proposed_as_a_decision_request_naming_its_precedents, tests/governance/test_rules_from_precedent.py::test_nothing_changes_before_the_proposal_is_accepted, tests/governance/test_rules_from_precedent.py::test_an_accepted_rule_answers_its_kind_and_names_itself, tests/governance/test_rules_from_precedent.py::test_a_declined_proposal_changes_nothing_and_is_not_proposed_again_at_once, tests/governance/test_rules_from_precedent.py::test_one_decision_otherwise_or_with_a_modification_breaks_the_pattern, tests/governance/test_rules_from_precedent.py::test_a_rule_that_declines_halts_the_run_as_a_person_s_decline_would, tests/governance/test_rules_from_precedent.py::test_a_retired_rule_answers_nothing, tests/governance/test_rules_from_precedent.py::test_a_rule_is_no_person_s_confirmation_at_level_two, tests/governance/test_rules_from_precedent.py::test_no_rule_is_proposed_over_an_act_an_anchor_keeps_with_a_person, tests/governance/test_rules_from_precedent.py::test_only_a_tenant_s_strategic_anchor_may_ever_be_answered_by_a_rule, tests/governance/test_rules_from_precedent.py::test_the_pattern_is_found_by_count_and_no_language_model_reads_the_register, tests/governance/test_rules_from_precedent.py::test_a_decision_a_rule_took_is_nobody_s_response_time]
adrs: {ADR-0008: e6a4e033abd4, ADR-0015: 3a42705e5561, ADR-0042: bfc76a4a3797, ADR-0088: 655238bb8152, ADR-0152: b3f4df1be26f, ADR-0161: 80b8a7d53d72}
supersedes: null
---

# UC-7.10 — Recurring decisions become rules on proposal

## 1. What must be achieved

A person who answers the same question the same way, time after time, is doing work a rule
could do. Taktus notices it. Where the decision register shows a consistent pattern — the same
kind of request answered the same way — Taktus proposes a rule that answers that kind from then
on. The rule exists only once a person accepted it. Autonomy grows through use, and control is
not given away: what an anchor keeps with a person stays with a person, and a rule can be
retired at any time.

## 2. How it is verified

- **A kind of request** is one anchor at one step of one process. **A pattern is consistent**
  when the five most recent decisions of one kind, all decided after the last proposal of that
  kind was decided, chose the same option, by the same role, without modifications, and none of
  them was taken by a rule. One decision that chose otherwise, or carried a modification, breaks
  the pattern.
- The proposal is a decision request in the one shape of UC-7.4, addressed to the role that
  decided the precedents. It names every precedent by its register entry. A test decides one
  kind consistently and finds the proposal, with each precedent named in it.
- Nothing changes before the proposal is accepted: a request of the kind raised while the
  proposal is open waits for a person as before. A proposal declined changes nothing, and the
  kind is not proposed again before as many new decisions agree.
- An accepted rule answers every later request of its kind with its option. The request is still
  raised and still in the register; its entry names the rule, and no person is named as having
  decided it. A rule is no person's confirmation of a step: at level 2 the step still waits for
  one. A decision a rule took is nobody's response time (ADR-0015).
- A person can retire a rule; from then on its kind is asked again.
- A rule that would decide an act an anchor keeps with a person is never proposed: a request of
  the class `legal` or `correction`, of the frame's own anchors, of a step's own `ask`, an
  approval or a sample, or a proposal to change a process. Only a request of a strategic anchor
  of the tenant's own configuration may be answered by a rule, because the tenant may reduce its
  strategic class (ADR-0008) and the person who accepts the rule makes that reduction.
- The pattern is found by a rule or a statistic, never by a language model. A test finds that the
  detection imports no model port and no adapter.

## 3. Where the boundary lies

**Not method maturation.** Moving a step to a trained model on evidence is UC-8.4 and DEC-0164;
a rule from precedent answers a request and changes no process. **Not a level.** A rule does not
raise an autonomy level and no level adopts a rule. **Not the anchor set.** Which acts are
anchored stays the tenant's configuration (UC-15.5). **Not a judgement of the person.** The
register is read by kind of request, never by who answered (principle 14).

## 4. What it rests on

The decision register and its requests (ADR-0042, UC-7.4); ADR-0008, whose consequence names the
register as a precedent memory from which rules are proposed; the step's own `ask` (ADR-0088);
the checks that put a value to a person (ADR-0152); the protective rule for response times
(ADR-0015). ADR-0161 builds it; which requests a rule may answer and how many precedents make a
pattern are NTC-0249. The roadmap's `0.6.0` names it; UC-7.4 left it to this milestone. Written
in the branch that builds package B (DEC-0222), beside its implementation.

## 5. What is proven so far

Every condition of §2 is proven by the named tests: the proposal after five consistent
decisions, naming them; nothing answered while it is open; the rule answering its kind once
accepted, naming itself; a decline, a different answer and a modification each holding the
pattern back; a rule that declines halting the run; a retired rule answering nothing; a rule
being no confirmation at level 2; no proposal over a legal anchor or a step's own ask; and the
detection importing no model.
