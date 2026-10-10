# Blueprint `finance` — the finance reference domain under legal anchors

Use case UC-15.2. The reference domain for a business run as orchestrated process chains with people as
owners and deciders, and for the legal anchors that keep acts with a person whatever the autonomy level.
It is the domain where "a business run by agents" most visibly does not mean "a business without people":
it means people exactly where law and responsibility require them.

**State: a description.** No process of it exists as a bundle, and it is not on the roadmap: the second
domain the roadmap schedules is systems operation (`it-operations`, `0.7.0`). Before it is used for any
tenant, its legal-anchor catalogue is reviewed for that tenant's jurisdiction by a tax adviser
(DEC-0029).

**Who it involves:** the owner of the finance processes, who is the domain's responsibility anchor
(UC-15.5); the tax adviser, outside the organisation; and the executive.

---

## 1. What the domain does

Taktus conducts the accounting system the organisation already has, through connectors, by capability —
for example "an accounting system that imports documents". It keeps no books of its own
(`docs/vision/non-goals.md`).

| Work | What Taktus does |
|---|---|
| Capturing documents | takes in receipts and invoices from mail, portals and scans |
| Matching | matches them against orders and incoming payments |
| Proposing how to account | attaches a proposal of the accounts to each document and hands it into the accounting system |
| Recurring bookings | runs them as the organisation's policy says |
| Preparing filings and closings | prepares tax pre-filings, closings and reports, and hands them to the tax adviser with a complete package for review |
| Electronic invoices | receives and sends them in open standards — for example XRechnung, ZUGFeRD or Peppol — so that both directions can be processed by machine |

**Prepared, not filed.** Taktus prepares; the filing, the signature and the release are a person's.

## 2. The legal anchors

Legally binding acts stay with a person **whatever the autonomy level of the rest of the process**: filing
a tax return, releasing a payment above a threshold the organisation configures, a signature, the annual
accounts. Each halts the run at a step boundary and raises a decision request to a person (ADR-0008,
UC-7.4); at level 4 as at level 1.

The anchors are configurable per country and jurisdiction, can never be reduced to nothing, and appear in
the organisation's generated conformity evidence (definition `UC-11.3`).

## 3. What must hold

- Every booking can be traced back to its document and to the basis of its decision, through the ledger
  and the provenance record (UC-6.1, ADR-0021).
- Records are made unalterable in the accounting system, as the rules for proper bookkeeping require —
  not in Taktus.
- An amount or an account reaches the accounting journal only from a reproducible method or a person's
  confirmation. A language model may propose how to account for a document; its proposal never becomes
  the booked value on its own (ADR-0014, `CLAUDE.md` §4). Recurring bookings run as rules.
- The tax adviser receives the review package in the format of the adviser's own system, not in a format
  of Taktus.
- The value balance shows the finance processes against the accounting hours they save (UC-9.3).
- Every system the domain conducts is named by capability, so that replacing the accounting system breaks
  no process (UC-8.9).

## 4. What it rests on

Domain blueprints (UC-15.1) and the responsibility anchor with its legal-anchor catalogue (UC-15.5);
anchors and decision requests (ADR-0008, UC-7.4); exactness (ADR-0014); the provenance record (ADR-0021);
partner interfaces and data contracts for the electronic invoices exchanged with partners (UC-15.3);
end-to-end chains such as order-to-cash and procure-to-pay, whose last links are here (UC-15.4); the value
balance (UC-9.3). Definition `UC-15.2`, new in version 2. Placing it here, as a deployment rather than a
capability of the core, follows the migration of epic E15; what it adds beyond the definition stands, by
DEC-0087.
