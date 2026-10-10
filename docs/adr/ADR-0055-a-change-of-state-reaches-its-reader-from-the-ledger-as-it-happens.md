# ADR-0055 — A change of state reaches its reader from the ledger, as it happens

**Status:** accepted · makes UC-6.10's condition *live* buildable (issue #103, DEC-0055)

## Context
UC-6.10 requires that a change of a run's state reaches every open representation of that run
within 5 seconds, without the reader reloading. The changes it names are a step started,
completed, failed or halted, and a decision awaited. Today the control plane's HTTP surface
answers only when asked. A representation that asks every few seconds would meet the figure. It
would also cost one read per reader per interval, idle or not, and it would say nothing about
what a reader missed while away.

The use case leaves the transport to an ADR (UC-6.10 §3). Four questions are open: which
records a reader receives, in which shape, how a reader resumes after a broken connection
without missing a change, and how the 5 seconds hold when one instance runs several copies of
its `api` role.

Three facts of the repository bound the answer.

- **The ledger is the single source of every metric** (`docs/architecture/control-plane.md` §6).
  Every change of a run's or a step's state is recorded there, in the same transaction as the
  change itself. An entry carries identifiers and tokens, never content (ADR-0006).
- **One tenant has one chain** (ADR-0020). Its entries are appended under a transaction lock on
  the chain (`PostgresLedgerStore.last`). The order of their sequence numbers is therefore the
  order in which they became visible: an entry with a lower number never commits after one with
  a higher number.
- **PostgreSQL is the only mandatory dependency** (ADR-0002). A *replica* here is one running
  process of the `api` role; an instance may run several of them against its one database, which
  is what ADR-0013 A means by several instances with the load spread across them.

## Decision

### 1. The transport is Server-Sent Events, from the `api` role
A reader opens one long-lived HTTP response, `GET /changes`, and receives changes on it as
Server-Sent Events: a standard text format over plain HTTP, in which every event carries an
`id`, and a reader that reconnects sends the last `id` it received as the header
`Last-Event-ID`. The worker contract already uses the same format for its event stream
(ADR-0007). The stream runs one way, from Taktus to the reader. Everything a reader asks for
still goes through the ordinary requests of the HTTP surface.

A request names its **scope**: the tenant as a whole (the overview), one process, or one run.
The origin of a result needs no scope of its own: a result's origin changes only when a step
completes, and that change is in the run's scope.

The reader authenticates with an account key in the `Authorization` header, as every
authenticated request on the surface does. The key is never accepted in the URL. The browser's
built-in `EventSource` cannot send a header, so the web app reads the stream with `fetch` and a
streamed response body.

### 2. The source is the ledger; a signal only wakes the reading
What a reader receives is read from the ledger, and from nothing else. The stream holds no
second record of what happened.

Every insert into `ledger_entry` sends a PostgreSQL notification, from a statement-level
trigger in the database, so that no writer can forget it. The notification carries the tenant
and nothing else. It commits with the transaction that wrote the entries; a rolled-back entry
sends nothing.

Each replica keeps one database connection that listens. On a notification for a tenant with
open streams, the replica reads that tenant's entries after the oldest position any of its
streams holds, once, and hands each entry to every stream that may see it. A replica that has
received no notification for a tenant with open streams reads it anyway every 2 seconds. A lost
notification — a listening connection that dropped and reconnected — therefore costs at most
those 2 seconds, never a change.

The signal sits behind a port of its own, with this PostgreSQL adapter as the default. A
cluster may supply another, a broker for example (ADR-0002, the event bus). Correctness never
depends on the signal: a stream advances only by reading the ledger.

### 3. Which records a reader receives
A reader receives a **change** for every ledger entry that records a change of state of a run, a
step or a decision request, within its scope, that it may see (§5). The kinds are those of the
run's and the step's state machine (`control-plane.md` §5.2) and of the decision request
(ADR-0042). The implementing change lists them in the contract (§4), and its test fails a kind
UC-6.10 names that reaches no stream: a step started, completed, failed or halted, a decision
awaited. An entry of any other kind — a budget statement, a report delivered, a removal verdict
— is not sent.

A change of state that writes no ledger entry is not a change on this path. The rule that every
state change is recorded with it is the control plane's, and this decision relies on it rather
than adding a second way.

### 4. The shape of a change
Three event types, defined as a versioned contract under `contracts/` by the change that builds
this decision:

- **`snapshot`** — the current state of the scope: every run the reader may see in it, with its
  state and the state of each step, and the process version each run belongs to. Its `id` is the
  position it was read at. It is read in one database transaction together with that position,
  so that it shows exactly the entries up to it and none after.
- **`change`** — one ledger entry, projected: the run, the step if there is one, the decision
  request if there is one, the entry's kind and outcome token, the method kind of the step, the
  moment it was recorded, and whether it belongs to a rehearsal (ADR-0030). Its `id` is the
  position of that entry.
- **a heartbeat** — a comment line every 15 seconds, so that an idle connection is not closed by
  a proxy in between, and a reader notices a dead one.

A change carries no content, no figure and no person. The ledger entry's `actor` and its
consumption are left out. Which state an entry's kind and outcome lead to is the run
component's, published beside its state machine, so that the stream and every representation
read it from one place. A figure that moved — what a run has consumed so far — is read again
from the component that owns it (ADR-0029). A result is read through the ordinary requests,
under their own rules.

**A position is the hash of the ledger entry**, not its sequence number. The sequence number
counts every entry of the tenant. A reader who saw only some of them could subtract two
positions and learn how many changes were withheld from them. The hash says nothing about its
neighbours. The replica finds the sequence number from the hash when a reader resumes.

