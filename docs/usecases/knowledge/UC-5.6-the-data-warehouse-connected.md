---
id: UC-5.6
title: The data warehouse connected
component: knowledge
epic: E5
serves: [P1, P7, P12]
state: specified
version: 0.7.0
tests: []
adrs: {ADR-0006: 4ef70c98354b, ADR-0014: 6611f7833deb, ADR-0021: 202e0442e7ec, ADR-0024: ac6a1fe1610a}
supersedes: null
---

# UC-5.6 — The data warehouse connected

## 1. What must be achieved

Above all for larger and data-led organisations: Taktus connects to the data warehouse or lakehouse
where the organisation keeps its consolidated data. It can query that data in natural language, use it
in processes — "escalate when figure X falls below threshold Y" — and feed it into reports and
controlling views.

Reading is the safe default. Writing is granted explicitly, per connection. Every query Taktus
generates can be seen and is recorded. The warehouse's own permissions, down to rows and columns, are
passed through and never bypassed.

## 2. How it is verified

- A new connection reads only. Writing is a grant on that connection, made by a person with the right
  to make it, and recorded; a write attempted without the grant is refused before it reaches the
  warehouse.
- Every query Taktus sends is recorded with the step that sent it, by reference in the ledger
  (ADR-0006), and a person entitled to the step can read the query text.
- The warehouse is queried with the identity of the person or process on whose behalf Taktus acts, so
  that row-level and column-level security apply. A test with two identities whose warehouse
  permissions differ sends the same question and finds each answer limited as the warehouse limits it.
- A figure that feeds a step of class `exact` comes from a query that is fixed in the process version
  and was reviewed when the version was registered. A query a language model writes during a run may
  feed only a step of class `tolerant` or `free` (ADR-0014).
- A threshold over a warehouse figure can start or escalate a process, and the reading that triggered
  it is in the step's provenance record (ADR-0021).
- Every warehouse figure shown in a view or a report is in the export (UC-5.7).

## 3. Where the boundary lies

**Not a warehouse.** Taktus keeps no copy of the organisation's data beyond what a step consumed
(principle 1). **Not a business-intelligence tool**: the views are UC-6.4, and the organisation's own
tool is UC-5.7. **Not the warehouse's governance.** Who may read what in the warehouse is decided
there; Taktus respects it and does not administer it.

## 4. What it rests on

Connectors and their effect classes (ADR-0024); exactness classes and which methods may produce an
`exact` value (ADR-0014); the content-free ledger (ADR-0006) and the provenance record (ADR-0021); the
export without a figure left behind (UC-5.7); rights and least privilege (UC-7.3). Definition `UC-5.6`.
The roadmap names no version; `0.7.0`, with the breadth of connectors the second domain brings, is
the session's proposal.
