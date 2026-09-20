# ADR-0027 — Taktus reaches itself through the connector port

**Status:** accepted

## Context
The removal test (ADR-0003) became a process Taktus runs for itself. A process that reads the
configuration of the instance it runs in, exercises other processes with an adapter withheld,
and writes to the catalog needs a way to reach the instance. CLAUDE.md §6 says that nothing
external is called directly, and ADR-0016 says that a component knows no class of another. A
step of the run component that called the composition root, or the catalog, directly would
have broken both rules at once — and would have made the first process Taktus operates for
itself the one process that does not follow the rules every other process follows.

## Decision

### 1. The loopback connector
An instance reaches itself the way it reaches everything else: through a capability, served by
a connector. The **loopback connector** (`src/taktus/adapters/driven/connectors/loopback/`)
sits in the pool the run engine resolves connectors from, under the adapter identifier
`connector.loopback`, and declares the capabilities `orchestrator.integrations`,
`orchestrator.removal` and `orchestrator.maturity`. A process names those capabilities and
nothing else; the bundle of the removal test is an ordinary bundle of `rule: connector` steps.

### 2. The adapter imports no component; the composition root binds it
The connector is a driven adapter and may not import a component (`.importlinter`). What it
needs from the instance is the `Orchestrator` protocol it defines — list the integrations,
describe one, exercise one, record a result — and the composition root implements that
protocol over the instance's own services (`composition/loopback.py`): the adapter pools, the
process version repository, the run engine and the catalog's recording use case. The
connector is created before the engine, because it is in the engine's pool, and bound to its
orchestrator after, because the orchestrator needs the engine.

### 3. Every operation is a read
The effect field of an operation says whether its effect leaves Taktus (ADR-0024 §3). A
rehearsal run inside the instance and a record in the catalog do not leave it, so every
operation of the loopback declares `read`, and no egress entry is written for them. A process
that reaches the outside still does so through the connector configured for that capability,
never through the loopback.

### 4. Taktus is not an integration of Taktus
The removal test lists what is configured and never lists `connector.loopback`: withholding
the instance from itself is not a test of anything. A process whose steps resolve to the
loopback is not exercised by the removal test either, for the same reason.

## Alternatives
- **A `rule: removal` built into the run component.** The run component would have to know
  the adapter pools' membership, the catalog's rules and the composition root's wiring — three
  boundaries crossed by one rule.
- **A driving adapter or a command line that runs the test.** A script that runs once. The
  owner's answer was a process that runs weekly, with its result in the ledger and the
  adapter's maturity, and a process is what the run engine runs.
- **Serving the capabilities over the HTTP surface from the start.** Right for an installation
  with several instances, where one instance tests another, and it needs a credential and a
  network path for what is, in the smallest installation, a call into the same process. The
  in-process loopback is the smallest installation's shape; the HTTP shape serves the same
  capabilities later and changes no bundle.

## Consequences
- `composition/loopback.py` is wiring, and the one place that holds the pools, the engine and
  the catalog at once; the verdict rules stay in the catalog component.
- The static pools gain `members()` and `without(adapter)`: the configuration can be read and
  a copy with one adapter withheld can be built; the original is never mutated.
- A missing adapter for a step ends the step failed and the run escalated, instead of an
  exception out of the engine: a rehearsal without an adapter must come to a boundary that can
  be compared.

## Where this promise ends
The loopback serves the instance it runs in and no other: in an installation with several
instances, an instance can test only itself until the capabilities are served over the HTTP
surface. Withholding is a rehearsal over pools with one adapter left out, not a change to the
configuration; an adapter that is reached by a process through some path other than the pools
— none exists today — would not be withheld. The `Orchestrator` is the composition root's, and
what it observes is as good as the pools' declarations: a worker that declares a capability it
cannot serve is listed as serving it.
