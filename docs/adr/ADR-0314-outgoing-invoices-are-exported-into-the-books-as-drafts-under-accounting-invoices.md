# ADR-0314 — Outgoing invoices are exported into the books as drafts, under `accounting.invoices`

**Status:** accepted · extends ADR-0169 (Taktus keeps no books) and ADR-0214 (invoices read from
the payment provider) · UC-03 §4.6 B-6.06, §8 "accounting export", #402, DEC-0225, DEC-0226

## Context

B-6.06 collects the month's outgoing invoices from the payment provider (ADR-0214). UC-03 asks
that they are also exported for the bookkeeping. The generic accounting interface of ADR-0169
proposes bookings of incoming invoices and holds no outgoing one. The accounting system of the
business is not named in this repository. The project uses no accounting system itself, so a
connector to one is proven against a stand-in built from its published API (DEC-0225, DEC-0226).

## Decision

### 1. A capability of its own, `accounting.invoices`

`accounting.invoices.export` takes a batch of invoices in the shape `payments.invoices.list`
gives them, with amounts in minor units. `accounting.invoices.read` reads one back. The export
is a write, `marked`. A process names the capability, never the system.

### 2. An exported invoice is a draft, never posted

Each invoice becomes one draft sales invoice: a collective customer, the date it was issued, its
due date, its currency, one line of the net amount to an income account, the tax as one charge to
a tax account. The customer and both accounts are the tenant's configuration of the connector.
Amounts become the currency's major unit by its exponent in ISO 4217. The connector never
submits, cancels or deletes a document. A person of the bookkeeping checks and posts each draft.
Taktus still keeps no books.

### 3. One mark per invoice, found across runs

A draft carries `taktus:<number>:<digest of the key>`. Before creating, the connector reads every
document whose mark names one of the batch's numbers. One under the same key is `replayed`. One
under another key was exported by an earlier run: it is reported as `before` and not exported
again. A month run twice books each invoice once. A batch that holds a malformed invoice is
refused whole before any request.

### 4. The first connector serves an open-source accounting system's REST API

Connector `erpnext` serves the capability over that system's REST API, with the API key and
secret of a user of its own (`BOOKS_TOKEN`). It passes the connector suite against a fake of the
API (`tests/fakes/books_service.py`). A connector for another system serves the same capability
and replaces it by configuration.

### 5. B-6.06 exports the issued invoices

B-6.06 gains the step `export` after `issued`, at version 2. It acts, so it starts at level 2:
a person confirms the export, and posting stays with a person at every level.

## Alternatives

- **A booking proposal under `accounting.bookings`.** Its body is an incoming invoice with a
  supplier and an order; an outgoing invoice has neither.
- **An export file a person imports.** It keeps the handwork the process exists to remove.
- **One draft per customer of the provider.** It would create master data in the books from a
  payment provider's identifiers. A collective customer is how a shop's sales to many private
  customers are booked.
- **Submitting the drafts.** A posted document cannot be changed, and a booking is the
  bookkeeping's act.

## Consequences

- Connector `erpnext`, its fake, scenario, image and chart entry; `BOOKS_TOKEN` in
  `CREDENTIALS.md`.
- B-6.06 version 2; `accounting.invoices` in the blueprint's capabilities.
- Proven in `tests/adapters/connectors/test_books_connector.py`,
  `tests/composition/test_software_operations_books.py` and the business connector suite.

## Where this promise ends

- **Nothing was run against a real system.** The fake follows the published reference; the
  business's own system is proven on its instance (DEC-0226).
- **The mark is in `remarks`.** A person who edits the remarks of a draft removes the mark, and a
  later run exports that invoice again.
- **Only the issued invoices of one month, at most 500.** A larger month is refused and goes to
  a person. A refund, a credit note and a payment are not exported.
- **Tax is one amount.** The provider's tax arrives as one figure; rates and categories are not
  split, and a tax determination stays with the bookkeeping.
- **One collective customer.** A business customer's own account in the books is the
  bookkeeping's to set.
- **Incoming invoices stay with the invoice-to-payment blueprint** (B-10.03).
