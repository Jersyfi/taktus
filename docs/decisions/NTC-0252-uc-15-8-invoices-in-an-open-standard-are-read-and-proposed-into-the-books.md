# NTC-0252 — UC-15.8: invoices in an open standard are read, and proposed into the organisation's own books

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-31
**Raised in:** branch `concept/package-c--invoice` (package C, concept mode, DEC-0222)
**How it follows:** the roadmap's `0.7.0` names "connectors for documents and accounting", and its completion condition is the second domain running "against real connectors". UC-15.2 requires electronic invoices received in open standards, every system the domain conducts named by capability, and no books kept by Taktus. UC-8.9 requires that changing a vendor breaks nothing. No use case stated what those connectors must do. UC-15.8 states it, each condition observable, and follows from those three sources and from the connector contract's own conditions.

## 1. What was decided

UC-15.8, component `catalog`, version `0.7.0`, the next free number of its area
(`docs/usecases/NUMBERING.md`). Its conditions: an EN 16931 invoice in UBL and in CII read into
one set of business terms, amounts as given; a declared document type or entity refused
unparsed; an order read; a booking and a released payment reaching the books once per key, the
key never leaving Taktus; a malformed amount refused before the books are asked; both
connectors passing the conformance suite; capabilities named by function.

Two conditions follow from what the owner already accepted rather than from the roadmap's line:

- the defused parse, because a document comes from outside the organisation and CLAUDE.md §6
  makes every outward access an adapter's, held to the contract;
- the refusal of a malformed amount before the books are asked, because UC-15.2 §3 lets an
  amount reach the journal only from a reproducible method or a person's confirmation.

Concept mode lets a new use case be written beside its implementation (DEC-0222). It was.

## 2. The evidence

- `docs/roadmap.md`, `0.7.0`; issue #402, *Component*: connectors.
- UC-15.2 §1 and §3; UC-8.9; `docs/vision/non-goals.md`; `contracts/connector/v1` §4 and §8.

## 3. What was considered

- **One use case for the whole domain.** Rejected: UC-04 is the blueprint's; the connectors
  serve any process that reads an invoice or proposes into books, as UC-15.2's other parts will.
- **A connector to one named accounting product.** Rejected for the requirement: the roadmap
  asks for connectors, and UC-8.9 makes the product replaceable. The use case requires the
  capabilities, not a product.

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here the roadmap's
`0.7.0`. The owner may veto it within seven days of the pull request.
