# ADR-0153 — A result defect is bounded, decided on by rule, and planned for

**Status:** accepted · builds on ADR-0021 (failure, result defect, incident), ADR-0022 (the
correction anchor) and ADR-0023 (the rule that decides escalation and stop) · serves UC-4.11,
UC-4.12, UC-6.8, UC-7.2 · issue #92

## Context

ADR-0021 named the result defect: a result that counted and is wrong. It recorded the provenance
chain first, so that "since when?" can be answered later. ADR-0022 defined when a result has left
the system and anchored its correction. ADR-0023 said that a rule, never a model, decides whether
a result defect escalates or stops. None of it was built beyond the chain and the predicate.

Two ways to find a result defect exist now. A person records what a result should have been
(`step.corrected`, ADR-0084). A sampling check puts a result to a person, who may judge it wrong
(ADR-0152). A check that finds a wrong result on its own after the fact is DEC-0223's question.

## Decision

### 1. One report starts four pure steps

A result reported wrong — corrected, or sampled and judged wrong — is assessed by the governance
component (`domain/service/defects.py`). The assessment reads provenance records and ledger
entries and changes nothing, at any level (ADR-0022 §1):

1. **Since when.** The records of the step, in its process, ordered by their ledger entry, are
   the step's series. Walking back from the reported result, the first record whose way of
   producing differs from the one before it is the cause. A difference is another process
   version, method, model, prompt, adapter or adapter version. The window starts at the result
   after the change and ends at the newest result. Where no change is found, the analysis says
   so; the window then starts at the earliest record and is *unbounded*.
2. **What is affected, built on it, and has left.** Every result of the window, and everything
   derived from one of them by the chain read forward, across runs and processes. Each names its
   class, the steps that read it, and the egress entry through which it left, if any.
3. **The decision.** The tenant's rules read five facts: the strictest class affected, whether
   anything left, whether a legal anchor applies to a step that read an affected result, the
   size of the window in runs and in time, and the business relevance where it is given. Every
   rule whose conditions all hold fires; the verdict is the strictest of them, `continue` when
   none fired. The decision records the rules that fired, the facts and the thresholds.
4. **The plan.** For each affected result in order, a step that produces it again inside the
   system. For each result that left, an outward correction after it. Every step names the
   system, the record, the value before and after, the steps it waits for, and how to tell that
   it is done. A delivered message cannot be taken back, and the plan says that the receiver
   then holds two values for a while.

Provisionally, under DEC-0223, a `sourced` step without a check is not refused.

### 2. The rules are the tenant's, and never empty

The rules are part of the tenant's watch configuration (`WatchConfiguration.defect_rules`). A
tenant may add a rule, change a threshold, or turn a `stop` into an `escalate`. A set with no
rule that escalates or stops is refused. The shipped set is NTC-0242's.

### 3. The incident carries the decision

`raise` makes an incident of kind `result.defect` with the facts the rule read and its verdict,
in one transaction with `incident.raised`, whose outcome is the verdict. A second report of the
same result raises nothing. The incident names no person (principle 14).

### 4. The plan is written for a person

`render` writes the plan as numbered steps a person carries out without Taktus. An outward step
is the correction anchor's: whoever carries it out, by Taktus or by hand, does so after the
person of the anchor decided it (ADR-0022 §3). `taktusctl defect assess` prints the analysis, the
decision and the plan; `taktusctl defect raise` raises the incident as well.

## Alternatives

- **A source whose digest changed as the cause.** A partner's file changes its digest every day;
  every run would be a change, and every window one result long. The way the step produces —
  version, method, model, prompt, adapter — is what a defect that "began on Monday" changed.
- **A model's judgement of severity.** Rejected by ADR-0023: the same facts must give the same
  decision.
- **The plan as a bundle the engine runs at once.** The plan's inside steps are re-runs of the
  original steps with corrected inputs, and which input is corrected is a person's answer to the
  defect. The plan is produced as a document first; executing it as a process is the next step.
- **The rules as a record of their own.** A new table for one list per tenant. The watch
  configuration is the tenant's rules about its runs already.

## Consequences

- `governance/domain/model/defects.py`, `governance/domain/service/defects.py` and
  `governance/application/service/result_defects.py`; `IncidentKind.RESULT_DEFECT`;
  `WatchConfiguration.defect_rules`.
- `taktusctl defect assess` and `taktusctl defect raise` (`adapters/driving/cli/defect_command.py`).
- `tests/governance/test_result_defects.py` holds the analysis, the rule, the plan and the
  incident to UC-4.11, UC-4.12, UC-6.8 and ADR-0023.

## Where this promise ends

The analysis reads what the chain recorded; it cannot bound a result produced before it, and
says so. It finds a cause only in how the step produced, not in the content of a source. A legal
anchor downstream is found where an anchor applies to a reading step's process, adapter or the
capabilities it read; an anchor that names only the actions a step's work declares is not seen
from its record. The rule reads business relevance only where the report gives it: a process
version does not carry one yet. A set of rules that escalates only on an unreachable condition
passes the refusal. The assessment reads every run's records of the tenant, which grows with the
ledger. The plan is a document: no engine executes it yet, no request of class `correction` is
raised by it, and nothing yet refuses to close an incident while one is open. No assessment
starts by itself: a person or a process calls it, on a correction or a sample judged wrong. The
incident is not delivered into the organisation's own tracking system, and no situation package
or narrative is produced for it yet (UC-6.8).
