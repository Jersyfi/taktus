# Blueprint `invoice-to-payment`

From an incoming invoice to its payment, released by a person. Its requirement is use case
UC-04, [`docs/usecases/AF-04-invoice-to-payment.md`](../../docs/usecases/AF-04-invoice-to-payment.md);
it is the first part of the finance reference domain ([`finance`](../finance/README.md),
UC-15.2) that runs as processes, and the roadmap's second domain (`0.7.0`, #402).

**Not to be used for a tenant before its legal-anchor catalogue is reviewed** for the tenant's
jurisdiction by a tax adviser, and the review recorded with its date and jurisdiction
(DEC-0029). The catalogue is the project's own and is not legally reviewed for any
jurisdiction.

The blueprint is product: its processes name capabilities only. The tenant's instantiation —
the inbox, the accounting system, its anchors, its risk classes and their levels — is the
tenant's configuration on its own instance and never enters this repository (ADR-0092).

## State

One bundle: [`processes/B-10.03-incoming-invoice.yaml`](processes/B-10.03-incoming-invoice.yaml).

| Step | Method | Exactness | What it does |
|---|---|---|---|
| `read-invoice` | rule, `documents.invoices.read` | sourced | the document read as the business terms of EN 16931, from UBL 2.1 or CII D16B |
| `read-order` | rule, `accounting.orders.read` | sourced | what was ordered or contracted under the invoice's reference, as the accounting system holds it |
| `check` | rule, `invoice` | exact | every amount computed again in decimal and the invoice matched against its order; any difference goes to a person; reconciled against the document's total with tax and recomputed |
| `propose-booking` | rule, `accounting.bookings.propose` | sourced | a booking proposal into the accounting system, once per key; at level 2: a person confirms it first |
| `release-payment` | rule, `payment.release.submit` | sourced | the payment handed to the payment run with the rule's amount; under the legal anchor at every level |

The process runs at level 3; its action `accounting.bookings` at level 2, counted per action
class until its corrections earn a raise (ADR-0110). A tenant caps an action lower for all its
processes with a risk class that carries a level (`taktusctl anchors set`, ADR-0170).

Not built: the daily collection of the inbox that hands each document to B-10.03, and the
classification of an invoice that names no order (UC-04 §4).

## Running it

It needs two connectors, each an image of its own (ADR-0158): the documents connector
(`taktus-connector-einvoice`) for `documents.invoices`, pointed at the inbox folder's WebDAV
address, and the accounting connector (`taktus-connector-accounting`) for `accounting.orders`,
`accounting.bookings` and `payment.release`, pointed at the accounting interface
(`connectors/taktus_connectors/accounting/README.md`). Their credentials are `DOCUMENTS_TOKEN`
and `ACCOUNTING_TOKEN` (`CREDENTIALS.md`).

    uv run taktusctl run --process blueprints/invoice-to-payment/processes/B-10.03-incoming-invoice.yaml \
        --input document=<the document's file name in the inbox>

The run waits twice for a person: once to confirm the booking proposal, once at the payment's
decision request.

## By hand, without Taktus

What a person does in place of B-10.03 (UC-6.3), from the same systems:

1. Open the invoice from the inbox folder and find the order or contract it names.
2. Check the invoice against it: the seller's tax identifier, the account to be paid against the
   one the accounting system holds, each line's price and quantity received, and the total
   against what is still open on the order.
3. Add the lines' net amounts, compute each tax category's tax at its rate rounded to the cent,
   and check the totals the invoice states. Any difference: ask the supplier, do not pay.
4. Enter the booking in the accounting system, to the order's account and cost centre.
5. Release the payment in the accounting system's payment run, to the account it holds for the
   supplier.
