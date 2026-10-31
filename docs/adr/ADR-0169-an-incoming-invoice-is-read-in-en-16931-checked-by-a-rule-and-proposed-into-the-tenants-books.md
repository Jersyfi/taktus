# ADR-0169 — An incoming invoice is read in EN 16931, checked by a rule, and proposed into the tenant's books

**Status:** accepted · extends ADR-0150 (connectors for a business's systems), ADR-0151 (a
built-in computation in decimal) and ADR-0042 (anchors at the step boundary) · issue #402,
roadmap `0.7.0` "connectors for documents and accounting"; UC-04, UC-15.8, UC-03 B-6.06 and
B-10.03

## Context

The second domain of the roadmap is `invoice-to-payment` (DEC-0195 W1, #402). An incoming invoice
is read, matched against what was ordered, its amount checked as `exact`, booked as a proposal
and released for payment by a person. Three things were missing.

**No connector reached a document or an accounting system.** UC-03 §8 lists the accounting
export as not built. A connector for one accounting product would tie the blueprint to that
product. The brief and the issue ask for generic product support: an open standard for the
document and a generic interface for the books.

**No computation could check an invoice.** A `rule` step compares values (`check`) and a
`statistics` step computes a deviation over a series (ADR-0151). Neither adds a line's quantity
times its price, rounds a tax to the cent and compares the result with the total the document
states. An amount held `exact` must come from such a computation, never from a model
(CLAUDE.md §4).

**The payment release had to stop at a person whatever the level.** The shipped legal anchor
names the action `payment.release` (ADR-0042). A connector operation under another name would
pass it by.

Taktus keeps no books (`docs/vision/non-goals.md`). Whatever is booked is the accounting
system's record, posted there by the organisation.

## Decision

### 1. A documents connector over two open standards

The connector `einvoice` serves `documents.invoices`. It reads an inbox: one folder served over
WebDAV (RFC 4918), which file shares, document stores and portals offer. How a document reaches
the folder is the organisation's. It reads a document as an electronic invoice of EN 16931 in
either of the standard's syntaxes, UBL 2.1 or CII D16B. National profiles are documents in one of
the two. The reading names the business terms a check and a match need, each amount the decimal
text the document gave. It computes nothing.

Parsing is defused. A document that declares a document type or an entity is refused before it
is parsed: neither syntax needs one, and one is how an entity expansion or an external reference
reaches a parser. The parser is the standard library's. No parsing library is added.

The reading is an adapter, not a rule of the core, for two reasons. The document comes from
outside, through a folder the organisation keeps, and is reached with its credential. And a
format is knowledge that changes with its standard. In an adapter it is replaced by capability:
a connector that reads scans, or another standard, serves `documents.invoices` instead (UC-8.9).

### 2. An accounting connector over a generic interface

The connector `accounting` serves three capabilities of the organisation's own accounting
system, over an interface of four resources in HTTP and JSON that its README states:

- `accounting.orders.read`: what was ordered or contracted under a reference — a purchase order
  or a standing contract such as a subscription — with what was received and invoiced, and the
  account it is booked to;
- `accounting.bookings.propose`: a booking proposal for one document, `marked`;
- `payment.release.submit`: a payment a person released, handed to the system's payment run,
  `marked`. The system pays the account it holds for the supplier, never one the call names.

The interface is Taktus's statement of what it needs, not a product's. An accounting system
serves it directly or through a bridge. A connector to one product's API serves the same
capabilities and replaces this one by configuration. A write's record carries a mark derived
from the key, and a repeat finds it (contract §4). A malformed amount is refused before the
system is asked.

### 3. The amounts are a rule's: `invoice`

A rule `invoice` takes the invoice's reading and the order's. It computes the amounts again by
the calculation rules of EN 16931 — each line, the lines' total (BR-CO-10), the total without
tax (BR-CO-13), each tax category's amount rounded half up to the cent, the tax total
(BR-CO-14), the total with tax (BR-CO-15), the amount due (BR-CO-16) — in decimal arithmetic.
It matches the invoice against the order: currency, the seller's tax identifier, the account to
be paid, each line's price and open quantity, and the open total. A credit note is not paid.

Any difference fails the step and names each difference. The run goes to a person through the
step's fallback. Otherwise the result is the amounts to book and to pay, as decimal text. The
same readings always give the same result. The step is `exact`. Two checks of the catalogue
hold it beyond the rule (ADR-0152): a `reconciliation` — the net and the tax it computed sum to
the total with tax the document states, read again through `documents.invoices` at the moment
of the check — and a `recomputation` (provisional, DEC-0173).

A check that reads through a connector reaches a system that needs the requesting identity's
credential, as the read of the step itself does. `checking.reads` therefore names
`credentials`, as every connector call does. Before, it could not, and a reconciliation against
a system that asks for a credential could never pass.

### 4. The payment release is the shipped legal anchor's

The release's operation is `payment.release.submit`, of the capability `payment.release`. The
shipped legal anchor names `payment.release` (ADR-0042). A run therefore halts before the step
at every autonomy level, with a decision request to the anchor's role. Only after a person
decided does the step run. A tenant may narrow the anchor, for instance by a threshold in a risk
class. It can never empty the legal class.

### 5. The booking runs at its own level

The blueprint's process runs at level 3: reading, matching and computing need nobody. Its
action `accounting.bookings` runs at level 2: a person confirms each proposal before it is
handed over. Each confirmation, correction or rejection is counted for that action class
(ADR-0110). The counts are the evidence a raise of the action rests on. A tenant may cap the
action lower for all its processes by a risk class with a level (ADR-0170).

### 6. The catalogue is not legally reviewed

The legal-anchor catalogue is the project's own, not reviewed for any jurisdiction. Before a
tenant uses this blueprint, the catalogue is reviewed for that tenant's jurisdiction by a tax
adviser, and the review is recorded with its date and jurisdiction (DEC-0029, Option A). The
blueprint and its use cases say so.

## Alternatives

- **A connector for one accounting product.** It would tie the product's blueprint to one
  vendor, and the brief asks for generic support. A product connector can still serve the same
  capabilities.
- **Parse the document in the core, as a rule.** The core would carry a standard's syntax, and
  removing the format would break a process instead of changing it. The reading has an outside
  source and a credential, which makes it an adapter's.
- **A parsing library with defused defaults.** A dependency for what one refusal before
  parsing achieves with the standard library.
- **Read invoices from mail attachments.** The mail connector reads no attachment's content, on
  purpose (ADR-0111). A folder serves mail, portals and scans alike.
- **Let a model read the invoice and give the amount.** An `exact` amount never comes from a
  model (CLAUDE.md §4). A model may later propose which order an invoice that names none belongs
  to; the rule then checks the proposal against the order.
- **A `statistics` step for the check.** The check is fixed arithmetic over one document, not a
  statistic of a series.
- **Name the release operation by the accounting system's own word.** It would pass by the
  shipped legal anchor.

## Consequences

- `connectors/taktus_connectors/einvoice/` and `connectors/taktus_connectors/accounting/`, each an
  image of its own (ADR-0158), with fakes under `tests/fakes/` and the conformance suite.
- `run`: the rule `InvoiceRule`, `domain/service/invoices.py`; `CheckRead.credentials`.
- `CREDENTIALS.md`: `DOCUMENTS_TOKEN`, `ACCOUNTING_TOKEN`.
- `blueprints/invoice-to-payment/`: the process B-10.03 as a bundle; UC-04 and UC-15.8.

## Where this promise ends

The documents connector reads structured invoices in UBL 2.1 or CII D16B. A scan, a PDF without
its XML, or another format is not read: such a document fails the read, and the run goes to a
person. Document-level allowances and charges are read as totals; their own tax category is not
split out, so the tax bases are checked against the total without tax as a whole. A line's own
allowances and charges are not read: a line whose net amount differs from quantity times price
is a difference for a person.

The rule matches against what the accounting system says was ordered and received. It does not
know whether the delivery happened, only what the system holds. An invoice that names no order
or contract fails its read of the order and goes to a person. Its classification by a model, and
the maturation of that classification to a rule, are not built.

The accounting connector proposes. Whether the system posts the booking, and when the payment run
pays, is the system's and its people's. The mark lets a repeat find a record the system kept; a
system that drops a record's mark defeats it. Whether a released payment was paid is not read
back.

The legal anchor halts the release. It does not decide the amount: the amount is the rule's, and
the person sees it in the request. A tenant that narrows the anchor by a threshold lets a payment
below it run without a person; that is the tenant's configuration, after the review DEC-0029
requires.
