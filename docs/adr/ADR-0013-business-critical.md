# ADR-0013 — Taktus is business-critical: what follows

**Status:** accepted · supersedes an earlier draft that claimed the opposite

## Context
An earlier draft contained the sentence that Taktus "must never sit in the critical path of its own
repair". The sentence was unclear and, in substance, backwards. **At level 4 Taktus is the
business-critical path.** If Taktus stops, accounting stops, sales stops, development stops. That is
the intent.

## Decision
Taktus is built like other business-critical systems. Four requirements:

**A — It runs without interruption.** Several instances, load spread across them, restart without
data loss. A restart resumes at the last step boundary. From `0.2.0`, not later.

**B — A person can take over any process.** Every process Taktus runs carries maintained
instructions: the sequence, the knowledge needed, the systems involved, a pointer to the
credentials. The **takeover test** passes when a person can run the process without Taktus. This is
why depending on Taktus is not a risk: the dependency can be dissolved at any time.

**C — Taktus is repairable without Taktus.** If Taktus is faulty, the repair must not depend on a
working Taktus. There is a manual way to restore an earlier version — through the command line and
through the target environment's deployment tool. It is documented and exercised.

**D — A release rule, for self-development only.** Taktus changes its own repository but does not put
itself into production: a version Taktus built is deployed by another instance or by a person.
Otherwise a faulty version could block the path its own fix would travel.

**A to C are product properties and apply to every Taktus installation. D applies only to the Taktus
project itself and is not a general architectural claim.**

## Consequences
- High availability moves from "later" to `0.2.0`.
- The takeover test becomes a release condition for autonomy level 4, not a reporting metric.
- The manual rollback path belongs in the operating documentation and in regular exercise.
