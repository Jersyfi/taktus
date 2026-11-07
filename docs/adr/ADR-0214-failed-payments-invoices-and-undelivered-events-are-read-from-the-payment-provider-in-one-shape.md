# ADR-0214 — Failed payments, invoices and undelivered events are read from the payment provider in one shape

**Status:** accepted · extends ADR-0150 (the payment provider connector), ADR-0206 (three
providers in one shape) and ADR-0130 (a step sees only its case's data) · UC-03 B-6.02,
B-6.04, B-6.06, DEC-0228

## Context

The three payment connectors read subscriptions only (ADR-0206). UC-03 asks for more of the
same providers: the events a webhook endpoint did not receive (B-6.02), the payments that
failed and the customer's way to pay again (B-6.04), and the outgoing invoices of a month
(B-6.06). Recurring revenue and churn (B-6.03) need the moment a subscription started
and ended, which the shared shape did not carry. Each provider's published API serves part of
this, and not the same part.

## Decision

### 1. Three more capabilities in the `payments` family, one shape each

| Capability, operation | First provider | Second provider | In-app service |
|---|---|---|---|
| `payments.failures.list` | open invoices whose payment was attempted and is still owed | subscriptions with consecutive failed payments | subscriptions in billing retry or grace period |
| `payments.invoices.list` | invoices created in a month | invoices dated in a month, the list read whole | not declared: invoices exist only per customer and only for web billing |
| `payments.events.undelivered` | events whose delivery to a webhook endpoint is pending or failed | not declared: the event list states no delivery | not declared: the API lists no events |

A failure is `{id, customer, subscription, amount, currency, attempts, failed_at, days_failing,
next_attempt_at, reason, update_url}`; an invoice is `{id, number, customer, subscription,
status, currency, total, tax, paid, remaining, issued_at, due_at, paid_at}`. Money is a whole
number of minor units, moments are seconds since the epoch. A value the provider does not state
is null, never derived from another field it does not mean. Each answer that depends on the
clock carries `as_of`, the moment the connector read it, so that `days_failing` is reproducible
from the reading.

### 2. The shared subscription gains its start and end

Every subscription carries `started_at` and `ended_at`, and every item `interval_count`. The
first provider gives `start_date` and `ended_at`; the second `start_time`, and the moment of its
status change for an ended one; the in-app service `starts_at`, and `ends_at` for an expired
one.

### 3. A customer's failures and contact are scoped

`payments.customers.failures` and `payments.customers.contact` belong to the scoped capability
`payments.customers`. The contact, a customer's e-mail address, is answered **only** to a call
that carries a case's scope naming that customer; a call without a scope is refused as
`out_of_scope`. No list ever carries an address. The in-app service declares no contact: the
store holds the customer's address and reminds them itself.

### 4. A repeat changes nothing because nothing is replayed

B-6.02 finds the undelivered events and names them to a person. It does not replay them. The
first provider's API reference names no operation that resends an event; its guide for
undelivered events tells the receiver to fetch and process them itself. The receiver is the
business's own system, which no public interface reaches. The second provider can resend an
event, but its list does not say which one was lost, so resending would be a guess.

## Alternatives

- **The customer's address in the failures list.** Every failing customer's address would sit
  in one stored result. Scoped per case, a run sees one address, for the case it serves.
- **A failure's moment taken from the first provider's charge.** It needs a second expansion per
  invoice; the finalization is the moment collection started, and the reason is on the intent.
- **Resending through the provider's command-line tool.** It is not the published API.

## Consequences

- Each connector declares the new operations; the fakes serve the documented endpoints;
  connector tests cover them; conformance runs unchanged.
- `PAYMENTS_TOKEN` needs read access to invoices, customers and events at the first provider,
  and the Invoicing feature at the second (`CREDENTIALS.md`).
- B-6.02, B-6.04 and B-6.06 are bundles of the blueprint `software-operations`.

## Where this promise ends

- **Undelivered events are found, never replayed** (§4), and only at the first provider, and
  only for the 30 days its API keeps.
- **A failure's moment differs by provider.** The first gives the invoice's finalization, the
  second the last failure, so a retry restarts its days; the in-app service gives none, and
  B-6.04 cannot stage its reminders there.
- **The second provider names no page to change the payment method** and no invoice's
  customer or payment moment; those fields are null.
- **The outgoing invoices are read, not exported.** The accounting connector proposes bookings
  of incoming invoices, and the documents connector reads incoming EN 16931 invoices; neither
  takes an outgoing one, and the business's bookkeeping has no open interface (UC-03 B-6.06).
- **Proven against fakes of the published APIs** (DEC-0225).
