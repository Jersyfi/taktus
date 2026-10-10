# ADR-0048 — An event starts each process its triggers name once, through the outbox and the elected automation role

**Status:** accepted · makes issue #76 buildable, beside ADR-0035 for time triggers

## Context
A process bundle has carried event triggers since the first slice, and nothing acts on them. The
intake keeps what a connector accepted and the identity component placed (ADR-0024, ADR-0040).
A person then completes it into a command by hand, on the control plane's surface. The
`automation` role starts and waits. The outbox table exists (ADR-0002) and nothing writes it.

ADR-0035 decided how a time trigger fires: once per slot, through the elected scheduler. It
excluded event triggers. An event differs from a slot in three ways. It arrives from outside, on
the HTTP surface, not from the clock. The source may deliver it twice. And one event may concern
several processes.

Three questions were open (issue #76). What happens when one event is delivered twice. What
happens when it arrives while the instance, or a part of it, is down. And what happens when one
event matches two triggers. A fourth was implied: how a trigger's `filter` and `condition` are
evaluated, and by which method. The events contract (`contracts/events/v1`) states the shapes;
this record states the delivery.

## Decision

### 1. An event is an intake the identity component placed
The events contract defines the event: the source's delivery identifier, a kind of its catalogue,
the channel, two moments and the context. It is derived from a kept intake. An intake whose
sender nobody could place is kept nowhere (ADR-0040 §5), so it never becomes an event. An intake
of a kind outside the catalogue is kept, and no trigger can name it.

### 2. A trigger decides by rule
A trigger matches an event when the kinds are equal and the trigger's filter holds. A filter is
a set of entries over the event's context, each holding when the field's value is one of the
values named; all must hold (`contracts/events/v1` §4). It reads the event and nothing else. The
same event and the same version therefore give the same answer every time, and the answer can
be recomputed from the ledger's digest and the stored event.

A trigger is not a step. It produces no result and has no exactness class, so the choice of a
method kind among several (anchors.taktus.md M3.13) does not arise: its method is `rule`, fixed
here. A process that must judge whether there is work does so in its first step, which carries
its method, its reason and its fallback like any step, and ends the run when there is nothing to
do. Whether a run starts is never decided by a probabilistic method, as ADR-0023 decides for the
emergency stop.

A condition is a named state of the instance, from a closed list in the contract. It is checked
when the run would start. A condition that does not hold makes the reaction wait for the next
pass. It never discards the event.

### 3. The path: intake, outbox, automation
The intake keeps the event and writes an outbox entry `intake.accepted`, naming the event, in
the same transaction. Either both exist or neither does.

The `automation` role leads through the leadership port, under its own name, as the scheduler
does (ADR-0002). Only the leader reacts. While it leads, every pass reads the unpublished outbox
entries of every tenant the instance serves, in the order they were written, and for each:

1. asks the process component which triggers of the processes' active versions match the event;
2. with no match, marks the entry published and leaves the intake as it was, so that a person
   can still complete it by hand;
3. with a match whose condition does not hold, leaves the entry unpublished and goes on to the
   next one;
4. otherwise completes the intake into one command, commissions one plan per matching process
   from it, submits one run per plan, and marks the entry published once every run exists.

The command acts for the identity the sender was placed as, as a command from any channel does
(ADR-0040 §6). A schedule acts for whoever activated the version because a schedule has no
sender; an event has one.

### 4. One delivery starts each process once
Four mechanisms hold this, each for a failure the others miss.

- **The intake keeps a delivery once.** A delivery whose identifier is already kept in the
  tenant changes nothing and writes no outbox entry. Until now a redelivery replaced the kept
  intake, which would reset one already completed.
- **Only the elected automation role reacts.** Two instances never react to the same entry at
  the same moment while the lead holds.
- **The run's identifier is derived** from the tenant, the process and the event's identifier.
  The run engine refuses to create a run that exists (ADR-0035 §4). A second reaction to the same
  delivery — after a lost lead or a restart — names the same run.
- **The entry is marked published only after its runs exist.** A leader that dies in between
  leaves the entry unpublished. The next leader completes nothing twice: an intake completed
  before keeps its command, and that command is used. The runs that exist are refused as
  existing.

### 5. One event, several triggers
An event that matches triggers of several processes starts one run of each. An event that
matches several triggers of one process starts that process once, with the inputs of the first
of them in the order the version declares them. Triggers of one process are alternatives that
say when it starts, not instructions to start it several times.

### 6. When the instance, or a part of it, is down
- **The intake is down.** The delivery is not accepted, and the source's own redelivery is the
  only way it arrives later. Taktus does not ask a tool what it missed.
- **The automation role is down, or nobody leads.** The entries wait in the outbox, and the next
  leader reacts to them in the order they were written. Nothing is lost and nothing is reacted
  to twice.
- **A version registered after the event arrived.** An event received before the active version
  of a process was registered does not start that process. The process component records when a
  version became active. Without this rule an instance whose automation role was down for a day
  would start a process just registered for events from before it existed, which ADR-0035 §3
  refuses for slots for the same reason.

### 7. Inputs and registration
An event trigger gives the run every input the process declares: fixed values in `inputs`,
context fields in `from_event`. Registration refuses a version whose event trigger names a kind
outside the catalogue, filters on a field its kind does not carry, names a condition outside the
list, takes an input from a field its kind does not require, or leaves an input without a value
(`contracts/events/v1` §3).

### 8. The ledger
Every run an event started carries `run.triggered` beside `run.created`, in the same transaction,
with the outcome `event` and the digest of the trigger's document — the process, the trigger,
the event's identifier and kind. A run the engine refuses for a reason of its own — no budget,
work it cannot execute — is a `trigger.refused` entry, and the outbox entry is marked published,
so that the refusal is not repeated every pass. The ledger stays content-free (ADR-0006).

## Alternatives
- **React in the HTTP request that accepted the delivery.** The webhook's sender waits for the
  answer, and a crash between accepting and starting would lose the reaction with no record of
  it. The outbox keeps acceptance and reaction apart, in one transaction with the event.
- **Let a language model read a filter written in words.** P-02's bundle once said "a section
  of the ready standard missing". Whether a run starts would then vary between two readings of
  the same event, and an instance could not say afterwards why it started. The judgement belongs
  in the process's first step, where its method is declared and observed.
- **One run per matching trigger.** Two triggers of one process matching one event would run
  the same work twice for one cause.
- **Discard an event whose condition does not hold.** An issue labelled ready while the
  instance is full would then never be implemented. A condition says when, not whether.
- **Poll the source for events missed during an outage.** It needs a read per kind per
  connector and a memory of what was seen, and duplicates what a schedule trigger already does:
  a process that must not miss an event also carries a schedule trigger over the source's
  current state.
- **Act for the identity that activated the version, as a schedule does.** Any linked person
  could then make a process act with someone else's identity by causing an event. Acting for
  the sender keeps every command with whoever caused it.
- **Process outbox entries on every instance with a row lock instead of an election.** It
  spreads the load, and it needs claims and leases like the queue's (ADR-0038). Reactions are
  few and cheap: they submit runs, which the runners spread. One leader is enough until a
  measured event rate says otherwise.

## Consequences
- The outbox is written for the first time, by the intake, and read by the automation role.
- The automation role leads through the leadership port, beside the scheduler.
- The process component answers which triggers match an event, and validates event triggers at
  registration against the contract.
- A process records when its active version was registered (a migration).
- The intake no longer replaces a kept delivery on redelivery.
- The bundles of P-01, P-02 and P-03 name kinds of the catalogue. Their triggers, written before
  the contract, are rewritten to it in the change that builds this record.

## Where this promise ends
A delivery starts each process at most once as long as every instance sees the same database;
two instances on two databases each react. A delivery the source sends with a new identifier —
a label removed and added again, a redelivery the source numbers anew — is a new event, and
starts the process again; the process's own first step must refuse what it has done, as P-03's
admission refuses a claimed issue. An event that never reached the intake starts nothing, and
nothing notices that it is missing. A filter sees the event as the source described it when it
happened, not the source's state when the run starts: an issue labelled ready and unlabelled a
second later still starts the run. The `paths` of a pushed branch are what the source listed,
and a source that truncates its list hides a changed file from a filter. A condition that never
holds keeps its event waiting without end; nothing expires it, and the log says on every pass
that it waits. Order holds within one tenant, in the order the intake wrote the entries; across
tenants there is none. Who may cause which event is not decided here: authorisation is UC-7.3,
and today any linked sender can start any process whose trigger matches what they did. Events
that arise inside Taktus — an anchor hit, a milestone reached — are not covered; the catalogue
of v1 holds only events from tools.
