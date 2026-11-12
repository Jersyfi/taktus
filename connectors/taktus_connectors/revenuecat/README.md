# The in-app subscription connector — the RevenueCat REST API v2

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over the customers and subscriptions of the RevenueCat REST API v2: the subscriptions an app
sells through the app stores and the web, held in one project. This directory, this file and the
configuration that points at it are the only places that name the product. Everywhere else it
is the capabilities `payments.subscriptions` and `payments.customers` (ADR-0150, ADR-0206).

It answers the same operations as the first payment provider connector
([`stripe/`](../stripe/README.md)), under the same names and in the same shape, so that B-6.01
and B-3.04 of the blueprint `software-operations` run on it unchanged. It is proof and example,
not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.revenuecat --port 9145 --project proj1ab2c3d4
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address, `https://api.revenuecat.com` by default; point it at the fake under
`tests/fakes/app_subscriptions_service.py` to run without a network. `--project` is the
project's identifier. Added to an instance by one entry of `TAKTUS_CONNECTORS` per capability:
`payments.subscriptions=http://payments-connector:9145/mcp`, and `payments.customers` at the
same address.

## The documentation it follows

- the API v2 overview, <https://www.revenuecat.com/docs/api-v2>: the bearer key, lists
  `{object: "list", items, next_page, url}` paged forward by `starting_after` and `limit`, the
  error body `{type, param, message, retryable, doc_url}`;
- the customers, <https://www.revenuecat.com/docs/api-v2/customer>: `GET
  /projects/{project_id}/customers`, `limit` clamped to 1 to 100;
- a customer's resources, <https://www.revenuecat.com/docs/api-v2/customer/resources>: `GET
  /projects/{project_id}/customers/{customer_id}/subscriptions`;
- the subscriptions, <https://www.revenuecat.com/docs/api-v2/subscription>: `GET
  /projects/{project_id}/subscriptions/{subscription_id}` and the fields of a subscription. The
  only list of that page searches by a store's transaction identifier; **the API has no list of
  every subscription of a project**.

## What it declares

Three operations, all of effect `read`, every request one unit of consumption.

`payments.subscriptions.list` takes `status` and `limit` as the first connector does. Because
the API lists no project's subscriptions, it reads the customers page by page, at most 100
pages of 100, and each customer's subscriptions, keeping those in `status`. A reading of every
active subscription therefore costs one request per customer and a request per hundred
customers. The provider allows 480 requests a minute in this domain: a project of thousands of
customers is read in minutes, and of more than 10000 customers it is not read whole —
`complete` is false then, and B-6.01 stops on it rather than match a partial list.

The provider's statuses are mapped into the shared vocabulary:

| Shared | The provider's |
|---|---|
| `trialing`, `active`, `paused`, `incomplete` | the same |
| `past_due` | `in_grace_period`, `in_billing_retry`: a renewal failed and is retried |
| `canceled` | `expired` |
| null | `unknown` |

`unpaid` and `incomplete_expired` have no counterpart and are refused as `invalid`.

`payments.subscriptions.read` takes `id`, a subscription's identifier.

`payments.customers.subscriptions` takes `customer`, the app's user identifier, which the
product chooses itself and which may carry reserved characters (it is sent encoded). Its
capability is declared `scoped` (ADR-0130): a call that names another customer than the case's
subject is refused as `out_of_scope` before the provider is asked. Conformance check C-11
proves it.

Each subscription is reduced to the shared fields:

| Field | From |
|---|---|
| `id` | `id` |
| `customer` | `customer_id`, and nothing else of the customer |
| `status` | as mapped above |
| `current_period_end` | `current_period_ends_at`, given in milliseconds, in whole seconds since the epoch; null when the provider gives none (paused indefinitely) |
| `cancel_at_period_end` | `auto_renewal_status` is `will_not_renew` |
| `items` | one item: `product` the `product_id` (null for a promotional subscription), `quantity` 1, and no `price`, `unit_amount`, `currency` or `interval` |
| `metadata` | `store` and `environment`, as text |

A store subscription is one customer's, and the API names no number of seats, so `quantity` is
1 by what the subscription is, not by a reading. A subscription carries no price: the API states
only the revenue it brought in, converted to US dollars, which is no price and is not copied.
B-5.06, which compares the seats a business pays for, therefore has nothing to compare on this
provider; a business sold seats sells them through a payment provider of its own.

The country, the management address, the revenue and every customer attribute are never copied.
A request the provider refuses, or a subscription or customer it does not know, is `invalid`. A
key it does not admit is `unauthenticated`, and one without the permission
`customer_information:subscriptions:read` (and, for the list, `customer_information:customers:read`)
is `forbidden`. A throttled or failing provider is `unavailable` and retryable. Only the error's
`type` is reported, never its message.

Each subscription carries too `started_at` (`starts_at`) and, for an expired one, `ended_at`
(`ends_at`), both in seconds; its item's `interval_count` is null (ADR-0214).

## Failed renewals (ADR-0214)

`payments.failures.list` (capability `payments.failures`) and the scoped
`payments.customers.failures` answer the subscriptions in `in_billing_retry` or
`in_grace_period`, read customer by customer, in the first connector's shape. The store bills,
reminds the customer and offers the change of the payment method itself; the subscription's
`management_url` is `update_url`, its status the `reason`. The API states no amount owed, no
attempts and no moment of the failure, so they are null and B-6.04 stages no reminder here.
No contact is declared: the store holds the customer's address. Invoices exist in the API only
per customer (`GET /projects/{project_id}/customers/{customer_id}/invoices`, documented at
<https://www.revenuecat.com/docs/api-v2/invoice>), and the API lists no events; neither is
declared: a month's invoices would cost one request per customer, and the page states not which
store's purchases they cover. The documentation: the subscription object,
<https://www.revenuecat.com/docs/api-v2/subscription> (`status`, `management_url`,
`starts_at`, `ends_at`).

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `PAYMENTS_TOKEN` | actions: the **requesting identity's** secret API key of version 2, with read permissions on customers and subscriptions and nothing else | the file `TAKTUS_CREDENTIAL_PAYMENTS_TOKEN_FILE` names, read at the moment of each call, never stored |

The contract has no connector without the requesting identity's credential (C-03).
`CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9145/mcp --scenario connectors/taktus_connectors/revenuecat/scenario.json
```

[`scenario.json`](scenario.json) lists the active subscriptions of the fake, reads one it does
not know as the call the provider refuses, and reads one customer's subscriptions under that
customer's scope. It names no write, and C-05 passes as not applicable. `--fault NAME` breaks
exactly one check; `tests/conformance/test_connector_v1_business.py` runs every fault.
