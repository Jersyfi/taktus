# ADR-0206 — Two more payment providers serve the same capabilities, and a renewal is read from the end of the paid period

**Status:** accepted · extends ADR-0150 (the payment provider connector) and ADR-0199 (the
match of payments against entitlements); amends ADR-0199's boundary on B-5.06's renewal ·
issues #437, #401, UC-03 B-6.01, B-3.04, B-5.06

## Context

B-6.01, B-3.04 and B-5.06 read subscriptions through `payments.subscriptions` and the scoped
`payments.customers` (ADR-0150, ADR-0199). One connector served them. A software business that
sells through another provider, or through the app stores' in-app purchases, could not run them.
ADR-0199 left B-5.06's renewal unbuilt: "no capability serves a contract's end date".

## Decision

### 1. Two more connectors in the first one's shape

`paypal/` reads a payment provider's subscriptions API; `revenuecat/` reads an in-app
subscription service. Each serves `payments.subscriptions.list`, `.read` and the scoped
`payments.customers.subscriptions`, all `read`, in the first connector's output shape. The
bundles run on any of the three unchanged. All three take the credential `PAYMENTS_TOKEN`.

| | Second provider | In-app service |
|---|---|---|
| list | the API's own list, 20 per page | no list of a project's subscriptions exists: customers are read page by page, then each one's subscriptions |
| one customer's | the whole list, kept to the payer: the API has no filter by customer | the customer's own list |
| status | mapped: `ACTIVE` active, `SUSPENDED` paused, `CANCELLED`/`EXPIRED` canceled, approval states incomplete | mapped: grace and retry past_due, `expired` canceled, `unknown` null |
| `current_period_end` | `billing_info.next_billing_time` | the period's end, in seconds |
| `cancel_at_period_end` | always false: the API has no such flag | whether it will not renew |
| items | product, price and interval from the plan | one seat per item, without a price |

A value the API does not give is answered as null, never guessed.

### 2. B-5.06 prepares a renewal from the end of the paid period

Every provider answers `current_period_end`. B-5.06 version 2 takes an optional input
`renew_before`, a moment in seconds since the epoch, and keeps by the rule `filter` the paid
subscriptions whose period ends at or before it, ordered by that end. A rule that read the
clock would not give the same result twice, so the moment is the trigger's. The corridor
`payments.renewals_due` turns each renewal due into an incident for the responsible role.
Nothing leaves the system: the contract and the price stay with a person (UC-03 §6).

## Alternatives

- **A connector per process.** The match is the same whichever provider holds the money.
- **The clock read inside the rule.** The result would depend on when it ran, and `exact`
  needs recomputation.
- **The in-app service's list built from webhooks.** It would need state of its own in the
  connector.

## Consequences

- Two connector directories, two fakes, adapter tests, conformance entries (C-11 for both).
- `B-5.06-business-seats.yaml` version 2 with the step `renewals`;
  `tests/composition/test_software_operations_payments.py` runs B-6.01, B-3.04 and B-5.06 on
  every provider.

## Where this promise ends

- **The in-app service's list costs one request per customer**, against a provider limit of
  480 a minute; a large customer base reads slowly, and `limit` bounds it.
- **The in-app service gives no price and one seat per item.** B-5.06's seat check has nothing
  to compare there, and B-6.01 matches by product only.
- **The second provider's one-customer read reads the whole list**, up to 10000 subscriptions.
- **The end of a paid period is not a contract's end.** A contract signed outside the provider
  is not seen; the role that renews reads it.
- **Proven against fakes of the published APIs** (DEC-0225).
