# ADR-0116 — Each model purpose is served by an ordered chain, switched at the step boundary

**Status:** accepted · amends ADR-0043 §5 (a provider at its rate limit moves the step to the
next member where one fits) and ADR-0021 §4 (a record of a step on a model carries its route) ·
issue #328, UC-8.2, DEC-0190

## Context
A process names a *purpose* for a step on a language model, such as `reasoning` or `triage`
(ADR-0003). Until this decision an instance configured one model. It served every purpose it
named, through `TAKTUS_MODEL_*`.

Three faults follow from one model.

- **A rate limit stops the work.** A provider that answers `429` makes the step wait for that
  same provider (ADR-0043 §5). A second provider with room is never asked.
- **A failure escalates.** A model that cannot be reached fails the step, and the run escalates
  to a person. A second model is never asked either.
- **Residency cannot be held.** UC-11.1 lets an organisation keep its data inside a location.
  With one model nothing chooses a model by where it processes.

A *gateway* is a proxy in front of several providers that answers in one dialect. Gateways
offer fallback chains, load balancing and caches. The market review of 2026-10-12 read two of
them (`docs/research/2026-10-12-market-review.md`, part 3). DEC-0190 accepted its outlook:
routing belongs to Taktus, and a gateway is supported only as a pass-through.

## Decision

### 1. A chain of members per purpose
`TAKTUS_MODELS` names the *members* of the instance's model configuration, in order. Each
member reads its own settings under `TAKTUS_MODELS_<MEMBER>_…`: its endpoint, its model name,
its purposes and its credential are its own alone. Its billing, output cap, provider limit,
usage kinds, location and exactness classes fall back to the instance's `TAKTUS_MODEL_*`.

The ledger records a member as `model.<member>`, never as a product (ADR-0003).

The *chain* of a purpose is every member that serves the purpose, in the order
`TAKTUS_MODELS` names them. An instance that names no members has one member, configured by
`TAKTUS_MODEL_*` as before and recorded as `model.endpoint`.

### 2. A member declares where it processes and what it may produce
- **Location.** `own` is the organisation's own infrastructure. `eu` is inside the European
  Union. `elsewhere` is anywhere else. The operator declares it, and `elsewhere` is the
  default: a location nobody declared is outside every rule narrower than *anywhere*.
- **Exactness classes.** The classes of a step the member may produce a result for, out of
  `sourced`, `tolerant` and `free`. All three are the default. A member declared for `exact`
  is refused when the configuration is read, because a language model never produces an
  `exact` result (ADR-0014).

### 3. A tenant's residency rule
A tenant's *residency rule* names the location its data may be processed in: `own`, `eu` or
`anywhere`. It may name a narrower location for a *data class*, such as `personal`. A rule
for a class is never wider than the tenant's own.

A tenant that set no rule holds `anywhere`. `taktusctl residency` shows and sets the rule. A
change is the ledger entry `residency.configured` in the transaction that stores it.

A step on a model may declare the data class of what it sends, as `data_class` in its work.
The location a step permits is the rule for that class, or the tenant's own where the class
has none.

`own` permits a member located `own`. `eu` permits `own` and `eu`. `anywhere` permits every
member.

### 4. The route is the first member that fits
The *route* of a step is the first member of its purpose's chain that fits the step. A member
fits when three things hold.

1. The step's permitted location admits the member's location.
2. The member may produce the step's exactness class.
3. The member is not cooling down (§5).

The route is a pure function of the chain, the step's declared needs and the members cooling
down at that moment. A step with the same needs at the same moment is routed to the same
member. Admission takes the step's estimate from the routed member, at that member's price.

No member fitting for location or exactness fails the step with outcome `no model`. Its reason
names each member and why it does not fit. The step never moves to another method: that is
method selection (ADR-0004).

### 5. A member at its limit or failing cools down
A member *cools down* when it answered at its rate limit, or when a call to it failed. A
member at its rate limit cools down for the delay its `Retry-After` names. Where it names none,
and after a failure, it cools down for `TAKTUS_MODEL_COOL_DOWN_SECONDS`, 60 by default.

The engine of an instance keeps the cool-downs in its memory, for every run and tenant it
executes. A provider's limit applies to the credential, and the credential is the instance's.

### 6. The step moves at its boundary
The engine never changes the member in the middle of a call. It moves the step at the boundary
after the call.

- **At a rate limit.** The step goes back to its boundary as ADR-0043 §5 says. The ledger says
  `step.waiting` with outcome `at_provider_limit`, and the block is booked to `limit.provider`.
  Where another member fits, the step is admitted again at once and routed to it. The block
  ends when that member answers. Its record names the member that was at its limit and, as
  `answered_by`, the member that answered. Where no other member fits, the step waits as
  ADR-0043 says.
