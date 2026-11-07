# ADR-0256 — A stop is scoped to a process, a tenant or the instance, and a rule may request one

**Status:** accepted · extends ADR-0138 (a stop scoped to an adapter) · carries out ADR-0023 §1
and ADR-0153's verdict `stop` · serves UC-7.2

## Context

UC-7.2 asks for a stop whose scope is global, a tenant, a process, a run, or an adapter. ADR-0138
built the adapter and the run. It left out the process, the tenant and the instance.

UC-7.2 also asks for an automatic trigger: a rule over measurable criteria that yields
`continue`, `escalate` or `stop` (ADR-0023). ADR-0153 built the rule over a result reported
wrong. Its verdict `stop` was the incident's severity and stopped nothing.

## Decision

### 1. A stop of a process and a stop of the tenant

A stop of a process halts every run of that process at its next step boundary. A stop of the
tenant halts every run of the tenant there. Both are kept as ADR-0138's stop is, with a scope
beside it: `adapter`, `process` or `tenant`. A run's process is the part of its version reference
before `@`.

The run engine reads the held stops before it hands any step on. A run a stop of its process or
its tenant covers halts there, with cause `stop` and a reason that names the stop. A run inside a
worker step is asked to stop at the worker's boundary by its runner, at the renewal of its lease,
as for an adapter. A running step is never aborted.

The confirmation is ADR-0138's. It holds once no run the stop covers is inside a step. It names
the runs the stop halted: those halted with cause `stop` under its scope since the request.

### 2. A stop of the instance is a stop of each tenant

A stop of the instance is a stop of each tenant the instance serves, requested at once by the
same person. Each is confirmed in its own tenant. A stop is kept per tenant because every record
of a tenant is (ADR-0020).

### 3. A rule's stop

Where the tenant's rules decide `stop` over a result reported wrong, the governance component
requests a stop of the process that produced the result. It does so through a port the
composition answers from the run component's stops, before the incident is written. The stop
names the rules that fired and the incident. The incident holds the facts the rules read and
their thresholds, and names the stop. `stop.requested` has no actor, since no person acted. Its
outcome is the scope, its incident reference the incident, and its content the rule.

No language model, classifier or statistical estimate takes part in the decision. A narrative
written afterwards names the rule and the facts the incident holds (ADR-0023 §4).

### 4. Kept where the previous release does not read

A stop of a process or of the tenant is a row of its own table, `scoped_stop` (migration 0105).
The previous release reads `adapter_stop` and would refuse a row it cannot read. A stop of an
adapter is still written there, in the shape the previous release wrote (ADR-0093).

### 5. Every scope on the command line

`taktusctl stop process NAME`, `stop tenant` and `stop global` request the stops of §1 and §2.
None asks a reason. A stop of one run stays `RunEngine.request_stop`.

## Alternatives

- **One row per stop of the instance.** A record that spans tenants breaks row-level security,
  under which every row belongs to one tenant.
- **A rule's stop of every affected process.** A result read downstream is one the rule escalates
  through the incident. Stopping every reader would stop processes that have done nothing wrong.
- **The stop columns widened in place.** A nullable adapter column and a scope column would be
  allowed by expand-then-contract. The previous release would still fail on the row a stop of a
  process writes there.

## Consequences

- `run/domain/model/stop.py`: `StopScope`, the stop's process, rule and incident.
- `run/application/service/stops.py`: `request_process`, `request_tenant`, `request_everywhere`,
  `covering`.
- The engine halts a covered run before its next step; `stops_held` reads the process stops.
- `governance/ports/stops.py`: `ProcessStops`; `ResultDefects(stops=...)`;
  `composition/stops.py`: `RuleStops`.
- Migration 0105: `scoped_stop`.
- `tests/components/run/test_scoped_stop.py`; `tests/governance/test_result_defects.py`.

## Where this promise ends

A stop takes effect at the next boundary of a run its runner holds. A run that waits for a person
halts when it would next hand a step on, not at the request. The stop's confirmation does not
name it until then.

A rule's stop exists only where a result was reported wrong and assessed (ADR-0153). A result
defect no check found fires no rule. A stop is not yet followed by an incident of its own when a
person requests it. The situation package goes to the on-call role only through a rule's
incident (ADR-0179).

A stop of the instance stops the tenants served at the moment of the request. A tenant created
afterwards is not stopped. The surfaces other than the command line offer the stop of an adapter
alone.
