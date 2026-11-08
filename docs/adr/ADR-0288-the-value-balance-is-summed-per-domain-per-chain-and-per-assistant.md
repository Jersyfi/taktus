# ADR-0288 — The value balance is summed per domain, per chain and per assistant

**Status:** accepted · extends ADR-0244, ADR-0259, ADR-0261, ADR-0274 · UC-9.3, UC-15.1, UC-12.1, UC-12.3

## Context

The value ledger computes a balance per process (ADR-0244). Three use cases ask for it over a
group of processes:

- **A domain** (UC-15.1, UC-9.3): the processes of a domain of the tenant. The governance
  component keeps the domain record, with its processes (ADR-0259).
- **A chain across domains** (UC-15.4, UC-9.3): the processes a chain links. A chain is declared
  and run by `ChainRuns` (ADR-0274); it is not stored. Each link's run carries a plan whose
  identifier names the chain.
- **An assistant** (UC-12.1): the process an agent runs when it is called, its flow (ADR-0261).

A composed case (UC-12.3) is one process version; its balance is that process's balance.

## Decision

### 1. A group is a scope of the value ledger

A figure's scope may be `domain`, `chain` or `assistant`, beside the tenant, a process, a stream,
a unit, a role and a supplier. None of them is a person (principle 14).

### 2. The composition gathers the groups; the value component sums them

The facts handed to the value component carry each group: its scope, its subject, and the
processes it holds. The composition reads them from their owners:

- a domain from the governance component's domain records;
- a chain from the runs of its links, by the plan identifier `ChainRuns` gives each link
  (`pln_<chain>_<n>`); the function that names it also reads it back;
- an assistant from the catalogue's agent cores, by their flow.

The value component sums, per group, the figures the proof of value sums: time saved, the
personnel equivalent, cost, the cost of errors, licences, the balance and errors avoided. Each sum
names its method, the processes it holds, and those without a value. A sum with no value is
withheld, never zero.

### 3. Only what the reader may see

A group sums only the processes the reader may see. A process outside the reader's view
contributes nothing, as for every figure (ADR-0241).

## Alternatives

- **Store the sums.** They would be a second record of the balance (ADR-0029).
- **A scope per composed case.** A composed case is a process; a second scope would double it.
- **Store chains to read their links.** A chain's links are named by the runs that ran them.
  A chain that never ran has no figure to sum.

## Consequences

- `value/domain/model/figure.py`: three scopes more; `reporting`'s `Shown` takes the same.
- `value/domain/service/figures.py`: `Group` and `groups(...)`.
- `composition/figures.py`: the groups gathered; `composition/chains.py` names and reads a
  link's plan.

## Where this promise ends

- **Sums of the balance, not a balance of their own.** A group has no revert analysis, no
  quadrant and no recommendation; those stay per process.
- **A chain that ran.** A chain is known by the runs of its links. A chain declared but never run
  shows no figure.
- **Weights of the organisation's own criteria** are not applied to the sums; UC-9.3 still lacks
  them.
- **Not a measure of the domain's owner.** The owner is the addressee of the domain's figures,
  never their subject (ADR-0259).
