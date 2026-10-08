# ADR-0035 — A time trigger fires once per slot, through the elected scheduler

**Status:** accepted

## Context
A process bundle has carried `triggers` since the first slice, and nothing acted on them
(`examples/README.md`). The scheduler role was elected and ticked, and the tick did nothing
(ADR-0002, `docs/architecture/project-structure.md` §5). The removal test S-01 is meant to run
weekly (`blueprints/self-operation/`), so a weekly workflow of the repository's CI ran it
instead, through a script. An installed instance had no way to run its own weekly check.

Three facts shape the decision. Several instances may run the scheduler role at once, and only
one leads, but a lead can be lost in the middle of a tick (`ports/leadership.py`). A leader can
die between starting a run and remembering that it did. And an instance can be down for longer
than one period of a schedule.

S-01 also needs an input: the integration it withholds. The script ran it once per configured
integration, and a schedule alone gives a run no input.

## Decision

### 1. What a schedule is
A schedule trigger names a five-field cron expression — minute, hour, day of month, month, day
of week — read in UTC, or one of `hourly`, `daily`, `weekly` (Mondays 00:00 UTC) and
`monthly`. A **slot** is a minute the expression matches. A schedule that matches no day is
refused when the bundle is registered.

### 2. Which version fires
Registering a version makes it the process's active version, the pointer control-plane.md §4.2
names. The scheduler fires the schedule triggers of the active version of every process in
every tenant the instance serves. Event triggers are not the scheduler's.

### 3. When a trigger is due
The scheduler remembers, per process and trigger, when it first saw the trigger (`armed_at`)
and the latest slot it fired for (`trigger_state`, migration 0011). A trigger is due when the
latest slot at or before now lies after both. Slots before the trigger was armed do not fire,
so a process registered on a Wednesday does not run for the Monday before. Slots missed while
no scheduler led start one run, for the latest of them, not one per missed slot. A trigger is
identified by the digest of what it says, so a new version with the same trigger keeps its
memory, and a changed trigger starts fresh.

### 4. A slot starts its runs once
Three mechanisms hold this, each for a failure the others miss.

- Only the elected scheduler fires (ADR-0002).
- The run's identifier is derived from the tenant, the trigger, the slot and the item. The run
  engine refuses to create a run under an identifier that exists, in the transaction that
  would create it. The run's job carries a derived identifier too, so two creators that miss
  each other's run collide on the job.
- The firing is recorded as fired only after its runs exist. A leader that dies in between
  leaves the slot due; the next leader starts what is missing, and the runs that exist are
  refused as existing.

A run the engine refuses for a reason of its own — the version names no budget, a step cannot
be executed — is not retried every tick. The slot is recorded, and the refusal is a
`trigger.refused` entry in the ledger and an error in the log.

### 5. A scheduled run is given its inputs by the trigger
A schedule trigger gives fixed values in `inputs`, and one run per item in `each`: a read
operation of a connector, the list in its output and the field of each item. Together they
give every input the process declares, or the version is refused at registration. A scheduled
run has nobody to ask. `each` calls only an operation declared `read`, through the connector
port like every outward access (ADR-0003). S-01 lists the instance's integrations through the
loopback connector and starts one run per integration.

### 6. Who acts, and what the ledger says
A scheduled run comes from a command on the channel `channel.schedule`, commissioned like any
other (control-plane.md §1). It acts as the identity the identity port places in the tenant;
until the identity component exists that is the provisional operator identity (DEC-0013).
Without one, nothing fires and the log says why. Every run a trigger started carries
`run.triggered` beside `run.created`, in the same transaction. The entry names the trigger's
kind as its outcome and carries the digest of the trigger's document — the trigger, its
schedule, the slot and the item — which the command keeps in its context. The ledger stays
content-free (ADR-0006).

## Alternatives
- **Fire on the leader's word alone.** The election keeps two leaders apart only between
  ticks. A leader that loses its lead mid-tick, or dies after starting a run, would fire twice
  or not at all.
- **One run per missed slot.** A weekly check run five times after an outage says nothing the
  last of the five does not, and it costs five times.
- **Arm a trigger when the version is registered.** The registration would need the clock and
  the trigger state of another use case. Arming on first sight costs at most the first slot
  after a registration made while no scheduler ran.
- **Give a scheduled run the declared examples as inputs.** An example shows the shape of an
  input. Running on it would run S-01 for `worker.endpoint` alone, every week, and call that
  the removal test.
- **A cron library.** The five fields fit in a page of standard Python in the process
  component. A dependency in the core is a technology import the architecture forbids.

## Consequences
- `trigger_state` is a new table (migration 0011), written through the process component.
- `StartRun` takes a derived `run_id` and the `trigger` that started the run; the engine
  answers `RunExists` for a run that exists.
- `taktusd` with the scheduler role fires S-01 weekly. `.github/workflows/removal-test.yml`
  stays until an installed instance runs S-01 on its own (issue #69).

## Where this promise ends
A slot starts its runs once as long as the run engine sees every run of the tenant in the
same database. Two instances on two databases each fire. A run that was created and later
deleted by a person would be created again by a firing of the same slot, but a slot is fired
again only until it is recorded, which happens at the end of the same tick. A slot fires only
while a scheduler leads. A slot that passed during an outage is fired late, once, when one
leads again, and a slot older than the latest missed one is never fired. Time is the clock of
the instance that leads. A leader whose clock runs ahead fires early, and the slot is then
recorded and does not fire again when the correct time arrives. The `each` list is what the
read answered at the moment of the firing; an integration added after it waits for the next
slot. A version registered while no scheduler runs is armed when one first leads, so a slot
in between does not fire. Event triggers are not covered here.
