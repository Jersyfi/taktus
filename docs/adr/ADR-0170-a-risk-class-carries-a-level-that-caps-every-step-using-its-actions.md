# ADR-0170 — A risk class carries a level that caps every step using its actions

**Status:** accepted · extends ADR-0039 (a level is applied at the step boundary) and ADR-0042
(a tenant's anchors and risk classes are configuration) · roadmap `0.7.0`, "autonomy per action
class in production use"; UC-7.1, UC-04

## Context

UC-7.1 §2 asks for a level per process, per tool action and per risk class, the lowest holding.
Levels per process and per tool action are built (ADR-0039). Both live in the process version's
statement (ADR-0026), which the process's author writes.

That is enough for a process the tenant writes itself. It is not enough for a process the
tenant takes from a blueprint. A blueprint is product: its statement is the same for every
tenant that registers it (ADR-0092). The tenant's own limits — "nothing that touches a payment
runs above level 2 here, in any process" — are the tenant's configuration and must not require
editing the product's bundle. The invoice-to-payment domain (UC-04) is the first that runs such
an action in production. Its booking proposals and its payment release are the cases.

The tenant already names sets of tool actions: a **risk class** is a name for capability
patterns, kept in the anchor configuration so that an anchor can select by it (ADR-0042). Until
now a risk class could select an anchor and nothing else. UC-7.1 §5 says so: "a tenant's risk
classes select anchors, not levels yet".

Four questions had to be answered. Where is the level of a risk class kept? What does it do to
a step? When does a run take it on? What happens to the counting of corrections (ADR-0110)?

## Decision

### 1. A risk class may carry a level, beside its patterns

The anchor configuration gains `levels`: a map from a risk class it defines to an autonomy
level. A level for a class the configuration does not define is refused, as an anchor that
selects one is: it would never hold. A class without a level sets no ceiling. The shipped
default sets none. `taktusctl anchors set` takes the field in the same document;
`anchors.configured` records it with the rest. Migration 0095 adds the column
`anchor_configuration.levels`, nullable.

### 2. The level is a ceiling on every tool action the class covers

A tool action a risk class covers, by the matching of ADR-0042, runs at most at that class's
level, in every process of the tenant. Where two classes with a level cover one action, the
lower holds. A ceiling never raises anything: where the process, its action or a lowering by
rule is lower already, that lower level holds. A step's level stays the lowest that applies to
it (ADR-0039), now over four sources: the process, its actions, a lowering by rule (ADR-0110)
and the tenant's ceilings.

### 3. A run takes the ceilings on when it is created

When the run engine creates a run, it asks the governance component, through the run's port
`Anchors`, for the ceilings on every tool action the run's steps use. Each one lower than the
run's own level for the action is written into `Run.actions` before `run.created` is recorded.
The run carries it from then on, as it carries its levels from its start, and the entry
`run.created` holds it. Every later question of the run about a step's level reads it there:
the boundary, the decision on a proposal, healing at level 4. A rehearsal is asked no level and
takes on none (NTC-0079).

### 4. A capped step is counted as its action

A step a ceiling holds is held by the action the ceiling caps: `Held.action` names it. A
decision on its proposal is therefore counted for that action class (ADR-0110 §2), as a step
held by the action's own level is. A unit's rate falls and rises as before. A raise proposed by
rule (ADR-0110 §8) raises the statement, never the ceiling: the ceiling is the tenant's and
moves only when a person configures it again.

## Alternatives

- **Write the tenant's limits into the bundle's statement.** The bundle is product and is the
  same for every tenant (ADR-0092). Each tenant would fork it to change one level.
- **A second statement per tenant and process.** ADR-0039 rejected a second place where a level
  is set and rises. A ceiling cannot raise; it is not such a place.
- **Apply the ceiling at every step boundary instead of at the run's creation.** A ceiling
  configured while a run waits would then change the level of a step a person was already asked
  about, and the level the run started with would no longer be the one it shows. A ceiling is
  configuration, as the statement is; the statement too is read once, at the start.
- **Record a ledger entry per capped action.** `run.created` already carries the run with its
  actions. A new kind would change `LedgerEntry.json` for a fact the run's own entry holds.
- **Keep the levels in a table of their own.** A risk class is defined once, in the anchor
  configuration, and its level belongs beside its definition. A second table would let the two
  drift.

## Consequences

- `governance`: `AnchorConfiguration.levels`, refused for an undefined class;
  `domain/service/anchors.py` `ceilings`; `AnchorsInForce.ceilings`.
- `run`: the port `Anchors` gains `ceilings`; `RunEngine` folds the ceilings into `Run.actions`
  at creation.
- Migration 0095, the column `anchor_configuration.levels`.
- `docs/architecture/governance.md` §1 and UC-7.1 §5 no longer say that levels per risk class
  are not built.

## Where this promise ends

A ceiling holds for a run created after it was configured. A run created before keeps the
levels it started with, and a step that already waits is not asked again. A ceiling covers the
tool actions a step declares: the capabilities it requires and the connector operation it calls
or waits on. An act a worker performs beyond its step's declaration is not capped, as it is not
anchored (ADR-0110). A step whose work cannot be read when the run is created is not looked at
for a ceiling; it is refused where it runs, with its reason.

The ceiling caps the level. It does not select an anchor, change what an anchor asks, or decide
who may confirm a step: who may confirm is not checked until rights per role exist (UC-7.3).
Which risk classes a tenant has, and their levels, is the tenant's configuration. Nothing checks
that a class covers what its name says.
