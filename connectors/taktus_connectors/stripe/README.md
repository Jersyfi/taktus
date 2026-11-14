# The payment provider connector — the Stripe REST API

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over the subscriptions of the Stripe REST API. This directory, this file and the configuration
that points at it are the only places that name the product. Everywhere else it is the
capabilities `payments.subscriptions` and `payments.customers` (ADR-0150).

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.stripe --port 9111
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address, `https://api.stripe.com` by default; point it at the fake under
`tests/fakes/payment_service.py` to run without a network. Added to an instance by one entry
of `TAKTUS_CONNECTORS` per capability: `payments.subscriptions=http://payments-connector:9111/mcp`,
and `payments.customers` at the same address.

## Why not the vendor's own server

The provider ships a server on the connector protocol. The `vendor` connector can put such a
server behind the contract under a manifest of its effects (#410, ADR-0117). This connector
does not, for one reason. The vendor's server answers a tool in text. A match of a payment
against an entitlement is held `exact` (UC-03 B-6.01, B-3.04), and a rule can only match fields
it can read one by one. So the connector reads the REST API, whose answers are records.
ADR-0150 records the decision.

## What it declares

Two operations of `payments.subscriptions`, both of effect `read`, one request per page.

`payments.subscriptions.list`:

| Input | Meaning |
|---|---|
| `status` | `active` (default), `past_due`, `unpaid`, `canceled`, `incomplete`, `incomplete_expired`, `trialing`, `paused`, or `all` |
| `limit` | how many subscriptions at most, 1 to 10000 (default 1000); at most 100 pages of 100 are read |

The output is `subscriptions` and `complete`, which says whether every subscription fit within
`limit`.

`payments.subscriptions.read` takes `id`, a subscription's identifier `sub_…`, and answers one
subscription.

`payments.customers.subscriptions` takes `customer`, a customer's identifier `cus_…`, and
answers `customer`, every `subscriptions` of that customer in every status, and `complete`. Its
capability is declared `scoped` (ADR-0130): a step that serves one customer's case carries the
customer as its scope, and a call that names another customer is refused as `out_of_scope`
before the provider is asked. Conformance check C-11 proves it against the fake.
`payments.subscriptions` is not scoped: a reconciliation reads every subscription.

Each subscription is reduced to these fields:

| Field | Meaning |
|---|---|
| `id` | the subscription's identifier |
| `customer` | the customer's identifier, and nothing else of the customer |
| `status` | the provider's status |
| `current_period_end` | the end of the paid period, in seconds since the epoch |
| `cancel_at_period_end` | whether it ends then |
| `items` | each `price`, `product`, `quantity`, `unit_amount` in minor units, `currency` upper-cased, `interval` |
| `metadata` | the subscription's metadata, every value as text |

The customer's e-mail, name and address, and the payment method, are never copied. No match
needs them, and what is not read cannot leak. Every request names `Stripe-Version: 2024-06-20`,
so that the record's shape does not change when the account's default version does.

A request the provider refuses, or a subscription it does not know, is `invalid`. A key it
does not admit is `unauthenticated`, and one without the right to read is `forbidden`. A
throttled or failing provider is `unavailable` and retryable. The provider's message is never
copied into an error: only its type and code are (`operations.py`).

Each subscription carries too `started_at` (`start_date`) and `ended_at`, and each item
`interval_count`, for B-6.03's revenue (ADR-0214, ADR-0231).

## Failed payments, invoices, undelivered events (ADR-0214)

Five more operations, all `read`, one request per page:

| Operation | Capability | Reads |
|---|---|---|
| `payments.failures.list` | `payments.failures` | `GET /v1/invoices?status=open&expand[]=data.payment_intent`, keeping the invoices whose payment was `attempted` and of which an amount remains |
| `payments.customers.failures` | `payments.customers`, scoped | the same, `customer=` the case's subject |
| `payments.customers.contact` | `payments.customers`, scoped | `GET /v1/customers/<id>`: the `email`, answered only to a call that carries the customer's case as its scope |
| `payments.invoices.list` | `payments.invoices` | `GET /v1/invoices` with `created[gte]` and `created[lt]` of a month, `month` YYYY-MM or the month before |
| `payments.events.undelivered` | `payments.events` | `GET /v1/events?delivery_success=false`: events still pending or failed at a webhook endpoint |

A failure is `{id, customer, subscription, amount, currency, attempts, failed_at, days_failing,
next_attempt_at, reason, update_url}`: the invoice's identifier, the amount remaining in minor
units, `attempt_count`, the invoice's finalization as the moment collection started and failed,
the whole days since, `next_payment_attempt`, the payment intent's `last_payment_error`
decline code, and `hosted_invoice_url`, the page where the customer pays with another method.
An invoice is `{id, number, customer, subscription, status, currency, total, tax, paid,
remaining, issued_at, due_at, paid_at}`, the tax being `total` less `total_excluding_tax`. An
event is `{id, type, created, hours_pending, pending_webhooks, object, subject}`: the kind and
identifier of the object it is about, and nothing else of it. Answers that depend on the clock
carry `as_of`. No answer but the contact carries an e-mail or a name.

The documentation it follows: the API reference for listing invoices,
<https://docs.stripe.com/api/invoices/list>, and events, <https://docs.stripe.com/api/events/list>
(`delivery_success`, 30 days kept), the invoice and event objects, retrieving a customer,
<https://docs.stripe.com/api/customers/retrieve>, and the guide for undelivered events,
<https://docs.stripe.com/webhooks/process-undelivered-events>. **The API reference names no
operation that resends an event**; the guide tells the receiver to process it itself, so the
connector resends nothing.

## Intake: payment events (ADR-0337)

The provider's webhook is taken by the `intake` tool under `hmac-sha256-stamped`:
`Stripe-Signature` carries `t=<moment>` and one or more `v1=<digest>`, the HMAC-SHA256 of
`<moment>.<raw body>` with the endpoint's signing secret, in hex; one must verify, before the
body is read, and a moment more than 300 seconds from the arrival is a replay. `invoice.payment_failed`
becomes `payment.failed` (`customer`, `payment`); `customer.subscription.created`, `.updated` and
`.deleted` become `subscription.changed` (`customer`, `subscription`, `change`); every other type
is `unsupported_event`. The event's identifier is the provider's `evt_…`, so a redelivery is one
event. Identifiers only: no amount, no address. [`payloads/`](payloads/) holds deliveries written
for the test from the published payloads. The secret is `PAYMENTS_INTAKE_SECRET`.

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `PAYMENTS_TOKEN` | actions: the **requesting identity's** restricted key, with read access to subscriptions, customers, products, prices, invoices and events, and nothing else | the file `TAKTUS_CREDENTIAL_PAYMENTS_TOKEN_FILE` names, read at the moment of each call, never stored |

The contract has no connector without the requesting identity's credential (C-03): a call
that references none is refused. The key goes to the configured API and nowhere else.
`CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9111/mcp --scenario connectors/taktus_connectors/stripe/scenario.json
```

[`scenario.json`](scenario.json) lists the active subscriptions of the fake, and reads one it
does not know as the call the provider refuses. It names no write, and C-05 passes as not
applicable. `--fault NAME` breaks exactly one check (`connectors/serving.py`);
`tests/conformance/test_connector_v1_business.py` runs every fault.
