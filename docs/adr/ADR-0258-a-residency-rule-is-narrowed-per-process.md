# ADR-0258 — A residency rule is narrowed per process

**Status:** accepted · extends ADR-0116 §3 (the tenant's residency rule) and ADR-0157 (workers
held to it) · serves UC-11.1

## Context

UC-11.1 asks that a residency rule is set per tenant and narrowed per process and per data
class, with the narrowest holding where several apply. ADR-0116 built the rule per tenant and
per data class. Models and workers are held to it at run time (ADR-0116 §4, ADR-0157). A process
could not narrow it: a payroll process in a tenant whose rule is `eu` could not be kept to the
tenant's own infrastructure without narrowing every other process with it.

## Decision

### 1. A rule per process

The tenant's rule gains a location per process, by the process's identifier. A process's
location is never wider than the tenant's. A rule that would widen it is refused, as a data
class's is.

### 2. The narrowest holds

Where data of a class is processed in a run of a process, the permitted location is the
narrowest of three: the tenant's, the data class's and the process's. The run asks the rule with
the run's process, before it routes a step to a model and before it hands a step to a worker.
A model or a worker outside that location is never chosen. A worker step with only such workers
fails before anything is assigned, naming the rule.

### 3. Set on the command line

`taktusctl residency set --process payroll=own` narrows a process. `--clear-process payroll`
removes its rule. Every change is `residency.configured`, as before.

### 4. Read by the previous release

A rule that names no process is written as before, without the field. The previous release then
reads it (ADR-0093).

## Alternatives

- **The data class as the only narrowing.** A process handles several classes and a class
  appears in several processes. Narrowing a whole process through its classes narrows the same
  classes everywhere else.
- **The location on the process version.** A version is never changed once registered. Narrowing
  a process would need a new version, and a person who changes residency is not changing the
  process.

## Consequences

- `governance/domain/model/residency.py`: `ResidencyRule.processes`, `permitted(class, process)`.
- `run/ports/residency.py`: `Residency.permitted(tenant, data_class, process)`.
- `taktusctl residency set --process`, `--clear-process`.
- `tests/components/governance/test_residency.py`, `tests/components/run/test_worker_residency.py`.

## Where this promise ends

The process's rule holds where the tenant's rule already holds: at the choice of a model and at
the choice of a worker. A connector declares no location yet, and nothing holds a connector call
to the rule. Registration does not yet refuse a version whose step would be bound outside the
permitted location: the binding is made when a run routes the step. The hosts an execution unit
may reach are its frame's allowed hosts and are not narrowed by the rule.
