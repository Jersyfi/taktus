# NTC-0030 — UC-6.8: an escalated result defect carries the situation package

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-08
**Raised in:** [#61](https://github.com/Jersyfi/taktus/issues/61)
**How it follows:** the owner's project definition, version 2, UC-4.6 (the repository's UC-4.5): every business-critical or business-damaging finding or problem brings in a person with a complete situation package — what happened, what was tried, which systems and data are affected, the options with their risks, the documentation and access needed. A wrong result that the stop rule escalates or stops is such a finding. The amendment requires the same five parts for it as for a failure.

## 1. What was decided

`docs/usecases/governance/UC-6.8-incident-and-incident-report.md` gains a requirement. When the
rule of ADR-0023 escalates or stops on a wrong result, the person it brings in receives a situation
package with the five parts a failure's escalation carries under UC-4.5; a package with a part
missing says which part it lacks. Section 1 states it, and section 2 has the condition.

## 2. The evidence

- The definition's escalation (its UC-4.6) covers *findings or problems*, not only failures; the
  repository's UC-4.5 says in section 1 that a business-critical finding always brings in a person,
  and in section 3 that a wrong result is not its subject.
- ADR-0021 split the two: a failure halts or escalates under UC-4.5; a wrong result is found by a
  check (UC-4.10), escalated or stopped by a rule (ADR-0023, UC-7.2) and tracked as an incident
  (UC-6.8). The first text of UC-6.8 gave the incident a severity, a timeline, a scope, a plan and a
  report, but not the parts "what was tried", "the options with their risks" and "the documentation
  and access needed".
- The first text of UC-7.2 already said that a stop is followed by "a situation package to the
  on-call role, produced under UC-6.8"; UC-6.8 did not require one.

## 3. What was considered

- **Requiring it in UC-4.5.** Rejected: UC-4.5 is about failures, and ADR-0021 keeps the two apart;
  the incident is where a wrong result reaches a person.
- **Asking it in DEC-0069.** Rejected: the package adds nothing the definition does not ask; it
  closes a gap the split of ADR-0021 left between two use cases. DEC-0041 makes that the session's.

## 4. Which entry permits it

M2.7, *"Bringing a use case up to the owner's own definition: an amendment of what a use case
requires that only restores what `docs/vision/` and the owner's project definition already
require."* The amendment restores definition UC-4.6 for wrong results and adds nothing beyond it.
