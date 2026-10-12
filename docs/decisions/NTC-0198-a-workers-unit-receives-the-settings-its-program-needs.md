# NTC-0198 — A worker's unit receives the settings its program needs

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-12
**Raised in:** the pull request for issue #288

## 1. What was decided

A launched worker is one whose execution unit the control plane starts per job, as a process,
a container or a Job in a cluster. Its unit now receives the variables the operator configures
for it, beside the launch convention's. ADR-0090 is the decision; this notice records the
change of behaviour.

1. **The setting** is `TAKTUS_EXECUTION_UNIT_ENV`: `NAME=value` pairs, separated by commas.
   A named worker sets its own as `TAKTUS_WORKER_<NAME>_EXECUTION_UNIT_ENV`. In the chart it is
   the map `execution.defaults.unitEnv`, and `unitEnv` per worker.
2. **Every unit of the worker receives them**: an assignment's, a probe's and the conformance
   suite's. Before, a unit received the launch convention, the proxy and its credentials
   alone.
3. **A name that carries a secret is refused** at the start: the `TAKTUS_` namespace, a name
   ending in `_FILE`, a name the adapter sets itself, a name with the word `PASSWORD`,
   `PASSWD`, `SECRET`, `TOKEN` or `KEY`, and a credential the configuration supplies. A job
   that names a credential under a configured variable's name is refused at launch.
4. **The configuration a maturity record names** states the variables' names in a field
   `environment`, never their values. It is absent where a worker names none.

With the setting unset, which is the default, every unit receives exactly what it received
before.

## 2. The evidence

- The installed instance, 2026-10-12: the coding worker on the cluster kind exited with code 2
  before it was ready, because nothing gave it `CODING_AGENT_AUTH`. Issue #288 states it.
- `workers/claudecode/worker.py` `main()` refuses to start without `--auth` or
  `CODING_AGENT_AUTH`; `workers/codex/worker.py` does the same.
- `tests/composition/test_unit_environment.py` holds points 1 to 4, and starts the coding worker
  launched through the `process` adapter with its fake agent: with the variable it answers, and
  without it the unit exits with the worker's own message.
- `tests/adapters/execution/test_process.py`, `test_container.py` and `test_kubernetes.py` hold
  each adapter to passing the variables; `tests/governance/test_chart.py` the chart.

## 3. What was considered

- **A probe without the variables**, as a probe has no service hosts (ADR-0089 §2). Not taken:
  a coding worker that cannot start cannot answer `capabilities`, and these variables grant no
  reach and no secret.
- **The narrower refusal the issue's brief listed**, without the words that mark a secret. Not
  taken: `ANTHROPIC_API_KEY` would then pass, and its value would stand in the ConfigMap and in
  every pod's description.
- **The values in the recorded configuration.** Not taken: a record is never changed, and a
  value set by mistake would outlive its correction there.
- **The alternatives to the design itself** are in ADR-0090.

## 4. Which entry permits it

M2.4 of `docs/decisions/anchors.taktus.md`: "A change of what the software does, made inside an
agreed scope, that breaks no contract, moves no limit or autonomy level and says nothing
public." The scope is issue #288. No contract changes: the worker contract does not know how
its unit was started, and the execution port is internal. No limit moves: a unit's variables
grant no host, no credential and no resource, and the default adds none. Nothing public is
said.
