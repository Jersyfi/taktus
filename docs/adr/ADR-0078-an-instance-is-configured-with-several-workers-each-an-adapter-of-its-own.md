# ADR-0078 — An instance is configured with several workers, each an adapter of its own

**Status:** accepted · builds issue #209 (roadmap `0.4.0`)

## Context
A worker step is resolved by capability. The worker pool holds a list of workers, and the first
whose declared capabilities cover what the step requires serves it. The pool could always hold
several workers. The instance's configuration could name only one: `TAKTUS_EXECUTION` said how it
is reached, `TAKTUS_WORKER` or `TAKTUS_EXECUTION_UNIT` said where, and its adapter identifier was
`worker.<kind>`.

Since #154 a second coding worker exists. With both coding workers in one pool, the removal test
withholds one, and the other serves the coding step: the verdict is *changed* through an adapter,
not through a person (DEC-0111). On an instance this could not happen, because an instance read
one worker.

Two further facts shaped the decision. A credential reaches a launched unit under the name the
assignment carries, read from `credential.<name>` (CREDENTIALS.md). Two coding workers read the
same name, `CODING_AGENT_API_KEY`, but each needs the key of its own agent. And the removal test
exercised an integration only on the steps it serves first. A worker configured behind another
that covers the same capabilities serves nothing first, so its verdict was *untested*.

## Decision

### 1. `TAKTUS_WORKERS` names the workers, in the order a step is resolved in
The setting is a comma-separated list of names. A name is lowercase letters and digits, words
joined by hyphens, at most 40 characters. Each worker is the adapter `worker.<name>`. The order
is the pool's order: the first worker whose declared capabilities cover what a step requires
serves it.

An instance that sets no `TAKTUS_WORKERS` reads its one worker as before. Its identifier stays
`worker.<kind>`, and nothing about it changes.

### 2. A worker reads its own settings first, and the instance's where it sets none
Each named worker reads every execution setting under its own prefix: the key `k` is read as
`worker.<name>.k`, the variable `TAKTUS_WORKER_<NAME>_K`. A hyphen in the name is an underscore in
the variable, and a name holds no underscore, so two names never share a variable. Where the
worker sets nothing, the instance's own setting applies. So the execution namespace, the egress
image and the default limits are set once, and each worker sets what differs: its kind, its unit,
its memory.

Two settings have no such default:

- **The endpoint**, `TAKTUS_WORKER_<NAME>_ENDPOINT`. Two workers at one endpoint are one worker.
  A named worker of kind `endpoint` without its own endpoint is refused at startup.
- **Every credential**, `TAKTUS_WORKER_<NAME>_CREDENTIAL_<CREDENTIAL>_FILE`. A named worker
  receives only its own credentials. Two workers that reference the same credential name each
  receive the value configured for that worker. Neither sees the other's, and neither sees a
  value configured for the instance under `TAKTUS_CREDENTIAL_<CREDENTIAL>_FILE`.

The execution adapter of each worker is given the configuration as that worker reads it. It
resolves credentials there, so no adapter changes. A launched unit is named after its worker,
so the state and the logs of two launched workers stay apart.

### 3. Each worker is an adapter of its own
Each worker is withheld by the removal test on its own, and its verdict is recorded under its
identifier. Each earns the conformance half on its own: `taktusctl conformance record
worker.<name>` runs the suite against that worker, with the suite settings and the credential as
that worker reads them (ADR-0044). The maturity of one says nothing about the other.

### 4. The removal test puts the withheld integration first in its baseline
The removal test now resolves an integration's steps, and runs its baseline, with that
integration moved to the front of its pool. The withheld run is unchanged: the same pool without
the integration. An integration that already served first is tested exactly as before. One that
stands behind another adapter is exercised on every step it can serve, and the adapter in front
of it is its alternative.

Without this, the second of two coding workers would always read *untested*. Its removal half
could never pass, and so it could never become *verified*, although it serves the same steps the
first serves.

### 5. Admission asks for the largest memory among the launched units
Admission against the platform asks how much memory a worker step's unit takes. It does not yet
know which worker will serve the step. It therefore asks for the largest limit among the workers
this platform launches. A worker reached by endpoint or run as a Job in the cluster takes no
memory of this platform, as before.

### 6. The chart carries the same configuration
`execution.workers[]` in the chart names the workers, each with what it sets itself, and renders
`TAKTUS_WORKERS` and the per-worker variables. A credential of one worker is listed under
`credentials[]` with the parameter `worker.<worker>.credential.<name>`. The chart refuses a name
the instance would refuse, a name twice, and a worker of kind `endpoint` without its endpoint.

## Alternatives
- **One JSON document describing every worker.** One variable would carry everything, but a
  credential's file would have to be named inside it, unlike every other secret. The chart and
  `.env.example` would also need a second way of writing a setting.
- **A named worker falls back to the instance's credentials.** It would be convenient: a
  repository token both workers use would be configured once. It would also hand a worker a value
  meant for another whenever an operator forgets a worker-specific one. That is what the issue
  forbids. Strict in substance wins (DEC-0040): the operator points two variables at one file.
- **Name workers by kind, `worker.cluster-1`.** The identifier would carry no meaning, and
  reordering the workers would change which maturity record a worker reads.
- **Leave the removal test as it was, and let the operator reorder the workers to test the
  second.** The weekly test runs on the configuration as it is. A verdict that needs the
  configuration changed by hand is not the automatic test CLAUDE.md §6 requires.

## Consequences
- Settings `TAKTUS_WORKERS` and `TAKTUS_WORKER_<NAME>_…`; `.env.example`, `CREDENTIALS.md` and the
  chart name them.
- `composition/settings.py` gains `WorkerSettings`, `WorkerConfiguration` and `load_workers`;
  `Settings.execution` becomes `Settings.workers`. `composition/execution.py` opens every worker,
  `composition/conformance.py` runs the suite per worker.
- The three pools gain `first`, and `Pools.first` moves an integration to the front.
- `tests/integration/test_two_coding_workers.py` proves S-01 on an instance configured with both
  coding workers. `tests/conformance/test_taktusctl.py` proves a conformance half per worker.
  `tests/integration/test_launched_process.py` proves that each launched worker receives only its
  own credential.

## Where this promise ends
A worker is chosen by order and capability, never by cost or quality: model routing is its own
roadmap item. Admission does not know which worker will serve a step, so it reserves the largest
memory among the launched units. The `--worker` option of `taktusctl` overrides the endpoint of
the unnamed worker only; it does nothing to a named one. Workers share the instance's execution
namespace and egress proxy image, and they share `execution.stateClaim` unless a worker names an
existing claim of its own; the chart renders no claim per worker. The removal test's baseline is
a rehearsal with the integration first, not the order the instance runs in. A verdict of
*changed* for a worker that stands behind another says that the steps it can serve keep running
without it, not that it serves them today. Nothing here deploys a second worker on Taktus's own
instance: that needs the second coding worker's image (#208) and a release.
