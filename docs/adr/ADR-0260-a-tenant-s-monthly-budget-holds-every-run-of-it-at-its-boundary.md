# ADR-0260 — A tenant's monthly budget holds every run of it at its boundary

**Status:** accepted · extends ADR-0005 (a budget is held by admission) and ADR-0166 (a unit's
monthly quota) · serves UC-8.5

## Context

A tenant wants one monthly money budget across all its processes and agents together, for
example a fixed amount a month. When the month's runs have cost it, every run of the tenant should
wait at its next step boundary, not only the run that crossed the line. The role that answers
for the money is told. A person raising the budget, or the month's turn, lets the runs go on.

ADR-0005 holds each run to its own budget. ADR-0166 holds an organisational unit's runs to a
monthly quota, committed when a run starts. Neither sums what the tenant's runs actually cost in
a month, and neither holds a run that is already running.

## Decision

### 1. The tenant sets the budget

A tenant sets an amount per currency per calendar month in UTC, and the role told once it is
reached. Nothing is shipped: a tenant that set none is held by none. `taktusctl budget set
--amount EUR=250 --role finance-lead` sets it, and `budget.configured` records who did.

### 2. A rule at every boundary

Before the run engine hands any step on, it sums what the tenant's runs created this month
cost. A run's cost is its recorded consumption, with tokens and compute priced at the
instance's table, whatever budget the run itself was held to. A rehearsal costs nothing and is
never held. Where a sum reaches its amount, the run waits at that boundary. It halts with cause
`parked`, its step blocked as `at_tenant_budget` and booked to `limit.budget`, with `budget.held`
in the ledger. It is tried again after the budget's interval, or at the month's turn if that
comes sooner. A running step is never aborted. It is a rule over stored records, never a model.

### 3. The role is told once a month

The first run that meets the reached budget in a month raises the incident `budget.reached`,
addressed to the budget's role, with the sums and the amounts. Later runs of the same month
raise nothing new.

### 4. Raised, or a new month

A budget a person raises lets each waiting run go on at its next try. At the month's turn the
last month's runs no longer count.

## Alternatives

- **The unit's quota of ADR-0166 for the tenant as a whole.** It commits a run's own budget when
  the run starts. A run without a money budget commits nothing, and a running run is never held.
- **A running total kept by the engine.** It would be cheaper to read. Several runners would
  write it at once, and a lost update would let a month cost more than its budget.

## Consequences

- `run/ports/tenant_budget.py`: `TenantBudget`, `MonthBudget`; the engine's
  `_over_tenant_budget` and `_at_tenant_budget`; `block.AT_TENANT_BUDGET`.
- `governance/application/service/tenant_budget.py`: `TenantBudgets`;
  `IncidentKind.BUDGET`; `composition/decisions.py`: `BudgetOfTheRun`.
- `taktusctl budget`; migration 0105: `tenant_month_budget`.
- `tests/components/run/test_tenant_budget.py`.

## Where this promise ends

The month's cost is known only at the instance's price table; without one, nothing is priced
and the budget holds nothing. Money a worker reports only when its assignment ends counts once
it is reported. A month may end over its budget by what the steps running when it was reached
still use, since a running step is never aborted. Reading the month's runs at every boundary
costs a read of every run of the tenant, which grows with the month. The role is told through
the incident; no channel message is sent on its own.