- **At a failure.** The attempt ends as `step.finished` with outcome `failed`, and no block is
  booked: a failure is not a block (ADR-0043 §4). Where another member fits, the step is
  admitted again at once and routed to it. Where none fits, the run escalates as before.
- **Every fitting member cooling down.** The step is admitted on the first member that would
  fit if nothing cooled down. It calls nothing, goes back to its boundary, and waits booked to
  `limit.provider`, for the delay until the first cool-down ends.

A move takes a fresh estimate at the new member's price. A run's budget therefore holds across
the move.

### 7. The provenance records the route
The provenance record of a step on a model gains `route`. It names the purpose, the member
that produced the result, the location the step permitted, the data class where the step
declared one, and every member the route passed over with its reason: `residency`,
`exactness` or `cooling_down`. These are identifiers and tokens, never content (ADR-0021 §3).
The record's `adapter` is the member that produced the result, as before.

A route adds at most 320 bytes to a record, plus 112 bytes for every member passed over. The
bound of ADR-0021 §4 grows by that much.

### 8. Routing is not delegated to a gateway
A gateway can hold a fallback chain of its own. Taktus does not hand its routing to one, for
four reasons.

- **The route would not be in the provenance.** A gateway's fallback happens behind one
  endpoint. Taktus would record the alias it asked, not the model that answered.
- **Residency would be unprovable.** One alias may fan out to providers in several locations.
  The member's declared location would have to be the widest behind the alias.
- **Admission would be wrong.** Taktus reserves a step's estimate at the price of the member it
  routes to. A gateway that falls back to a dearer model spends past the reservation.
- **Blocked time would be hidden.** A gateway that retries a `429` inside the call books the
  wait to nobody. Taktus books it to `limit.provider` at the step boundary.

A gateway may stand behind a member as a *pass-through*: one alias for one model, no fallback,
no load balancing and no cache. Each alias is then one member with its own location.
`deploy/docker/README.md` documents that profile and names a gateway that does not fit it.

## Alternatives
- **Routing inside a gateway.** Rejected for the four reasons of §8.
- **Moving to the next member inside the call.** The call would retry with another model
  before the step's boundary. The estimate admitted would be the first member's, and the
  ledger would show one attempt for two calls.
- **A chain setting per purpose, such as `TAKTUS_MODEL_CHAIN_REASONING`.** A second place for
  the order of the same members. One list with each member's purposes gives every chain.
- **Cool-downs in the database.** Every instance would see the same cool-downs. It needs a
  table written on every `429`, for a state that frees itself within minutes. The memory of the
  engine costs one extra `429` per instance.
- **Choosing by price, latency or load.** A score over measured values would change the route
  between two identical steps. The route would not be reproducible.

## Consequences
- `TAKTUS_MODELS`, `TAKTUS_MODELS_<MEMBER>_…`, `TAKTUS_MODEL_LOCATION`,
  `TAKTUS_MODEL_EXACTNESS` and `TAKTUS_MODEL_COOL_DOWN_SECONDS` are new settings.
- `ResolvedModel` carries the member's location and exactness classes. The run's `ModelPool`
  gains `chain`.
- The run gains the port `Residency`. The governance component holds the rule
  (`ResidencyRule`), its command line and the ledger kind `residency.configured`.
- Migration 0061 adds the table `residency_rule` and the column `provenance.route`.
- `Provenance.json` gains the optional `route`.
- A block of a step that moved to another member ends with `answered_by` in its record.
- NTC-0217 records the shipped defaults: `anywhere`, `elsewhere` and 60 seconds.

## Where this promise ends
A member's location is what its operator declares. Taktus holds routes to the declaration and
does not verify it. A pass-through gateway behind a member is one member with one location,
and Taktus cannot see what it does behind its alias.

Cool-downs live in the memory of one engine. A restart forgets them, and several instances
each learn them on their own. Each costs at most one more `429` or failed call per member.

The route excludes no member for want of an evaluation. That a member is eligible only after it
passed the step's evaluation is UC-8.4, not built here. No member's request or token rate is
counted before a call. A limit is learned from the provider's answer.

The rule is per tenant and per data class. A rule narrowed per process is UC-11.1, not built
here. The rule steers the route of a step on a model. A worker's unit and a connector are held
to it by UC-11.1, not by this decision. A data class is what the process declares, and Taktus
does not infer it.

A rehearsal replays a model's answer from its recording, which leaves the instance for no
location. Its route names the recorded member as `own`.

Credentials and budgets per tenant are #352. Every member here is reached with the instance's
credential for it.
