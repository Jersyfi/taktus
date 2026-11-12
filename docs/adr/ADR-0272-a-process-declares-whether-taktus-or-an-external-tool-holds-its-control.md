# ADR-0272 — A process declares whether Taktus or an external tool holds its control

**Status:** accepted · extends ADR-0011, ADR-0024, ADR-0005 · UC-5.2 · DEC-0228

## Context

UC-5.2 requires that an organisation decides per process where its control sits. Coupled:
Taktus decides the order and the timing of the steps. Decoupled: a workflow in an external tool
decides what happens next, and Taktus takes the task, does it and writes the result back. A
process version declares which; the same steps give the same results, ledger entries and
provenance in either mode; in the decoupled mode the external tool's state is the authority, and
a task the tool withdraws is not continued past the next step boundary. A move between the modes
is a new version. The tool is named by its capability, never by product.

P-02 and P-03 of the dev-orchestration blueprint work decoupled by hand — the issue tracker holds
the state — and no version said so.

## Decision

### 1. The declaration

A bundle's `control` is `coupled`, the default, or
`{mode: decoupled, task: {operation, input, select, withdrawn}}`: the `read` operation that
answers the task's state, by capability; its input, fixed or `{$input: <name>}` of the run; the
dotted path to the state in the answer; and the states that mean the tool withdrew the task.
Registration refuses a decoupled version without `task`, a coupled one with it, and a task input
the version does not declare. The declaration is part of the version, so a move between the modes
is a new version: the history stays, and a run keeps the version it started with.

### 2. The boundary asks the authority

The engine asks its port `ExternalControl` at every step boundary, before the next step is
admitted. The composition's `TaskControl` reads the run's version; for a decoupled one it reads
the task's state through the connector configured for the capability, as a read. A state listed
under `withdrawn` stops the run at that boundary: the ledger records `control.withdrawn`, and the
run is halted with cause `stop` and the reason in words. No running step is aborted (ADR-0005).
A coupled version is never read, and a rehearsal acts on nothing outside.

### 3. Everything else is the same

The engine runs the steps of a decoupled version as it runs any: admission against the budget,
anchors, the ledger, provenance, takeover instructions and the removal test apply unchanged.
What differs is how a run starts — a trigger or an event from the tool — and where its state is
reported, which the steps do through connectors.

## Alternatives

- **The tool's state copied into Taktus by a synchronisation.** UC-5.2 forbids a general
  synchronisation; the boundary reads only what decides whether to go on.
- **A withdrawn task ends the run as failed.** Nothing failed; the authority withdrew it, and a
  person may resume it once the tool gives it back.

## Consequences

- `control` is a new bundle field and a column of `process_version` (migration `0104`);
  `control.withdrawn` is a new ledger kind; the engine takes the port `ExternalControl`.

## Where this promise ends

- **A tool that cannot be read withdraws nothing.** The run goes on, and the failed read is
  logged; the next boundary asks again.
- **The read is not in the ledger.** The task's state read at a boundary leaves no entry unless
  it stops the run.
- **Which tools can hold control** depends on the connectors that read a task's state; this
  decision requires only that any read can.
