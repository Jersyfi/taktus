# ADR-0023 — An automatic emergency stop is rule-based

**Status:** accepted · applies ADR-0004 to governance itself

## Context
Governance.md §4 gives the emergency stop to a person: at any time, globally and per process.
With result defects detected by the system (ADR-0021, `0.5.0`), the system will also be in a
position to *trigger* one: a detected result defect in a billing process is a reason to stop
that process before the next invoice goes out.

An emergency stop triggered in error is its own damage. At autonomy level 4 the stop halts a
department: nothing is booked, nothing is shipped, nothing is answered until a person has
looked. A false stop once a week makes level 4 worthless; a false stop during a month-end close
costs more than most result defects. The trigger must therefore be as reliable as the thing it
protects.

ADR-0004 says how a method is chosen for a step: by what the step needs, with reproducibility
and cost weighed against judgement. A decision to stop needs reproducibility above everything.
The same facts must lead to the same decision every time, and a person must be able to check
afterwards why it was taken. That rules out a probabilistic method for the decision. It does not
rule one out for describing the situation once the decision is taken.

## Decision

### 1. The decision is a rule
Whether to escalate a result defect and whether to stop a process is decided by a rule over
measurable criteria. No language model, no classifier and no statistical estimate produces
that decision. The rule reads facts the ledger, the provenance chain and the process
definition hold, compares them with thresholds, and yields one of `continue`, `escalate`,
`stop`. Given the same facts, it yields the same answer. The facts and the thresholds it used
are recorded with the decision.

### 2. The criteria
The criteria are few, measurable and documented here. Each is a number or a yes/no the system
already holds.

| Criterion | Measured as | Source |
|---|---|---|
| **Size of the window** | the number of runs, or the span of time, between the first affected result and now | the provenance chain (UC-4.11) |
| **Exactness class affected** | the strictest class among the affected results: `exact`, `sourced`, `tolerant`, `free` | the provenance records |
| **Has left the system** | whether any affected result has an egress entry (ADR-0022 §4) | the ledger |
| **A legal anchor downstream** | whether a step that reads an affected result, transitively, sits under a legal anchor | the process definitions and the tenant's anchor set |
| **Business relevance** | the relevance the tenant assigned to the process: a small ordered scale, set at commissioning | the process version |

A rule combines them. Two examples the default set ships with:

- *stop* when an `exact` result has left the system **and** a legal anchor lies downstream;
- *escalate* when the window exceeds a configured span **or** the class is `exact` or
  `sourced`, whatever else holds.

### 3. Configurable per tenant, never empty
Every tenant configures the thresholds and may add a criterion of its own, provided the
criterion is measurable from data Taktus holds. A tenant may raise a threshold, lower one, or
turn a `stop` into an `escalate`. **The set cannot be emptied**: a tenant cannot configure a
process for which no criterion leads to `escalate`. That mirrors the anchor set of ADR-0008 —
reducible, never empty — for the same reason. An unattended process with no condition that
brings a person in has no owner in practice, whatever the configuration says.

### 4. The narrative may come from a language model
Once the decision is taken, what a person reads — the incident description, the situation
package, the report — may be produced by a language model. It is the kind of text ADR-0004
assigns to that method: explanation under ambiguity, for a reader. It must state which rule
fired, on which facts, with which thresholds, so that the reader can check the decision
against §1 without trusting the prose. The narrative is exactness class `free`; the decision it
describes is `exact`, and `exact` admits a rule (ADR-0014).

### 5. The model carries its own consequence
This is the method selection of ADR-0004 applied to governance itself. Taktus chooses the
method per step by what the step needs, and records why. The step "decide whether to stop" needs
reproducibility and auditability and gets a rule. The step "describe the situation" needs
language and gets a language model. The two steps sit in one process and carry different
methods and different exactness classes — which is what every Taktus process does. A governance
mechanism that chose differently for itself than it demands of the processes it governs would
have no ground to stand on.

## Alternatives
- **A model judges severity.** It would take the whole situation into account, including what
  no criterion captures, and it would take it into account differently each time. A false
  stop that cannot be explained cannot be prevented from recurring.
- **A person decides every stop.** Correct where time allows, and it does not always: an
  invoice run at 03:00 with a detected `exact` result defect should stop before 03:01. The
  rule stops; the person decides what happens next.
- **Many criteria, finely weighted.** A score over twenty inputs is a model in disguise: the
  weights are guesses, the decision is not readable. Five criteria and a rule a person can
  hold in their head.
- **A fixed set, not configurable.** A start-up and a bank do not draw the line at the same
  window size. The set is fixed in kind, configurable in threshold.

## Consequences
- UC-7.2 (emergency stop) states that the automatic trigger is rule-based, with the criteria of
  §2 and the rule that the set cannot be emptied; UC-6.8 states that the narrative may come
  from a language model and must name the rule and the facts.
- The governance component, from `0.2.0`, holds the criteria as tenant configuration with the
  defaults of §2 and refuses a configuration that empties the set; `tests/governance` proves
  both.
- Every automatic stop and every escalation is a ledger entry with the rule and the facts as
  tokens; the narrative is an artifact referenced from it, never the entry itself (ADR-0006).
- The process's business relevance becomes a field of the process version at `0.2.0`, set at
  commissioning, so that the rule has it.
