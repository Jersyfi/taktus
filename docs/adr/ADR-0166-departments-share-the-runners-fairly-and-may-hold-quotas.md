# ADR-0166 — Departments share the runners fairly, and may hold quotas

**Status:** accepted · extends ADR-0005 (admission control), ADR-0043 (every block is booked) and the fair claim round of #319 · issue #343, UC-7.11

## Context

#319 made a runner serve the tenants it is given in turn. Below the tenant, nothing was scoped.
On 2026-10-12 department A's 200 queued runs kept department B's one run waiting 50.6 s: the
claim took the oldest due job of the tenant, whoever it was for. A tenant also had no way to say
that one department may hold at most so many runner places at once, or commit at most so much
money in a month.

The organisation's structure exists already. A command carries its `org_path`: tenant, then
department or group, then team, then project (control-plane.md §2, UC-1.4). A run did not keep
it. A person's identity is not a place in the structure, and principle 14 forbids a quota, a
count or a figure that names a person.

Two words need a definition before the decision uses them. An **organisational unit** here is
the first level of the structure below the tenant: the department or group. A **quota** is a
limit a tenant sets on one unit. The word *unit* also names a worker's unit of execution
(ADR-0090, ADR-0102); the code therefore says `org_unit`.

## Decision

### 1. A run carries the unit it runs for, and so does its job

`StartRun.org_unit` names the unit. Every composition root that starts a run from a command
passes `Command.org_unit`: the second element of the command's `org_path`, or none when the
path names only the tenant. The run keeps it (`Run.org_unit`) and its job carries it
(`job.org_unit`, migration 0092). A run's unit never comes from its identity. Two persons of
one department share their department's places and quota, and no person is a unit.

### 2. A claim shares places fairly between units

The queue's claim orders the tenant's due jobs by their *place* first, then by age. A job's
place is the number of its unit's jobs that hold a live claim, plus its own position among its
unit's due jobs. So a unit that holds no place comes before one that holds two, whatever it
queued and whenever. With unit A holding 200 queued runs and unit B one, the second claim of
any runner takes B's run. Jobs without a unit form one unit of their own. A tenant with one
unit, or none, claims in age order as before. The round robin between tenants (#319) is
unchanged: the fairness here works inside each tenant's turn.

### 3. A tenant may set a quota per unit: concurrent runs and a monthly budget

A tenant's quota for one unit (`OrgUnitQuota`, governance) holds either limit or both:

- **Concurrent runs** — how many of the unit's jobs may hold a runner's claim at once, across
  every runner of the instance. A claim skips a job whose unit holds that many. A take-over's
  claim (ADR-0128) holds no runner place and is not counted.
- **Budget** — the money the unit's runs may commit per calendar month (UTC), in one or more
  currencies. A run commits its own budget's amount in each of the quota's currencies when it
  starts, once. The sum committed in a month never exceeds the quota. A run is held to its
  budget by admission (ADR-0005), so the unit is held to its quota with the same boundary: the
  overrun of one inner step per run, which ADR-0005 records.

A tenant that sets no quota holds none: nothing is skipped and nothing is committed. A person
sets and clears a quota (`taktusctl units`), recorded as `units.configured` by that person. A
quota is refused for a unit whose name is an identity of the tenant, so that no quota limits a
named person (principle 14).

### 4. A refusal is booked as a block

A job that a claim skipped because its unit holds its concurrent runs is marked with when it
was first held (`job.quota_held_since`). When it is claimed, the engine books that stretch as a
block on the step the run goes on with: account `limit.quota`, cause `at_unit_quota`, from the
mark to the claim (ADR-0043 §3). A step already blocked for another cause keeps its block, so
no time is counted twice.

A run whose budget does not fit what is left of its unit's month waits before its first step:
account `limit.budget`, cause `at_unit_budget`. It halts with cause `parked`, and its job is
deferred to the next check: the quota's check interval, or the start of the next month if that
comes first. A run whose budget names no amount in a currency of the quota cannot be committed.
It halts at the limit (cause `limit`), and a person gives it a budget in that currency, or
resumes it once the quota changed. A run that fits is recorded as `org_unit.admitted`, with the
amounts and the month by digest, in the transaction that commits them. A run held is
`org_unit.held`, outcome `budget` or `no_amount`.

Rehearsals (ADR-0030) commit nothing and are held by no budget quota. They do hold runner
places, and count towards concurrent runs.

### 5. Method and exactness

Each decision here is a `rule` over stored counts: which job a claim takes, whether a unit
holds its places, whether an amount fits. None is probabilistic. The amounts committed are
`exact` sums of the runs' own budgets. Rejected: a weighted share learnt from past demand
(`statistics`). A quota a person sets must hold as set, and a share that moves with history is
not a limit anyone can read.

## Alternatives

- **A second round robin in the runner, per unit.** The runner would ask the queue for every
  tenant's units, then claim per unit: one transaction per unit per round, and fairness within
  one runner only. Rejected: the order in the claim is one query, and it is fair across every
  runner, because the places it counts are the instance's.
- **The engine refuses a run of a unit at its concurrent quota after the claim.** Its block
  would be booked as every other is. Rejected: a unit at its quota with 200 queued jobs would
  have each of them claimed, parked and deferred again at every poll. A claim that skips them
  costs nothing.
- **A unit budget measured from what the unit's runs consumed.** Rejected for now. It lets a
  run start that the unit's remaining money cannot hold, and it needs the cost of every unit
  aggregated as UC-8.5 describes, which is not built. Committing the run's budget is stricter
  and exact.
- **Quotas per team or project as well.** Rejected for this step. One level is what the
  measurement asked for, and quotas on several levels need the inheritance rules of UC-8.5.

## Consequences

- Migration 0092 adds `job.org_unit`, `job.quota_held_since`, `run.org_unit`,
  `run.org_unit_month`, the tables `org_unit_quota` and `org_unit_spend`, and a claim function
  that takes the units' limits as a fifth argument. The previous release calls the
  four-argument function, which stays as it was (ADR-0093).
- A claim of a tenant that holds a concurrent quota takes a transaction lock per tenant
  (`_locks.CLAIM`), so that two runners claiming at once cannot both take a unit's last place.
  Claims of tenants without one stay parallel.
- The runner reads a tenant's concurrent quotas once per tenant per claim round.

## Where this promise ends

- Fairness is between departments inside one tenant's turn. Teams and projects below a
  department share their department's places; nothing is fair between them.
- The share is by places held, not by the work a run does. A unit whose runs are long holds its
  places longer, and another unit's runs may start more often.
- The claim counts and orders every due job of the tenant each time. Past some ten thousand due
  jobs per tenant a claim becomes slow; that is measured when an instance comes near it.
- A concurrent quota counts claims, not running steps. A run that waits for a person or for a
  time holds no claim and is not counted. A run whose lease expired with its runner is not
  counted until it is claimed again.
- A budget quota counts what runs committed when they started, not what they spent. A run that
  ends below its budget leaves its whole budget committed for the month. Of the two readings the
  quota takes the stricter.
- A budget quota holds only amounts in the currencies it names. A run is never converted
  between currencies.
- Runners of the previous release, during a rolling upgrade, neither share fairly nor hold a
  quota.
- Who sees a unit's figures is UC-6.4's, not this decision's.
