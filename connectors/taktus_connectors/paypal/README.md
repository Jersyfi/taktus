# The second payment provider connector — the PayPal Subscriptions API

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over the subscriptions of the PayPal Subscriptions API v1. This directory, this file and the
configuration that points at it are the only places that name the product. Everywhere else it
is the capabilities `payments.subscriptions` and `payments.customers` (ADR-0150, ADR-0206).

It answers the same operations as the first payment provider connector
([`stripe/`](../stripe/README.md)), under the same names and in the same shape, so that B-6.01,
B-3.04 and B-5.06 of the blueprint `software-operations` run on either provider unchanged. It
is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.paypal --port 9144
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address, `https://api-m.paypal.com` by default (`https://api-m.sandbox.paypal.com` for the
provider's sandbox); point it at the fake under `tests/fakes/billing_plans_service.py` to run
without a network. Added to an instance by one entry of `TAKTUS_CONNECTORS` per capability:
`payments.subscriptions=http://payments-connector:9144/mcp`, and `payments.customers` at the
same address.

## The documentation it follows

- the Subscriptions API v1 reference, <https://developer.paypal.com/docs/api/subscriptions/v1/>,
  and its OpenAPI document, <https://developer.paypal.com/api/subscriptions/v1/schema.json>:
  `GET /v1/billing/subscriptions` (`statuses`, `page_size` at most 20, `page`, a `next` link),
  `GET /v1/billing/subscriptions/{id}`, `GET /v1/billing/plans/{id}`, the fields of a
  subscription, a plan and a billing cycle, and the error bodies `{name, message, debug_id,
  details}`;
- the authentication guide, <https://developer.paypal.com/api/rest/authentication/>:
  `POST /v1/oauth2/token` with HTTP Basic over the client identifier and secret and
  `grant_type=client_credentials`.

## What it declares

Three operations, all of effect `read`. Every request is one unit of consumption: the access
token each call exchanges first, each page of the list, and each plan read (once per call).

`payments.subscriptions.list` takes `status` and `limit` as the first connector does. The
provider's statuses are mapped into the shared vocabulary:

| Shared | The provider's |
|---|---|
| `active` | `ACTIVE` |
| `paused` | `SUSPENDED` |
| `canceled` | `CANCELLED`, `EXPIRED` |
| `incomplete` | `APPROVAL_PENDING`, `APPROVED` |
| `all` | every status |

`past_due`, `unpaid`, `trialing` and `incomplete_expired` have no counterpart and are refused as
`invalid`. A subscription in a trial cycle is `ACTIVE` at the provider and answered `active`.

`payments.subscriptions.read` takes `id`, a subscription's identifier (`I-…`).

`payments.customers.subscriptions` takes `customer`, the payer's identifier
(`subscriber.payer_id`), and is declared `scoped` (ADR-0130). **The provider's list cannot be
narrowed to a payer**: the API has no such filter. The connector therefore reads the whole list,
up to 10000 subscriptions, and answers the subject's subscriptions only; `complete` is false
when the list was longer. A call that names another customer than the case's subject is refused
as `out_of_scope` before the provider is asked. Conformance check C-11 proves it.

Each subscription is reduced to the shared fields:

| Field | From |
|---|---|
| `id` | `id` |
| `customer` | `subscriber.payer_id`, and nothing else of the subscriber |
| `status` | as mapped above |
| `current_period_end` | `billing_info.next_billing_time`, in seconds since the epoch: the moment the next cycle is billed is the end of the paid one. Null where the provider gives none, as for a cancelled subscription |
| `cancel_at_period_end` | always false: the provider has no such flag; a cancelled subscription ends at once |
| `items` | one item, the subscription's plan: `price` the plan's identifier, `product` its `product_id`, `quantity` the subscription's quantity where it is a whole number, `unit_amount` the fixed price of the plan's first regular billing cycle in minor units (ISO 4217), `currency`, `interval` the cycle's `interval_unit` in lower case |
| `metadata` | `custom_id`, the merchant's own identifier, where the subscription carries one |

What is not known is not guessed: a quantity that is not a whole number is null, and so is the
amount of a subscription whose plan was overridden for it (`plan_overridden`), because the plan's
price is then not what it pays. The subscriber's e-mail, name, shipping address and payment
source are never copied.

A request the provider refuses, or a subscription it does not know, is `invalid`. A pair or a
token it does not admit is `unauthenticated`, and an application without the right to read is
`forbidden`. A throttled or failing provider is `unavailable` and retryable. Only the error's
`name` is reported, never its message.

## Which processes run on it

B-6.01, B-3.04 and B-5.06 read nothing but these three operations, so they run on this provider
unchanged once the product's entitlements name the payer's identifier as `customer` and the
plan's `product_id` as `product` (`blueprints/software-operations/connectors/entitlements.manifest.json`).
`tests/composition/test_software_operations_payments.py` runs all three against the fake.

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `PAYMENTS_TOKEN` | actions: the **requesting identity's** REST application credentials, `<client id>:<secret>`, of an application whose only feature is reading subscriptions | the file `TAKTUS_CREDENTIAL_PAYMENTS_TOKEN_FILE` names, read at the moment of each call, never stored |

The access token it exchanges for is kept for the one call and nowhere else. The contract has
no connector without the requesting identity's credential (C-03). `CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9144/mcp --scenario connectors/taktus_connectors/paypal/scenario.json
```

[`scenario.json`](scenario.json) lists the active subscriptions of the fake, reads one it does
not know as the call the provider refuses, and reads one payer's subscriptions under that payer's
scope. It names no write, and C-05 passes as not applicable. `--fault NAME` breaks exactly one
check; `tests/conformance/test_connector_v1_business.py` runs every fault.
