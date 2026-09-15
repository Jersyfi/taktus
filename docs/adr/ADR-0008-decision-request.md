# ADR-0008 — Decision requests and strategic anchors

**Status:** accepted

## Context
A process should run unattended while direction stays with its owner. The existing model only knows
*escalation*, and escalation reports a fault. What is missing is the planned, expected, recurring
question during normal operation.

## Decision
Two things that belong together.

**1. Strategic anchors** as a second class alongside legal anchors. Same mechanism — an act stays
with a person regardless of the autonomy level — different occasion: scope, accepting or rejecting a
feature, version assignment, architectural change, releases, licensing and pricing, public
communication.

Every organisation defines its own anchor set. A business at level 4 with a different model will
draw the line elsewhere, and some owners will hand over nearly everything. **The set is
configurable and can be reduced, but never emptied** — an act with legal force always has a person
behind it.

**2. Decision requests** as a domain object with a fixed shape: situation · what must be decided ·
options with a recommendation · what is blocked · deadline. Channel-independent, with a confirmation
loop, producing an entry in the decision register.

## Alternatives
- **Modelling it as escalation** — mixes fault with plan; the reader can no longer tell urgency
  apart and stops reading.
- **A free question in chat** — no shape, no blocked-work tracking, no history, no reuse.
- **Parsing the answer and acting on it** — rejected. A misread free-text answer at level 4 is
  exactly the harm governance exists to prevent.

## Consequences
- Level 4 becomes definable for a product whose direction a person owns: **unattended in execution,
  anchored in direction.**
- Each decision costs one extra confirmation message. Worth it.
- The decision register becomes a precedent memory. Once a pattern is consistent, Taktus proposes
  turning it into a rule — autonomy grows through use, without control being given away.
