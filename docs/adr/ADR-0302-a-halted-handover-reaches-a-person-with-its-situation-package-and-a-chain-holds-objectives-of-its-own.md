# ADR-0302 — A halted handover reaches a person with its situation package, and a chain holds objectives of its own

**Status:** accepted · extends ADR-0274, ADR-0252, ADR-0254 · UC-15.4 · DEC-0236

## Context

ADR-0274 halts a chain whose handover would leave out a declared item. It records
`chain.halted` and says the chain "goes to a person". Nothing delivered anything to a person,
and nothing let the person decide.

UC-15.4 requires that such a chain halts at that boundary and escalates (UC-4.5): the person
receives a situation package with five parts — what happened, what was tried, what is affected,
the options with their risks, and what is needed. It also requires that a chain has
service-level objectives of its own, beside those of its processes.

## Decision

### 1. The package is written by the governance component

`HandoverHalted` (`governance/domain/model/escalation.py`) is the record of a halted handover:
the chain and its run, the sending link and its run, the receiving link, every lacking item with
its step and clause, the items the sending run did hold, the links that finished before, the
links that did not start, and how many effects of the chain's runs left the system.
`escalations.handover_package` writes the five parts from it, as a rule. Its options are three:
give the lacking items by hand, stop the chain, or change the sending process and start again.
Each option names its risk.

### 2. It reaches the role the chain names

A chain may name `escalation`, as a process version does (ADR-0252): a role, a time to react and
a path. Without it, the role is `owner` and the path `channel`. `ChainRuns` raises a report of
kind `failure` to that role in the tenant's owner-facing channel. The ledger records
`chain.escalated` with the package by digest. Its outcome is `complete`, or the parts the
package lacks, with `_ledger` added where the package was recorded only.

### 3. The person decides, and the chain goes on

`ChainRuns.decide` takes the person's decision on a halted chain run:

- **given** — a value for exactly the items the handover lacked. The handover is built from
  what the sending run held and what the person gave. It is recorded as `chain.handover` with
  outcome `given_by_a_person`, and each item the person gave is marked `given_by: a person` in
  the handover's document. The next link starts with it.
- **stop** — the chain run is `stopped`, recorded as `chain.stopped`. A waiting chain may be
  stopped too.

Nothing is filled in by Taktus. A decision that names other items than the lacking ones is
refused.

### 4. A chain measures itself against its own objectives

A chain may name `slo`: a `latency` for one run of the whole chain, and a `completion` share of
its ended runs that finish, taken over its last twenty ended runs. When a chain run ends —
finished or stopped — it is measured once by the governance component's rule that measures a
process run (ADR-0254). The ledger records `chain.measured`, `met` or `missed_` with the
objectives missed, with the chain run's duration. The chain run keeps the outcome.

A chain's value balance is the sum of its links' balances (ADR-0288). This decision adds no
second one.

## Alternatives

- **Escalate through the sending link's run.** That run finished. Its escalation would say a
  run failed, which is not what happened: the run did what its version says, and the chain
  asked for more.
- **Let Taktus retry the sending link.** The same version gives the same result; a retry
  changes nothing and costs a run.
- **Measure a chain through the process objectives watch.** That watch reads run entries; a
  chain run is not a run.

## Consequences

- `chain.escalated` and `chain.measured` are new ledger kinds; `Chain` gains `slo` and
  `escalation`.

## Where this promise ends

- **No reminder.** A halted chain whose report is not answered is not recorded as overdue; the
  report stays open in the owner-facing channel.
- **The value a person gives is not checked by the chain.** The receiving link checks it as it
  checks any input.
- **The completion share counts the chain runs that ended.** A chain run that waits or is
  halted counts only once it ends.
- **A halted handover is not measured until a person decides.** The time it stood halted
  counts towards the chain's latency once it ends.
