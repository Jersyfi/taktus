# ADR-0090 — A launched worker's unit receives the settings its program needs, as the operator configures them

**Status:** accepted · builds issue #288 (roadmap `0.2.0`); extends ADR-0078 by one setting per
worker, beside ADR-0089's

## Context
An execution adapter starts a launched worker's unit with the image's command and with a fixed
set of variables. These are the launch convention's (`TAKTUS_UNIT_PORT`,
`TAKTUS_UNIT_STATE_DIR`), what a program needs to run on the machine (`HOME`, `TMPDIR`), the
egress proxy's, and the credentials the job names. Nothing else reaches the unit.

The coding worker refuses to start without its authentication mode, `--auth` or
`CODING_AGENT_AUTH`: an API key or a session. It assumes neither, deliberately, because the two
are billed differently and fail differently. On the workstation `tools/first_run.sh` passes
`--auth`. On the installed instance, on 2026-10-12, nothing could: the unit exited with code 2
before it was ready. The worker conformance suite's unit and every P-03 `implement` step failed
before the worker had answered once.

The mode could be baked into the image. Then one image would serve one mode, and changing from
an API key to a session would mean another image. The mode could be a flag on the image's
command line. The execution port has no command line for an image, and the chart names images,
not commands. The mode is configuration of the worker as the operator runs it, as its service
hosts are (ADR-0089).

## Decision

### 1. The operator names the variables a worker's unit receives, as configuration
`TAKTUS_EXECUTION_UNIT_ENV` holds `NAME=value` pairs, separated by commas. A named worker sets
its own as `TAKTUS_WORKER_<NAME>_EXECUTION_UNIT_ENV` and otherwise reads the instance's, as every
execution setting is read (ADR-0078 §2). A worker's own list replaces the instance's; the two
are not merged. A value may hold `=`; it may not hold a comma. Unset or empty, there is none.
The startup log names every pair, values included. The chart renders the setting from the map
`execution.defaults.unitEnv` and from `unitEnv` of an entry of `execution.workers[]`, where an
empty map is that worker's own *none*. A value with a comma fails the render.

### 2. They are configuration and never a secret
A secret reaches a unit as a credential the job names, read from a file at launch and never
written to configuration (`CREDENTIALS.md`). The unit's variables are configuration: they stand
in the ConfigMap, in the startup log and in the unit's pod. So a name that would carry a secret
there is refused at the start, with one sentence naming the setting:

- a name in the `TAKTUS_` namespace, which the launch convention and the credentials' files
  own;
- a name ending in `_FILE`, the shape of a secret's carrier;
- a name an execution adapter sets itself: `PATH`, `HOME`, `TMPDIR`, `LANG`, `LC_ALL`, `USER`,
  `SHELL`, and the proxy variables `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`, `ALL_PROXY` in
  either case;
- a name one of whose underscore-separated words is `PASSWORD`, `PASSWD`, `SECRET`, `TOKEN` or
  `KEY` — `VCS_TOKEN`, `CODING_AGENT_API_KEY`;
- a name under which this configuration supplies a credential, for a named worker its own: a
  credential's name need not give it away, as `CODING_AGENT_SESSION` does not.

The rule lives in the execution port (`variable_refusal`), so that a unit built without the
settings carries no such name either. At launch, a job that names a credential under one of the
unit's variables is refused before anything starts: a variable is either configuration or a
credential, and the adapter does not pick one silently.

### 3. Every unit of the worker receives them
`ExecutionUnit.environment` carries the pairs. The `process`, `container` and `cluster` adapters
give them to every unit they start: an assignment's, a probe's and the conformance suite's.
Unlike service hosts (ADR-0089 §2), a probe receives them too. A probe that cannot start cannot
answer `capabilities`, and these variables grant no reach and no secret. The cluster adapter
writes them as plain values in the pod, beside the launch convention's; nothing of them enters
the job's Secret.

### 4. A record names the variables, not their values
The configuration a conformance pass or a removal verdict names (`Pools.configuration`,
ADR-0044 §2) states the names of a launched worker's unit variables in a field `environment`. A
worker that names none has no such field, so that a configuration recorded before this decision
compares equal to the same configuration now. A worker whose names change is another
configuration, and its standing is measured again (ADR-0044 §4). The values are left out. A
ledger entry is never changed, and the record it names is kept by digest. A value an operator set by mistake, a
secret the refusal of §2 did not recognise, must not outlive its correction there. A worker
reached by endpoint records none: its environment is whoever runs it.

## Alternatives
- **Bake the mode into the image.** Nothing to configure. One image per mode, and a change of
  mode is a new image and a new release.
- **A command line per worker for an image.** It would let the operator pass `--auth` as on the
  workstation. The port has no command line for an image, the chart names images, and every
  worker that takes a flag also reads a variable.
- **Pass the control plane's own environment through.** No setting at all. The control plane's
  environment holds the paths to its own secrets, which is why the `process` adapter passes
  only what a program needs (`INHERITED`).
- **Refuse only the names the issue listed** (`_FILE`, `TAKTUS_CREDENTIAL…`, a configured
  credential, the convention's and the proxy's). Fewer refusals. A name such as
  `ANTHROPIC_API_KEY` would then pass, and its value would stand in a ConfigMap and in every
  pod's description. Where two options are both consistent with the sources, the strict one in
  substance is taken (`CLAUDE.md` §8).
- **Record the values in the configuration a record names.** A record would state exactly what
  the worker ran with. A value set by mistake would stay in a record nobody may change.

## Consequences
- `ports/execution.py`: `ExecutionUnit.environment`, `variable_refusal` and `unit_environment`.
  The three execution adapters pass the variables; each refuses a clash with a credential before
  starting anything.
- `composition/settings.py`: the setting, its refusals and its line in the startup log.
  `composition/execution.py`: the unit carries it, and `unit_environments` names it by adapter
  identifier, which the worker pool keeps and `Pools.configuration` records. The catalog's
  `Configuration` gains the optional `environment`.
- The chart: `execution.defaults.unitEnv` and `workers[].unitEnv`, rendered into the ConfigMap.
  `deploy/k8s/README.md` §2 and §7, `.env.example`, `docs/architecture/contracts.md` §2.4,
  `docs/architecture/project-structure.md`, the two coding workers' READMEs.
- No contract changes: the worker contract does not know how its unit was started. No
  migration: the new field of `Configuration` is optional.

## Where this promise ends
The refusal reads a name, never a value. A secret given under a name no rule of §2 recognises
reaches the ConfigMap, the startup log and the pod, and nothing here stops it; the operator
answers for what a value holds, and the documentation says so wherever the setting is named.
The list of words is not a scanner. It catches the common shapes and nothing more. The variables
reach the unit's program; whether the program passes them to anything it starts — an agent, a
tool — is the program's own. On the `endpoint` kind nothing is started, so the setting changes
nothing there. A value holds no comma, and none holds a NUL character. The configuration a
record names states the names as configured, not the values, so two configurations with the same
names and other values compare equal.
