# Examples

Worked examples that run against this repository as it is. Each is exercised by a test, so
that an example that stops working is a red gate, not a stale page.

| Example | Shows | Exercised by |
|---|---|---|
| [`processes/six-times-seven.yaml`](processes/six-times-seven.yaml) | the first control-plane slice end to end: a `rule` step, a `worker` step, a `wait` step, an `exact` step, and a step that admission control rejects before it starts | `tests/integration/test_first_slice.py`, `tests/exactness` |

## Running a process bundle

```bash
python3 workers/script/worker.py --port 9000 &
uv run taktusctl run --process examples/processes/six-times-seven.yaml
```

`taktusctl` lives in the project environment, hence `uv run`. With a database and the daemon
running (`uv run taktusd`, or `make up`), `uv run taktusctl submit --process …` queues the
bundle instead and prints the run's identifier; the daemon executes it, and
`GET /runs/{id}` shows where it got to. The command prints where the state
lives — the database named by `TAKTUS_DATABASE_URL`, or memory with a file snapshot, development
only — then the run, its steps, the ledger entries of the run with the result of verifying the
tenant's whole chain, the provenance of the run — one record per completed step — with the
result of verifying its chain, and the raw consumption against the budget. Exit code `0` means the run finished; `3` means it halted or
escalated, and the last line says how to resume; `2` means the bundle or the invocation is
wrong.

| Option | Meaning |
|---|---|
| `--resume RUN_ID` | continue a halted run at its step boundary. The bundle is read again: a changed `limits` block is a changed budget, which is how a run rejected by admission control is given more room. The steps a run executes are the ones it started with. A run still marked as running — its process was killed — is recovered: the step in flight goes back to its last persisted boundary and the run continues. |
| `--stop-after N` | request a stop after `N` steps have finished. The stop takes effect at the boundary; nothing is aborted. |
| `--worker URL` | the worker endpoint (default `http://127.0.0.1:9000`, or `TAKTUS_WORKER`) — for `TAKTUS_EXECUTION=endpoint`, the default. With `TAKTUS_EXECUTION=process` or `container` the command starts a unit per worker step instead, from the command line or image `TAKTUS_EXECUTION_UNIT` names (`.env.example`, `docs/architecture/contracts.md` §2.4); the bundle's `autonomy` decides whether `process` is allowed at all |
| `--state-dir PATH` | where artifact bytes are written, and — without a database — the snapshot of runs, plans and the ledger between invocations (default `~/.cache/taktus/taktusctl`, or `TAKTUS_STATE_DIR`). The snapshot is development only: the in-memory adapters, not a supported deployment. With `TAKTUS_DATABASE_URL` set the state lives in PostgreSQL (`README.md`, *Operating it*). |
| `--input NAME=VALUE` | one input of the run, repeatable; what `$input` references in the bundle resolve to. A value that reads as JSON is JSON (`--input issue=11` is a number, `--input labels='["taktus"]'` a list); anything else is text |
| `--identity LABEL` | the identity the command is attributed to and the run acts on behalf of — what every connector call carries. Default: the provisional operator identity configured for the tenant (`TAKTUS_PROVISIONAL_IDENTITY`, DEC-0013); with neither, nothing executes. The CLI channel authenticates nobody yet |
| `--tenant ID` | the tenant the run belongs to (default `default`, or `TAKTUS_TENANT`); until the identity component exists there is that one, created by the first migration. |

## The shape of a bundle

The process bundle format proper arrives at `0.3.0` (`docs/roadmap.md`, ADR-0011). Until then a
bundle is the process version of `docs/architecture/control-plane.md` §4, written as YAML, with
one addition per step. Every field of a step is the shared kernel's `Step`
(`contracts/shared/v1/Step.json`) — `id`, `method`, `reason`, `rejected`, `exactness`,
`fallback`, `model`, `requires`, `depends_on` — and the rules of that schema hold: a
result-producing step carries an exactness class, `wait` and `human` carry none, `llm` and
`worker` name a fallback, `ml` and `neural` pin a model, and `exact` admits `rule` and
`statistics` only. A bundle that breaks one of them is refused with every finding listed.

Top level:

| Field | Meaning |
|---|---|
| `id`, `version`, `name` | the process, its version, its name; the ledger refers to `id@version` |
| `autonomy` | the autonomy level the run and its worker assignments carry, 1 to 4 |
| `limits` | the run's budget: `currency`, `quota` and `compute` in the shape of the worker contract's `Limits` (`contracts/worker/v1`). Every worker step's estimate is admitted against what is left of it. |
| `triggers`, `slo`, `author`, `reason` | as in control-plane.md §4; recorded, not yet acted on |
| `steps` | the graph; edges are the `depends_on` lists. The graph is checked: acyclic, every dependency a step of the process, every step connected to the rest. |

