# `script` — the reference worker with no AI at all

A shell wrapper behind the worker contract v1. It runs shell commands as steps and reports what
the contract asks for: capabilities, an estimate, an event stream that resumes from any `seq`,
consumption after every step, a boundary with a checkpoint after every step, a stop that lands on
that boundary, refusal of tools outside the frame, rejection before starting when the limits do
not fit, artifacts, health.

It exists because of [ADR-0007](../../docs/adr/ADR-0007-worker-contract.md): a contract that a
shell script cannot satisfy is built around one specific coding agent. It is proof case 1 of the
contract ([README §8](../../contracts/worker/v1/README.md)), and the worker the conformance
suite is proven against ([CONFORMANCE.md](../../contracts/worker/v1/CONFORMANCE.md)).

One file, standard library only, nothing from `src/taktus`:

```
python3 workers/script/worker.py --port 9000
```

Two things talk to it from this repository, both through `uv run` because `taktusctl` lives in
the project environment: the conformance suite, `uv run taktusctl conformance run --contract
worker/v1 --endpoint http://localhost:9000`, and the control plane, `uv run taktusctl run
--process examples/processes/six-times-seven.yaml`, which hands this worker the `worker` steps
of a process bundle (`examples/README.md`).

## Two profiles

| `--profile` | Steps | Runtime | Consumption | Artifacts |
|---|---|---|---|---|
| `quick` (default) | `inspect`, `prepare`, `run`, `report` — one shell command each | about a second | `compute` seconds in `cpu.small` | `plan` after step 2, `result` after step 4 |
| `longrun` | `load`, `epoch-1` to `epoch-N`, `evaluate` | seconds, tunable | `compute` seconds in a resource class | a `model.checkpoint` after every epoch, `metrics` and a `model` file at the end |

**What `longrun` is, precisely.** It has the *shape* of the second proof case — a training job:
many steps, progress reported in epochs (`step.progress` with `current`, `total`, `unit`),
`compute` consumption with a resource class, a file artifact at the end, and a stop that lands on
an epoch boundary mid-run. It trains nothing. It holds no accelerator. The resource class it
reports is whatever `--resource-class` says (default `cpu.small`), and its epochs are `printf`
and a short sleep. It shows that the contract fits that shape; it is no evidence that training
works. The worker that trains, `mlbench`, arrives at `0.4.0` (`docs/roadmap.md`).

Tunables: `--step-seconds` (quick, default 0.3), `--epochs` (longrun, default 4),
`--epoch-seconds` (longrun, default 0.5), `--resource-class`, `--state-dir` for checkpoints
(default a fresh directory under `~/.cache/taktus-script-worker/`).

## What an assignment does

If `task.inputs.commands` is a list of strings, each becomes one step of kind `shell` with an
`output-N` log artifact. Otherwise the profile's steps run. Every step: `step.started`,
`tool.called` for `shell.script` with the command's sha256 as `arguments_digest`, the command,
any artifacts, `consumption.reported` with the measured seconds, a checkpoint on disk, and
`step.boundary` with its reference.

The frame is checked where the call happens, not before the assignment starts: a step whose tool
is outside `allowed_tools` or matches `forbidden` emits `tool.called` with `refused: true`, does
not run, reports its consumption and boundary, and the assignment ends `failed` with the reason.
This is what lets the suite observe the refusal (W-07). The limits are checked before the start:
an estimate above `limits.compute.seconds`, a missing compute limit, a foreign resource class, too
few `max_steps` or a deadline before the estimated end all give `finished` / `rejected` (W-10).

A stop request is honoured after the running step's boundary; the assignment ends `stopped` with
that boundary's `checkpoint_ref`. An assignment whose `context.checkpoint_ref` names a checkpoint
this worker wrote continues after it and does not produce the artifacts recorded there again.

Credentials arrive as names. The worker logs whether each is present in its environment and
nothing else. No value is ever written to an event, an artifact or the log.

## Fault injection

`--fault NAME` makes the worker violate exactly one conformance check, so that the suite can be
shown to fail where it should. `--list-faults` prints the table; the meta-test under
`tests/conformance/test_worker_v1_faults.py` runs every fault and asserts that the suite fails on
that check and only on that check.

| Fault | Breaks | What the worker does instead |
|---|---|---|
| `W-01` | W-01 | declares no consumption kind |
| `W-02` | W-02 | answers `501` to `POST /v1/estimate` |
| `W-03-gap` | W-03 | skips `seq` 2 |
| `W-03-resume` | W-03 | ignores `Last-Event-ID` and `?after=`; always replays from 1 |
| `W-04` | W-04 | reports every step's consumption at the end, just before `assignment.finished` |
| `W-05` | W-05 | never emits `step.boundary`, although it still writes checkpoints |
| `W-06` | W-06 | on a stop, skips the boundary of the running step and reports the previous checkpoint |
| `W-07` | W-07 | runs a tool outside the frame and reports it without `refused: true` |
| `W-08-event` | W-08 | writes the first credential's value into a `step.progress` message |
| `W-08-artifact` | W-08 | writes the first credential's value into an artifact |
| `W-08-log` | W-08 | writes the first credential's value to its log |
| `W-09` | W-09 | sends the command in clear as `arguments_digest` |
| `W-10` | W-10 | accepts an estimate above the limits and fails after the first step |
| `W-11` | W-11 | produces the artifacts from before a checkpoint again after resuming |

W-12, the removal test, has no fault: it is not something a worker does at runtime.

The three `W-08` faults are the only code paths in this repository that write a credential value
anywhere. They exist to be caught, and the meta-test proves that they are.

## Endpoints

Every endpoint of `contracts/worker/v1/openapi.yaml`, on `127.0.0.1` by default (`--host` to
change). Errors are RFC 9457 problem details. At most four assignments run at once; `GET
/v1/health` answers `not_ready` beyond that.
