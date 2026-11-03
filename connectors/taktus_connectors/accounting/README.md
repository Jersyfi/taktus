# The accounting connector — a generic accounting interface

The connector contract v1 ([`contracts/connector/v1`](../../../contracts/connector/v1/README.md))
over an organisation's own accounting system, through an interface that is generic, not a
product's. Everywhere it is three capabilities: `accounting.orders`, `accounting.bookings` and
`payment.release` (ADR-0169).

**Taktus keeps no books** (`docs/vision/non-goals.md`). It reads what the accounting system holds,
proposes a booking into it, which a person of the organisation posts there, and hands a payment
a person released to the system's payment run. Records are made unalterable in the accounting
system, not in Taktus.

It is proof and example, not a requirement: the control plane runs with it removed, and a
process that calls it falls back to a person. A connector for one accounting system's own API
serves the same capabilities and replaces this one by configuration (UC-8.9).

```
uv run python -m taktus_connectors.accounting --target https://accounting.example/taktus/v1 --port 9114
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. Point `--target` at
the fake under `tests/fakes/accounting_service.py` to run without a network. Added to an
instance by one entry of `TAKTUS_CONNECTORS` per capability, all at the same address:
`accounting.orders=http://accounting-connector:9114/mcp`, and `accounting.bookings` and
`payment.release` beside it.

## The interface

Four resources under `--target`, over HTTP and JSON. Every request carries the requesting
identity's credential as `Authorization: Bearer <value>`. Amounts are decimal text, at most two
decimals; dates `YYYY-MM-DD`; currencies ISO 4217.

| Request | Answer |
|---|---|
| `GET /orders/<reference>` | 200 and the order: `currency`, `supplier` (`vat_id`, `account`: the account the system pays the supplier to), `lines` (`id`, `item`, `price`, `received`, `invoiced`), `net_total`, `net_invoiced`, `account` and `cost_centre` it is booked to. 404 for a reference the system does not hold |
| `GET /bookings?mark=<mark>` | 200 and `{"records": [...]}`: every booking proposal carrying the mark |
| `POST /bookings` | 201 and the proposal created with its `id` and `status`. The body: `mark`, `document`, `digest`, `order`, `supplier`, `currency`, `issue_date`, `due_date`, `account`, `cost_centre`, `net`, `tax`, `gross`, `taxes`. 409 when the document is booked under another mark; 422 for a body the system refuses |
| `GET /payments?mark=<mark>` | 200 and `{"records": [...]}` |
| `POST /payments` | 201 and the payment scheduled with its `id` and `status`. The body: `mark`, `document`, `supplier`, `currency`, `amount`, `due_date`, `booking`. The system pays the account it holds for the supplier; the body names none |

An order is what was ordered or contracted: a purchase order, or a standing contract such as a
subscription, whose `received` is what the period delivered.

## What it declares

| Operation | Effect | Idempotency | Input |
|---|---|---|---|
| `accounting.orders.read` | read | — | `reference` |
| `accounting.bookings.propose` | write | marked | as the body of `POST /bookings`, without `mark` |
| `payment.release.submit` | write | marked | as the body of `POST /payments`, without `mark` |

**The mark.** A write's record carries `mark`: `taktus-` and the first 40 hexadecimal digits of
the SHA-256 of the idempotency key, which never leaves Taktus. Before creating, the connector
asks for a record with the mark; one found is the original, and nothing is created again
([`operations.py`](operations.py)).

**What is sent is checked first.** A malformed amount, date or currency is refused as `invalid`
before the system is asked. A payment of nothing or less is refused too.

Consumption is counted in `quota` units named `requests`: a read is one, a write two.

**The payment release is a legal anchor.** The operation's capability is `payment.release`,
which the shipped legal anchor names (`docs/architecture/governance.md` §2): a run halts before
it at every autonomy level, and a person decides. The connector does not check that a person
did; the run does.

## Credentials

One, referenced by name, `ACCOUNTING_TOKEN`: the requesting identity's key to the interface,
allowed to read orders and to create booking proposals and payments, nothing else
(`CREDENTIALS.md`).

## Errors

As [`operations.py`](operations.py) maps them. A creation the system did not answer is
`unavailable` with effect `unknown`: the record may exist, and a repeat with the same key finds
it.
