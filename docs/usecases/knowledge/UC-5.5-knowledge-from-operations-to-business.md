---
id: UC-5.5
title: Knowledge, from the operational to the business
component: knowledge
epic: E5
serves: [P2, P4, P7]
state: specified
version: 0.3.0
tests: []
adrs: {ADR-0003: d0268914fed9, ADR-0014: 6611f7833deb, ADR-0024: d57aa05c4f28}
supersedes: null
---

# UC-5.5 — Knowledge, from the operational to the business

## 1. What must be achieved

Taktus can draw on all the information that matters, however the organisation holds it: repositories
with their documentation, wikis and knowledge tools, shared drives, databases. From them it forms one
knowledge layer that joins operational knowledge — how is process X carried out? — with business
knowledge — why does process X exist, and what does it contribute?

Every statement Taktus makes from that knowledge names its source. Nobody learns through Taktus what
the source would not have shown them. The quality of Taktus's work rises demonstrably with the
knowledge connected.

## 2. How it is verified

- Every statement drawn from connected knowledge names the source it came from, with a link that
  opens it. A step whose result rests on knowledge is of class `sourced` or stricter (ADR-0014), and
  an answer without a source does not leave the step.
- The rights of the source system hold. A test with two identities whose permissions in the source
  differ asks both the same question, and each gets only what the source shows them. Taktus reads with
  the asker's rights, never with wider ones of its own.
- Every source is connected through a connector by capability (ADR-0003). Removing one changes what
  Taktus knows and breaks no process: the removal test.
- Taktus keeps an index, references and digests of what it read, so that it can find and cite it; the
  source stays the record. A source document changed or removed is reflected in the index, and an
  answer never cites a version the source no longer holds without saying so.
- The effect of connected knowledge on the quality of work is measured: the same work with and without
  a source connected is compared on the figures of the value ledger (UC-9.1).

## 3. Where the boundary lies

**Not a knowledge system.** Taktus replaces no wiki and no document store (principle 1); its index
is not a second record. **Not the data warehouse**, whose connection is UC-5.6. **Not a guarantee that
the source is right.** A cited statement is as good as its source; Taktus says where it came from, not
that it is true. **Not training a foundation model** on the organisation's knowledge
(`docs/vision/non-goals.md`).

## 4. What it rests on

The `knowledge` component, which owns knowledge sources, embeddings and citations
(`docs/architecture/project-structure.md` §1); the exactness class `sourced` (ADR-0014); connectors and
the adapter obligation (ADR-0003, ADR-0024); rights and least privilege (UC-7.3), sharing connectors per
circle (UC-8.8); a session with project knowledge (UC-1.8), which draws on this layer. Definition
`UC-5.5`. The roadmap's `0.3.0` names sessions with project knowledge; this use case is proposed there.
