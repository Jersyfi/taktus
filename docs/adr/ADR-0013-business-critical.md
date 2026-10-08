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

## Where this promise ends

Requirement A is proven for one instance and for two daemons on one database, and depends on
the platform underneath: an instance whose only database is gone does not run without
interruption, whatever Taktus does. With two runner processes, one killed mid-step, its runs
are resumed by the other at their last boundary (`tests/integration/test_runner_failover.py`).
A runner that is alive but cut off from the database for longer than its lease loses its claim,
and no write of it reaches the run after another runner has claimed the job: the claim is a
fence, checked in the transaction of every write (`tests/integration/test_runner_fence.py`,
NTC-0044). The fence covers the run's own records — the run, its ledger entries, its provenance.
What the cut-off runner's step did outward before its write was refused is not undone: a
connector's idempotency (ADR-0024) and a worker's checkpoint bound that, not the fence. How many
runs one instance carries is not measured; that is a `1.0.0` condition. Requirement B holds for the processes that carry
instructions — each blueprint's README says which do — and passes the takeover test only when a
person has actually run the process by hand; today that is the removal test
(`blueprints/self-operation/README.md`, *By hand*). Requirement C is documented and not yet
exercised on a schedule; the restore drill is a 1.0.0 condition. Requirement D is a rule the
Taktus project follows about itself and is not enforced in code.

*Amended 2026-10-08 (#73, DEC-0066): the section said requirement A was proven for one instance
and named no limit for several. Runners on two instances are now proven against a runner that
dies; a runner that is cut off and lives is the limit, and the work to close it is #107.*

*Amended 2026-10-09 (#107, NTC-0044): a runner cut off for longer than its lease no longer
commits beside the runner that took over; the claim is a fence. The limit that remains is what
the cut-off runner's step did outward before its write was refused.*
