# ADR-0138 — A stop can be scoped to an adapter, and is confirmed once it holds

**Status:** accepted · extends ADR-0005 (the stop at the step boundary), ADR-0023 (a stop is decided by a rule or a person, never by a probability) and ADR-0128 §2 (a runner reads what is asked of its run at every renewal) · issue #436, UC-7.2

## Context

UC-7.2 asks for an emergency stop. A stop takes effect at the next step boundary of every
affected run, never in the middle of a step. Until now a stop reached one run, by its
identifier, in the process that executed it.

The second tenant runs agents in support and development (DEC-0199). Its catalogue asks for "a
stop per agent and global, with confirmation" (UC-03 B-11.04, §7 row 6). In Taktus an agent
acts through an **adapter**: a worker, a connector or a model, named by the pool, never by a
product (CLAUDE.md §6). An agent that misbehaves is stopped by stopping its adapter. Its runs may
belong to many processes.

Two words are used below. A stop **holds** once no run of the tenant is still inside a step on
the adapter. Its **confirmation** is the record that it holds, naming the runs it halted.

Three things already exist. A runner executes a run under a claim it renews (the *lease*), and
reads what is asked of the run at every renewal (ADR-0128 §2). The engine asks a running worker
to stop, and the worker stops at its next inner boundary with a checkpoint (ADR-0005). The
elected scheduler ticks once a minute (ADR-0035).

## Decision

### 1. A stop of an adapter is a record of the tenant

A person requests a stop of one adapter. The request names no reason (UC-7.2). The adapter must
be a worker the instance has configured; any other name is refused, because no step would halt
at it (see where this promise ends). The request writes, in one transaction:

- the stop: the adapter, who requested it, when, and its state `holding`;
- `stop.requested`, with the person as actor and the adapter.

The entry is written first. It takes the tenant's ledger lock, and the stops are read under it.
A stop of the same adapter that is held already is returned instead, and nothing is written. A
tenant thus holds at most one stop per adapter.

The record lives in the table `adapter_stop` (migration 0072). It belongs to the run component.
No runner writes it.

### 2. Runners apply it at the step boundary

A held stop reaches a step in one of two places.

- **Before the handover.** A step is not handed to a stopped adapter. It stops at the boundary
  it was admitted from, keeps the checkpoint it had, and names the adapter. Its run halts with
  cause `stop`.
- **Inside the step.** A runner reads the tenant's held stops with every renewal of its lease.
  A run inside a step on a stopped adapter is asked to stop, as ADR-0005 asks. The worker
  stops at its next inner boundary and returns its checkpoint. A running step is never aborted.
  The run halts with cause `stop`.

A step on any other adapter runs as before. So does every run that does not reach the stopped
adapter.

A run halted by a stop is ended for its runner: the job is completed, not released. Releasing
it would let the next runner claim it and halt it again. A person resumes it, as every halted
run (UC-7.2 §3).

### 3. A stop is confirmed once it holds

A stop holds when no run of the tenant is in state `running` with a step admitted or running on
the adapter. The check reads the tenant's running runs.

The elected scheduler checks every holding stop on every tick. The surface that requested the
stop checks it while it waits. The first check that finds the stop holding confirms it, in one
transaction:

- the stop moves to `confirmed`, with the runs it halted;
- `stop.confirmed` names the requester as actor and the adapter. Its outcome is `held`, or
  `empty` for a stop that found no run. Its content digest names a document with the stop, the
  requester and the runs.

The runs it halted are read from the runs themselves. A run counts when it is halted with cause
`stop` and its step on the adapter stopped at or after the request. The entry is written first,
and the stop is read again under the ledger lock. A second confirmation meanwhile is rolled
back, so the confirmation is recorded once.

A confirmed stop still holds. No step is handed to the adapter until a person lifts it.

### 4. The requester reads the confirmation where they asked

`taktusctl stop adapter NAME` requests the stop. It waits up to `--wait` seconds, a minute by
default, and prints the stop. Once confirmed, the stop names the runs it halted. Before that,
it names the runs still inside a step on the adapter. `taktusctl stop show ID` prints it again.

### 5. A person lifts a stop

`taktusctl stop lift ID` moves a held stop to `lifted` and records `stop.lifted`, by the
person. Steps are handed to the adapter again. Lifting resumes no run: each run the stop halted
waits for a person (UC-7.2 §3).

### 6. Every decision here is a rule

A stop is a person's act. Whether it holds, and which runs it halted, are equality checks over
recorded states and times. Nothing here is estimated (ADR-0023).

## Alternatives

- **A stop flag on each run.** Rejected: a run is written by its runner alone. A flag written
  beside it is lost to the runner's next write (ADR-0128, Alternatives).
- **The adapter removed from the configuration.** Rejected: that takes a restart of every
  instance, fails every step that needs the adapter instead of halting it, and leaves no record
  of who stopped what.
- **The runners write the stopped runs into the stop.** Rejected: several runners would write
  one record at once. Reading the runs gives the same list without a shared write.
- **The confirmation pushed into a chat.** Not now: a person's channel is the owner-facing
  channel's, and a role's channel is not built (#85). The record and the ledger entry carry
  everything a push would.

## Consequences

- The run's domain model `AdapterStop`, its application service `Stops`, and the engine's
  `stops_held`, which the runner calls at every renewal.
- Migration 0072 adds the table `adapter_stop`.
- The scheduler's tick in `composition/stops.py`.
- The ledger kinds `stop.requested`, `stop.confirmed` and `stop.lifted`.
- `taktusctl stop adapter`, `show`, `list` and `lift`.

## Where this promise ends

It covers worker adapters. A step is handed to a worker at one place, and that is where the
stop is applied. A connector is called, and a model is asked, from inside a step, possibly
several times. A stop of a connector or a model adapter is refused, so that no confirmation
claims a stop that halts nothing. Halting at those calls is #621. The workers a stop
may name are those the requesting instance has configured.

A step inside a stopped worker is asked to stop at the runner's next renewal, twenty seconds by
default. It ends at the worker's next inner boundary, or at the step's ceiling for a worker that
signals none. A run executed in the process that started it, with no runner, is stopped only
before its next handover.

The confirmation is computed from runs in state `running`. A run whose instance died inside the
step counts once a runner recovers it. Until then, the stop is not confirmed. The list of
stopped runs counts runs halted with cause `stop` at the adapter after the request. A run
halted there by a person's stop of the run itself in that time is named as well.

The confirmation is read where the stop was requested, and in the ledger. It is not delivered
into a chat or a mail. A stop asked over the HTTP surface, the web app, chat or MCP is not
offered yet. A stop of a process, a tenant or every adapter at once is not built here.