`work` per step — what the step does when it runs. Four method kinds are executable in this
version; every other method is refused before the run starts.

| Method | `work` | What happens |
|---|---|---|
| `rule` | `rule: constant` with `value` | the result is the value |
| `rule` | `rule: verify_artifact` with `step`, `artifact`, optional `pattern` | the result is the text of the named artifact of an earlier step, after its bytes are checked against the digest its producer announced and against the pattern. If either check fails, nothing leaves the step and the run escalates. This is the `exact` pattern of ADR-0014: a worker proposes, a rule produces the value. |
| `rule` | `rule: check` with `conditions`, each `value` and one or more of `equals`, `matches`, `not_matches` | the result is the checked values, once every condition holds over its resolved value — a pipeline's state equals `success`, an issue's body does not match a pattern. A value that is not a string is matched as its JSON text. A condition that does not hold escalates the run, naming the condition. The verdict comes from the values, never from a judgement: admissible for `exact` |
| `rule` | `rule: template` with `text` and `values` | the result is the text with every `${name}` replaced by the named value (a value that is not a string as its JSON text); a name without a value escalates |
| `rule` | `rule: connector` with `operation`, `input`, `credentials` | the operation is called on the connector that declares its capability — every segment of the name but the last — with a call context the run builds: the run's identity, the step, the attempt and the idempotency key `taktus:<run id>:<step id>:<attempt>`, and the credentials by name (the connector's runtime holds the values). The result is what came back: `{output, effect, consumption}` of `contracts/connector/v1` §5. An effect the connector reports as `write` or `delivery` is written to the ledger as `egress.write` or `egress.delivery` beside `step.finished` (ADR-0022): the result has left the system. A classified failure escalates the run with the connector's cause; a resume retries with the same key when the connector said the failure was retryable, with a new attempt otherwise. An operation declared `idempotency: none` is never repeated by the run on its own — a failure with effect `unknown` escalates, and the reason says that resuming repeats the call, so that a person checks the target first (ADR-0024) |
| `wait` | `seconds` | the run waits through the clock port |
| `wait` | `until` with `operation`, `input`, `credentials`, `select`, `expect`, optional `poll_seconds` (30) and `timeout_seconds` (1800) | the run reads the operation — a read, never a write — every `poll_seconds` until the part of its output that `select` names is one of `expect`; past the timeout the step fails and the run escalates. A wait produces no result (ADR-0018); what the polls consumed is counted |
| `worker` | `task` (`goal`, `acceptance`, `inputs`), optional `max_steps`, `allowed_hosts`, `workspace`, `credentials` | the task goes to a worker that offers every capability in `requires`, in a frame of exactly those capabilities and exactly the hosts in `allowed_hosts` (none, by default), with what is left of the budget as its limits; `credentials` name — never hold — what the assignment references, and the execution adapter (or whoever runs an endpoint worker) supplies the values (`CREDENTIALS.md`) |
| `llm` | `purpose`, `prompt`, optional `system`, `values`, `max_output_tokens`, `pattern` | the prompt, with every `${name}` replaced from `values`, goes to the model configured for the purpose (`TAKTUS_MODEL_*`); the result is the text it answered, once it matches `pattern` — the check that keeps a `sourced` step from passing on an answer beside the point |

**References** inside the untyped parts of a step's work — a task's `inputs`, a connector call's
`input`, the `values` of a template, a prompt or a check's conditions, a wait's `input`:

| Reference | Replaced by |
|---|---|
| `{ $from: <step-id> }` | that step's result — the value a rule produced, the text an llm step produced, `{output, effect, consumption}` for a connector call, or `{artifacts: [...]}` for a worker step |
| `{ $from: <step-id>, $select: output.number }` | one part of it, by a dotted path over keys and list positions |
| `{ $from: <step-id>, $artifact: <artifact-id> }` | the content of that artifact: parsed when its media type is JSON, text otherwise |
| `{ $input: <name> }` | one of the run's inputs, given as `taktusctl run --input name=value` (a value that reads as JSON is JSON: `--input issue=11` is the number 11); `$select` applies here too |

A `$from` names a step that is a dependency, directly or through others. `$input` references are
resolved when the run is created and may therefore stand in typed places too — a workspace
location, an allowed host, a credential name. What a step read through a reference is recorded
in its provenance (ADR-0021); a read through a connector is recorded as an external source
with the moment and the digest of what it answered.

What every run does around every step, whatever the method, is stated in
`src/taktus/components/run/__init__.py` and ADR-0005.