### 5. Visibility per role holds on this path
Whether a reader may see a run is one predicate, owned by `reporting` (ADR-0029, UC-6.4). The
stream and every read of a representation use the same predicate. It is evaluated for each
change when the change is sent, against the reader's roles as they are then, not as they were
when the stream opened.

A change the reader may not see is absent. It is not replaced by a placeholder, and nothing in
the stream counts it: the positions are hashes (§4), the snapshot lists only visible runs, and
the heartbeat keeps its interval whatever happens unseen. A key that no longer proves an
identity ends the stream at the next change or heartbeat.

### 6. A reader resumes without missing a change
A reader that reconnects, to any replica, sends the position of the last event it received.
The replica answers in one of two ways:

1. it sends every change after that position, in the ledger's order, that the reader may see,
   and continues live;
2. when the position is unknown in the tenant, or more than 1,000 entries of the tenant lie
   behind it, it sends a fresh `snapshot` instead, and continues live from the snapshot's
   position.

A reader without a position receives a `snapshot` first. A representation therefore never
reads state separately before it subscribes, and no change can fall between the two. The order
of the ledger is the order of commit within a tenant (Context), so a change after a position is
never one that becomes visible later with a lower number.

A snapshot after a long absence replaces the changes in between; it does not replay them.
UC-6.10 §3 excludes the replay of past runs as motion, and the snapshot is the state the reader
would see on reloading.

Every replica reads the same database, so a reader needs no particular replica. A replica that
stops ends its streams, and its readers reconnect to another. The stream tells the reader to
wait 1 second before reconnecting.

### 7. How the 5 seconds are met
The time from the commit of an entry to its arrival at the reader is, on the path of §2:

| Part | Bound |
|---|---|
| notification from the commit to every listening replica | delivered on commit, by the database |
| read of the tenant's new entries, once per replica | one indexed read by sequence number |
| visibility check and hand-over to each stream | in memory, against roles read per batch |
| a lost notification | at most the 2 seconds of the read every replica makes anyway |

Notifications that arrive within 250 milliseconds of each other are read as one batch. The worst
case without failure is therefore the 2-second read, the batch and the network, inside 5 seconds
with room. The load on the database does not grow with the number of readers: one listening
connection and one read per tenant per batch for each replica, however many streams it holds.

The replica measures the time from an entry's recorded moment to its hand-over to each stream,
as a telemetry histogram, so that the figure is observed in operation and not only in a test.
The test that proves it opens a stream on one replica, records a change through another process
on the same database, and fails when the change arrives after 5 seconds. A second test drops the
notification and finds the change within the same bound.

Each replica holds a configurable maximum of open streams. A request beyond it is refused with
`503` and a `Retry-After` header, and the reader tries again, possibly on another replica.

## Alternatives
- **Each reader asks every 2 seconds.** It meets the figure. Its load grows with readers rather
  than with work, an idle system is asked as often as a busy one, and a reader away for a minute
  learns only the current state, not that it missed anything.
- **WebSocket.** A connection that runs both ways. Nothing needs to run from the reader to
  Taktus on this path, the format has no resumption by position of its own, and some proxies
  need configuration for it that plain HTTP does not.
- **Long polling**: one request per change, answered when something happens. It resumes by
  position as well, but opens a request for every change and loses the heartbeat.
- **A broker as a requirement.** It would carry the changes between replicas. ADR-0002 keeps
  PostgreSQL the only mandatory dependency, and the signal of §2 is a port a broker can fill
  where an operator has one.
- **Read the changes from the outbox.** The outbox is a work list for one consumer, marked
  published once acted on (ADR-0048). Readers are many, each at its own position, and only
  read. The ledger is already an ordered, permanent log of the same facts.
- **The sequence number as the position.** Simpler to resume from, and it would count, for every
  reader, the changes it may not see.
- **The notification carries the change.** The listener would then need nothing from the
  database. A notification has a size limit, it is lost when a connection drops, and it would be a
  second record beside the ledger.

## Consequences
- `GET /changes` joins the HTTP surface, and a versioned contract for the three event types
  arrives under `contracts/` with it.
- A migration adds the trigger that notifies on insert into `ledger_entry`, and an index from a
  ledger entry's hash to its sequence number within the tenant.
- `reporting` gains its visibility predicate before UC-6.4 is built; until then it holds the
  boundary that exists (§ *Where this promise ends*).
- The run component publishes which state each ledger kind and outcome lead to.
- The web app subscribes before it draws, and draws from the snapshot and the changes.
- The time from record to reader becomes a telemetry figure of every replica.

## Where this promise ends
The 5 seconds hold from the commit of an entry to its hand-over at the replica, and across a
network that delivers. A proxy that buffers a streamed response delays every change until its
buffer fills; turning that off is the operator's configuration, which the operating guide states
and Taktus cannot detect. Only a change recorded in the ledger is sent: a state change that some
path makes without an entry is missing from every stream, and the test covers the kinds UC-6.10
names, not every kind there is. Until UC-6.4 is built in `0.5.0`, the predicate of §5 knows no
roles: any identity of a tenant that holds an account key sees every run of that tenant, and the
stream is no narrower than the ordinary requests. An entitlement withdrawn takes effect from the
next change; what was sent before stays seen. Order holds within one tenant; a reader of two
tenants receives two orders and no order between them. The notification reaches only replicas
on the same database; an instance split across two databases is outside ADR-0020's rules, and
its streams see half. A reader away for more than 1,000 entries of its tenant receives the
current state, not what happened in between. Real time below the 5 seconds is not promised, and
nothing here draws: what the web app makes of a change is UC-6.10's and the visual vocabulary's
(#104). Channels other than the web app are not covered; how a chat receives the text
equivalent and a link is decided where the first such channel is built.
