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

`taktusctl` lives in the project environment, hence `uv run`. The command prints the run, its
steps, the ledger entries of the run with the result of verifying the whole chain, and the raw
consumption against the budget. Exit code `0` means the run finished; `3` means it halted or
escalated, and the last line says how to resume; `2` means the bundle or the invocation is
wrong.

| Option | Meaning |
|---|---|
| `--resume RUN_ID` | continue a halted run at its step boundary. The bundle is read again: a changed `limits` block is a changed budget, which is how a run rejected by admission control is given more room. The steps a run executes are the ones it started with. |
| `--stop-after N` | request a stop after `N` steps have finished. The stop takes effect at the boundary; nothing is aborted. |
| `--worker URL` | the worker endpoint (default `http://127.0.0.1:9000`, or `TAKTUS_WORKER`) |
| `--state-dir PATH` | where runs, plans, the ledger and artifact bytes are written between invocations (default `~/.cache/taktus/taktusctl`, or `TAKTUS_STATE_DIR`). Development only: these are the in-memory adapters with a file snapshot, not a supported deployment. |
| `--identity LABEL` | the identity the command is attributed to. The CLI channel authenticates nobody yet. |

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

`work` per step — what the step does when it runs. Three method kinds are executable in this
version; every other method is refused before the run starts.

| Method | `work` | What happens |
|---|---|---|
| `rule` | `rule: constant` with `value` | the result is the value |
| `rule` | `rule: verify_artifact` with `step`, `artifact`, optional `pattern` | the result is the text of the named artifact of an earlier step, after its bytes are checked against the digest its producer announced and against the pattern. If either check fails, nothing leaves the step and the run escalates. This is the `exact` pattern of ADR-0014: a worker proposes, a rule produces the value. |
| `wait` | `seconds` | the run waits through the clock port |
| `worker` | `task` (`goal`, `acceptance`, `inputs`), optional `max_steps`, `forbidden`, `workspace` | the task goes to a worker that offers every capability in `requires`, in a frame of exactly those capabilities, with what is left of the budget as its limits |

Inside `inputs`, the object `{ $from: <step-id> }` is replaced by that step's result — the
value a rule produced, or `{artifacts: [...]}` for a worker step. The named step must be a
dependency, directly or through others.

What every run does around every step, whatever the method, is stated in
`src/taktus/components/run/__init__.py` and ADR-0005.
