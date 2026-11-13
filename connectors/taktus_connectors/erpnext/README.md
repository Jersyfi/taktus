# The books connector — ERPNext's REST API

`accounting.invoices` over the REST API of ERPNext, an open-source accounting system on the
Frappe framework: an outgoing invoice the payment provider issued is exported into the books
as a draft sales invoice, which a person of the business checks and submits there (ADR-0314).
**Taktus keeps no books** (`docs/vision/non-goals.md`): it proposes into the accounting system
and never posts, submits or cancels. This directory, this file and the configuration that points
at it are the only places in the repository that name the product. Everywhere else it is
`accounting.invoices`.

It is proof and example, not a requirement: the control plane runs with it removed, and B-6.06
falls back to a person who exports the month's list by hand. A connector for another accounting
system's API serves the same capability and replaces this one by configuration (UC-8.9).

```
uv run python -m taktus_connectors.erpnext --port 9158 --target https://books.example \
    --customer "Online customers" --income-account "Sales - EX" --tax-account "VAT - EX"
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--customer` is the
collective customer the drafts name, as a shop's sales to many private customers are booked;
`--income-account` the account a draft's line books to, `--tax-account` the account its tax
books to, and `--company` the company where the site holds several. Each must exist in the
books. Point `--target` at the fake under `tests/fakes/books_service.py` to run without the
system.

The documentation followed: the Frappe framework's
[REST API](https://docs.frappe.io/framework/user/en/api/rest) (token authentication, `GET` of a
document and of a list with `fields`, `filters`, `or_filters` and `limit_page_length`, `POST` of
a document), ERPNext's [Sales Invoice](https://docs.erpnext.com/docs/user/manual/en/sales-invoice)
with its items and its taxes and charges of the type `Actual`, and the framework's
[document status](https://docs.frappe.io/framework/user/en/basics/doctypes#document-status)
(`docstatus` 0 a draft, 1 submitted, 2 cancelled).

## What it declares

| Operation | Effect | Idempotency | What it does, and how a repeat is recognised |
|---|---|---|---|
| `accounting.invoices.read` | read | — | `GET /api/resource/Sales Invoice/<name>`: the customer, the dates, the currency, the net and the grand total, `status` (`draft`, `submitted` or `cancelled`) and the `mark` it carries |
| `accounting.invoices.export` | write | marked | up to 500 invoices in the shape `payments.invoices.list` gives them (ADR-0214), each a draft sales invoice: the collective customer, the date it was issued as the posting date, its due date, its currency, one line of the net amount — the total less the tax — to the income account, and the tax as one charge of the type `Actual` to the tax account. Amounts arrive in minor units and are turned into the major unit by the currency's exponent in ISO 4217. The draft's `remarks` carry the mark `taktus:<number>:<40 hexadecimal digits of the SHA-256 of the key>`. Before creating, every invoice of the books whose mark names one of the batch's numbers is read: one under this key is the original, `replayed`; one under another key was exported by an earlier run, `before`, and is not exported again |

The output names each invoice's number, the draft's `name`, its `status` and whether it was
`created`, `replayed` or exported `before`, and counts each. **What is sent is checked first:**
a number, a currency, a total and a tax in whole minor units with the tax no larger than the
total, and the moment of issue; an empty batch, or one malformed invoice, refuses the batch as
`invalid` before any request.

| Answer | Cause |
|---|---|
| 400, 417: a document the site refuses | `invalid` |
| 401: the key is not admitted | `unauthenticated` |
| 403: the key's user may not do this | `forbidden` |
| 404: no such invoice | `not_found` |
| 409: a conflicting document | `conflict` |
| 429, 5xx, a refused or timed-out connection | `unavailable`, retryable; on a creation with effect `unknown`: a repeat with the key finds it |
| any other status, a body that is not the API's | `unexpected` |

Consumption is counted in `quota` units named `requests`: one lookup per hundred invoices and
one creation per invoice not found.

## Credentials

One, `BOOKS_TOKEN`: the API key and secret of a user of the books, as `<key>:<secret>`, sent as
`Authorization: token <key>:<secret>`. The user needs the role Accounts User with the right to
read and create sales invoices, and no right to submit them (`CREDENTIALS.md`). The value is
referenced by name in the context of every call and read at the moment of the call from the
file `TAKTUS_CREDENTIAL_BOOKS_TOKEN_FILE` names. The connector has no key of its own.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9158/mcp --scenario connectors/taktus_connectors/erpnext/scenario.json
```

[`scenario.json`](scenario.json) reads the submitted invoice the fake holds, exports one invoice
twice under one key and once under another, and asks for a name the API cannot hold. Against a
real site it creates drafts in the books it is pointed at: point it at a test site.
