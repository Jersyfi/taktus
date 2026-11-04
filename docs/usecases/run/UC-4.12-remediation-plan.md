---
id: UC-4.12
title: Remediation plan
component: run
epic: E4
serves: [P6, P10, P11, P12]
state: building
version: 0.5.0
tests: [tests/governance/test_result_defects.py::test_a_plan_for_results_inside_the_system_runs_without_a_halt, tests/governance/test_result_defects.py::test_every_result_that_left_gets_an_outward_correction_after_it_is_produced_again, tests/governance/test_result_defects.py::test_every_plan_step_says_what_a_person_needs_to_carry_it_out_without_taktus, tests/governance/test_result_defects.py::test_a_correction_that_cannot_be_made_at_once_says_so, tests/governance/test_anchors.py::test_a_level_four_run_halts_at_each_anchor_with_a_decision_request, tests/governance/test_remediation_run.py::test_a_plan_inside_the_system_runs_again_without_a_halt_and_names_the_correction, tests/governance/test_remediation_run.py::test_an_outward_correction_halts_with_a_request_of_class_correction_at_level_4, tests/governance/test_remediation_run.py::test_without_a_correction_anchor_that_names_the_act_the_outward_step_is_not_made, tests/governance/test_remediation_run.py::test_a_result_defect_starts_its_remediation_run_once_from_the_correction]
adrs: {ADR-0008: e6a4e033abd4, ADR-0013: 1da224cdeaf4, ADR-0021: dc801ddd1c47, ADR-0022: 69572977f46b, ADR-0153: f720e5930f42, ADR-0160: 34e64cb9d5ce, ADR-0179: b70d264ab655}
supersedes: null
---

# UC-4.12 — Remediation plan

## 1. What must be achieved

The impact analysis (UC-4.11) exists. Something has to be done about the affected results, and some
of them have left the system. Taktus produces the plan on its own, at any autonomy level, and
executes it under the rule of ADR-0022.

- **The plan is a process.** For every affected result it holds the steps that produce it again
  from corrected inputs, in dependency order, with the same methods and exactness classes as the
  original steps. For every result that has left the system it adds the *outward* correction — the
  re-issued invoice, the re-sent file, the restated value — as a step of its own, and names what
  the receiving party holds before and after.
- **Inside the system** — re-running steps, replacing artifacts, recomputing values nothing outside
  has seen — the plan runs at the autonomy level of the process. It is a retry with a longer
  memory.
- **Any outward correction** halts at the step boundary before it and raises a decision request of
  class `correction` (ADR-0022 §3). Its options are the plan and the alternatives Taktus rejected,
  with a recommendation. The person decides, and the answer is confirmed before it is acted on
  (ADR-0008). This holds at every autonomy level.
- **The plan can be carried out by hand.** Not every partner can be automated — a tax authority
  takes a letter, a customer a phone call — and a plan that only works inside the system is
  worthless exactly where it is needed most. The person who decides the correction anchor receives
  the plan in a form a person can carry out without Taktus, whether Taktus or a person then
  executes it.

Every result produced again gets a provenance record of its own, whose inputs name the corrected
inputs. The wrong result is never overwritten and never deleted: it stays, with its record, and the
incident links the two. Nothing else keeps "since when" answerable the next time.

## 2. How it is verified

- A plan for a result inside the system runs without a halt.
- A plan with one outward correction halts exactly before that step, with a decision request of
  class `correction`; the anchor holds at autonomy level 4 (`tests/governance`).
- An outward correction is never executed without a person, at any level.
- The result produced again carries a new provenance record, and the old result and its record
  are unchanged.
- Every plan passes the takeover test (ADR-0013 B): a test reads a generated plan and finds, for
  every step, the system to act in, the record to change, the value before, the value after, the
  order and how to tell that the step is done — and no reference to a Taktus identifier a person
  could not look up.
- The steps a person executed by hand are recorded in the incident with the role that did them and
  when. Which identity acted is recorded in the activity log (UC-6.1), not in the incident.
- A plan never produces two truths silently: an outward correction that cannot be made atomically
  — the partner keeps the old file while the new one is prepared — says so in the plan, so that the
  person decides with it in view.

## 3. Where the boundary lies

**Not the analysis.** What is affected is UC-4.11, and analysis is never anchored (ADR-0022 §1).
**Not the anchor's decision.** Whether an outward correction is made is the person's. **Not an act
outside Taktus.** A remediation a person carries out by hand is outside Taktus and outside the
anchor; Taktus records what it is told was done, and that is why the plan must be executable by
hand. **Not the incident.** Tracking and delivering it is UC-6.8.

## 4. What it rests on

The impact analysis (UC-4.11); the correction anchor in the tenant's anchor set (ADR-0022), whose
predicate "has it left the system" is built and tested in the governance component; the decision
request and its confirmation loop (ADR-0008, UC-7.4); the run engine, which executes the plan like
any process (ADR-0021); the takeover test's shape (ADR-0013 B, UC-6.3). Written first in
`UC-4-result-defects.md` on 2026-09-17, moved into this format in the migration's second step. The
requirement is unchanged except in one place: the first text recorded "who" executed a step by
hand in the incident, while UC-6.8 says an incident never names a person. The incident now names
the role, and the identity stays in the activity log; that change is the owner's and stands, by
DEC-0069. No version of the definition has this use case.

## 5. What is proven so far

The plan is produced from the impact analysis (ADR-0153): a plan for results inside the system
has no outward step; every result that left gets an outward correction after the step that
produces it again; every step names the system, the record, the value before and after, the order
and how to tell it is done, as text a person carries out without Taktus; a correction that cannot
be made at once says so. The plan runs on the engine as a remediation run of the wrong run
(ADR-0179 §3): the corrected step carried with the value a person gave, every step it is not built
on carried as it was, everything built on it run again at the process's level without a halt; every
step that acts outward halts first with a request of class `correction`, at level 4 too, and is not
made where no correction anchor names its act. The steps run again get provenance records of their
own that name the corrected result; the wrong run and its records stay — by the named tests. Not
built: a derived result in another run or process produced again by the engine; the steps a person
executed by hand recorded in the incident.
