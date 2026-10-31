# UC-04 — From an incoming invoice to its payment, released by a person

Blueprint `invoice-to-payment`, [`blueprints/invoice-to-payment/`](../../blueprints/invoice-to-payment/README.md).
The second domain of the roadmap (`0.7.0`, DEC-0195 W1, #402), and the first part of the finance
reference domain (UC-15.2) that runs as processes. Reference case: the incoming invoices of a
small software business — hosting, services, subscriptions — the second tenant (DEC-0199).

It shows what sets Taktus apart: an amount held `exact` by a rule, a legal anchor that holds
at every level, and autonomy that differs per action inside one process.

**Not to be used for a tenant before its legal-anchor catalogue is reviewed** for its
jurisdiction by a tax adviser, and the review recorded with its date and jurisdiction
(DEC-0029). Until then the catalogue is marked as not legally reviewed wherever it is shown.

---

## 1. The task in one sentence

An incoming electronic invoice is read, matched against what was ordered or contracted, its
amounts computed again and held `exact`, proposed for booking into the organisation's own
accounting system, and paid only once a person released the payment.

## 2. Origin and boundary

UC-03 names the work in two rows. **B-10.03**: an invoice matched to a subscription or project
and checked against what was expected, its amount `exact`, the payment with a person.
**B-6.06**: invoices collected, matched and exported for the bookkeeping, Taktus keeping no
books. This case says what the domain needs beyond those two rows: which documents, which
systems, which checks, what stays with a person, and when the case holds (NTC-0251).

**Not here.** Tax filings and payroll (#402). Outgoing invoices: B-6.06's other half. The
preparation of closings and the tax adviser's package: UC-15.2. Taktus is not the accounting
system (`docs/vision/non-goals.md`).

## 3. Autonomy

Autonomy belongs to the action as well as to the process (UC-7.1). In this domain that is the
point, not a refinement.

| What | Level | Why |
|---|---|---|
| reading the document, reading the order, computing and matching | 3 | they change nothing outside, and the amounts are a rule's |
| proposing a booking (`accounting.bookings`) | 2, rising on evidence | a proposal reaches the books; a person confirms each until the counted corrections show it need not (UC-7.5) |
| releasing a payment (`payment.release`) | anchored at every level | a payment is a legally binding act: a legal anchor (ADR-0008) |

A tenant caps any action lower for all its processes with a risk class that carries a level
(ADR-0170), without changing the blueprint.

## 4. Processes

| ID | Process | Trigger | Target level | Stays with a person |
|---|---|---|---|---|
| B-10.03 | **Incoming invoice**: one invoice read in EN 16931, its order read, every amount recomputed and matched, a booking proposed, the payment submitted after a person's release | one document in the inbox | 3, the booking 2, the payment anchored | releasing the payment; every difference |
| B-6.06 (incoming half) | **Collecting and matching**: the invoices of the inbox listed, each handed to B-10.03, the unmatched ones reported | daily | 3 | an invoice nobody matched |
| B-10.03 (unreferenced) | **Classifying an invoice that names no order**: which order or contract it belongs to, proposed by a model, later by a classifier trained on the decisions, later by a rule, each proposal checked by the rule against the order it names | an invoice without a reference | 2, rising | the classification until it matured |

Only the first row is built (§9).

## 5. What stays with a person

| What stays | How Taktus keeps it |
|---|---|
| **Releasing a payment** | the shipped legal anchor names `payment.release`; the run halts at the step's boundary at every level with a decision request, and the payment is submitted only after a person decided |
| **Every difference** | the `invoice` rule fails on any difference between an invoice's amounts and its parts, or between the invoice and its order, and names each; nothing is booked or paid, and the run goes to a person |
| **Posting** | Taktus proposes; a person posts in the accounting system, where the record becomes unalterable |
| **The account paid** | the accounting system pays the account it holds for the supplier; an invoice naming another is a difference |

## 6. What must hold

- **Every amount is `exact`.** It is produced by a rule in decimal arithmetic and held by machine
  checks: computed again by EN 16931's calculation rules, matched against the order, reconciled
  against the total the document states, and recomputed (ADR-0169). No model produces an amount
  (CLAUDE.md §4).
- **The payment release is never automatic**, at any autonomy level.
- **Every booking traces back** to its document, by the document's digest, and to the order it
  was matched against, through the ledger and the provenance record (UC-6.1, ADR-0021).
- **Every system is named by capability.** Replacing the inbox or the accounting system changes
  a connector, not a process (UC-8.9, UC-15.8).
- **No figure names a person.** Corrections are counted per action class, never per person
  (principle 14, ADR-0110).

## 7. The capabilities it needs

| Capability | Used by | Built |
|---|---|---|
| `documents.invoices` — an inbox read as EN 16931 | B-10.03 | the documents connector over WebDAV, UBL 2.1 and CII D16B (UC-15.8) |
| `accounting.orders`, `accounting.bookings`, `payment.release` | B-10.03 | the accounting connector over a generic interface (UC-15.8) |
| a classifier of unreferenced invoices | B-10.03 (unreferenced) | no |

## 8. When this case holds

The roadmap's condition for `0.7.0`: the domain runs end to end against real connectors, its
amount `exact` and its payment released by a person.

- B-10.03 reads an invoice, proposes its booking after a person's confirmation, and submits its
  payment only after a person's release, with the amount the rule computed — against fakes in
  the tests, and against the tenant's own inbox and accounting system on its instance.
- An invoice with any difference reaches a person with every difference named, and nothing is
  booked or paid.
- The legal-anchor catalogue was reviewed for the tenant's jurisdiction before the first run
  in earnest (DEC-0029).

## 9. What is proven so far

B-10.03 is built as a bundle and proven end to end against fakes of an inbox and an accounting
system (`tests/composition/test_invoice_to_payment.py`): an invoice that holds waits for the
confirmation of its booking proposal while the rest of the level-3 run went on, then halts at
the legal anchor, and its payment is submitted after a person's release with the rule's amount;
an invoice whose account to be paid differs from the books goes to a person and nothing is
booked or paid; a tenant's risk class at level 1 holds the booking at level 1 without a change
to the bundle. The rule's calculation and matching are proven in
`tests/components/run/test_invoice_rule.py`.

Not built: collecting the inbox daily and handing each document to B-10.03; classifying an
invoice that names no order; a run against a real inbox and accounting system, which needs the
tenant's credentials; the review of the catalogue (DEC-0029).

## 10. Dependencies

UC-03 B-10.03 and B-6.06 · UC-15.2 and `blueprints/finance/` · UC-15.8 and ADR-0169 · anchors
and decision requests (ADR-0008, ADR-0042, UC-7.4) · levels per action and per risk class
(UC-7.1, ADR-0039, ADR-0170) · corrections counted per action class (UC-7.5, ADR-0110) ·
exactness and its checks (ADR-0014, ADR-0152, UC-4.13) · the provenance record (ADR-0021) ·
the legal-anchor review (DEC-0029).
