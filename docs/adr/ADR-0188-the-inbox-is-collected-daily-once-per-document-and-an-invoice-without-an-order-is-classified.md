# ADR-0188 — The inbox is collected daily, once per document, and an invoice without an order is classified

**Status:** accepted · extends ADR-0035 (a schedule trigger's `each`) and ADR-0169 (the
invoice-to-payment blueprint) · serves UC-04 §4, UC-03 B-6.06 and B-10.03 · issue #402

## Context

B-10.03 checks one invoice of the inbox and is started by hand for one document (ADR-0169).
UC-04 §4 names two more processes. **Collecting**: the invoices of the inbox, daily, each handed
to B-10.03. **Classifying**: an invoice that names no order, matched to one of its supplier's
orders — by a model first, later by a classifier trained on the decisions, later by a rule,
each proposal checked by the rule against the order it names.

A schedule trigger with `each` starts one run per item a read lists (ADR-0035). Two things were
missing for an inbox. Its run's identifier carries the slot, so a document still in the inbox
tomorrow would start a second run tomorrow. And the read takes no input, so the trigger could
not ask for only the documents that name an order.

## Decision

### 1. `each.once`: one run per item, whatever slot lists it

A schedule trigger's `each` may say `once: true`. The run's identifier is then derived from the
tenant, the trigger and the item, without the slot. A later slot that lists the same item names
the run it has, and the engine refuses to create it again, as it refuses a slot fired twice. A
document is processed on the first day it is listed and never again. A new document starts its
run the day it appears. Without `once` nothing changes.

### 2. `each.arguments`: the read's input, fixed

`each` may give `arguments`, the input of its read, fixed in the bundle. The read stays a read
(`effect: read`); nothing else is passed.

### 3. The inbox lists by whether a document names an order

`documents.invoices.list` takes `referenced`, `true` or `false`. With it, every listed document
is read once and kept when it names an order — or names none. A document that is no invoice
counts as naming one: B-10.03 then fails to read it and hands it to a person, where the
classification could not do anything with it.

### 4. The two processes split the inbox

B-10.03 carries a daily trigger over the documents that name an order, `once`. The new bundle
`B-10.03-unreferenced-invoice.yaml` carries one over the documents that name none, `once`. It
reads the invoice and its supplier's open orders (`accounting.orders.list`, a new read of the
accounting connector), asks a model under the purpose `triage` for one reference, takes the
reference out of the answer by a fixed pattern, reads that order, and then goes B-10.03's way:
the `invoice` rule holds the invoice against the order, `exact`; a person confirms the booking
proposal; the payment is released at the legal anchor.

The model only proposes. A wrong choice fails the `invoice` rule — the seller's tax identifier,
a line, a price or what is still open differs — and goes to a person with every difference
named. The person who confirms the booking proposal sees the order it was classified against.
Maturation measures the step as any other and proposes a classifier, and later a rule, once the
decisions allow it (ADR-0084).

## Alternatives

**Remembering which documents were processed, in a table.** The run's identifier already is that
memory, and the engine already refuses a run that exists. A table would be a second record of
the same fact.

**Moving a processed document out of the inbox.** The inbox is the organisation's folder. A
process that reorganises it acts on something the blueprint only reads.

**One process for both kinds of invoice, with a condition on the classification.** The
classification and the read of open orders would sit in every run of B-10.03, and a
referenced invoice's run would carry a model step it never takes.

## Consequences

- `Each` gains `arguments` and `once`; the trigger passes `arguments` to its read.
- The documents connector's list takes `referenced`; the accounting connector serves
  `accounting.orders.list` against `GET /orders?supplier=`.
- UC-04 §4: all three processes are bundles. `tests/composition/test_invoice_to_payment.py`
  and `tests/composition/test_triggers.py` prove them against fakes.

## Where this promise ends

`once` keys a run by the item the read gives — here the document's file name. A document
replaced under the same name is not processed again; a corrected invoice is a new document under
a new name, as suppliers send them, or a person starts its run by hand. A document whose run
failed is not retried by the next day's collection: the run's incident is with a person. A list
with `referenced` reads every listed document every day, one request each. The list holds the
oldest `limit` documents, and both triggers ask for the most, 1000: an inbox that holds more
collects a newer document only once the organisation archived older ones out of the folder. The model's choice is checked only as
far as the `invoice` rule checks: an invoice that matches two open orders of its supplier equally
well is booked under the one the model chose, and the person confirming the booking is the check
on that. The classification is proven against a stand-in model; no tenant's invoices were
classified by a real model.
