# DEC-0176 — The wiki for the guides is a self-hosted open-source wiki

**Category:** NON-BLOCKING
**Mode entry:** M2.5
**Raised in:** the session of 2026-10-11, on NEED-0021 (issue [#199](https://github.com/Jersyfi/taktus/issues/199)); recorded in the pull request that records the owner's answers of that evening
**Issue:** [#199](https://github.com/Jersyfi/taktus/issues/199)
**Needed by:** before #197 runs its live test
**Written after the answer:** the owner answered in conversation on 2026-10-11 with a condition; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

NEED-0021 asks the owner for a wiki the guides are written into, and named BookStack, run by the
owner. The owner answered: take Notion for now, unless the session has a proposal for a European
alternative. The owner uses Docmost privately and doubts that its free edition offers what is
needed, an MCP interface.

## 2. Why you are being asked

Which wiki the owner runs is the owner's to provide (M2.5); the answer was conditional on the
session's proposal.

**Sources checked:** principle 11 (European values and sovereignty), principle 13 (no vendor
lock-in), ADR-0065 (the guides go to the knowledge system through a connector of capability
`knowledge.pages`), the adapter obligation (CLAUDE.md §6), NEED-0021 and DEC-0057.

## 3. What you must decide

Which wiki the guides go to.

## 4. What you need to know to decide

- Taktus reaches every wiki through a connector of its own (ADR-0065). The wiki needs an
  interface for programs; it does **not** need to offer MCP itself.
- BookStack is open source, runs on the owner's own servers in the EU, and has its full
  interface in the free version. Docmost would do as well where its free edition's interface
  allows creating and updating pages.
- Notion is a service of a company outside the EU; principle 11 asks for the European option
  where one exists.

## 5. Options

### Option A — BookStack, self-hosted (recommended)
- **Why recommended:** European and self-hosted (principle 11), open source with no lock-in (principle 13), its interface free.

### Option B — Notion

### Option C — Docmost, self-hosted

## 6. What is blocked

The live test of #197; the connector itself is built and tested against a fake.

## 7. How to answer

"DEC-0176: Option A.", "Option B.", "Option C." or the owner's own wording.

## Outcome

**Decided:** 2026-10-11
**Answer:** Option A, by the owner's condition: "Take Notion for now, if you have no proposal for what I can use as an EU alternative." The session has one, BookStack, and reflected it back the same evening (ADR-0008); the owner may still choose Option B or C, and the connector of #197 is written so that only its adapter changes.
**Reasoning given:** the owner's preference for a European option; the session's: self-hosted, open source, its interface free, and no MCP needed on the wiki's side.
**Recorded in:** this pull request; NEED-0021 stays open for the owner to run the wiki
