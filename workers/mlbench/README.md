# `mlbench` — the ML bench

A worker that trains, evaluates and serves classical models behind the worker contract v1. It is
the second proof case of the contract ([ADR-0007](../../docs/adr/ADR-0007-worker-contract.md)):
progress measured in epochs rather than tool calls, compute held in a resource class, the result
a model artifact with metrics. It is where a step's own model is made once a language model has
produced enough labelled data for it ([ADR-0004](../../docs/adr/ADR-0004-method-selection.md),
`docs/architecture/methods.md` §3).

```
python3 workers/mlbench/worker.py --port 9020
```

Two files and no import from `src/taktus`: `worker.py` is the contract, `bench.py` the machine
learning. It needs the libraries `requirements.txt` pins; in this repository they are the extra
`mlbench` of `pyproject.toml`, at the same versions, which `make install` installs. Its own image
is `Dockerfile` in this directory, built from the repository root.

The libraries are a provisional answer: which library the bench trains with is the owner's
decision, asked as DEC-0161 and built on its recommended option until it is answered.

## Three operations

`task.inputs.operation` names one. Every assignment begins with the step `load`, which reads what
the task names; each read is one `tool.called`, held against the frame where it happens.

| Operation | Steps | Artifacts |
|---|---|---|
| `train` (default) | `load`, `epoch-1` to `epoch-N`, `evaluate` | `checkpoint-K` (`model.checkpoint`) after every epoch; `metrics` (`report`) and `model` (`model`) at the end |
| `evaluate` | `load`, `evaluate` | `metrics` (`report`) |
| `predict` | `load`, `predict` | `predictions` (`dataset`, CSV: row, class, confidence) |

The inputs, all optional except where an operation needs them:

| Input | Meaning | Default |
|---|---|---|
| `dataset` | `{"uri": ...}` — fetched over http or https from a host the frame allows; `{"base64": ...}` — in the task; `{"synthetic": {"rows", "features", "classes"}}` — drawn from the seed. `digest` is checked on the bytes where given; `rows` and `features` inform the estimate | a synthetic dataset of 2000 rows, 8 features, 3 classes |
| `model` | for `evaluate` and `predict`: a model file as `uri` or `base64`, **with** its `digest`. A model without one is rejected: a model is used only as pinned | — |
| `label` | the label column of a CSV | its last column |
| `seed` | every random choice: the synthetic data, the held-out split, the order within an epoch | `0` |
| `epochs` | passes over the training rows | `5` |
| `holdout` | the share of rows held out for the metrics, 0.05 to 0.5 | `0.2` |

A dataset is a CSV with a header row and a number in every feature column. The model family is a
linear classifier — logistic regression fitted by stochastic gradient descent — on standardised
features.

## What it promises about the result

**Reproducible at a pinned version.** The same dataset, seed and worker version give a model file
with the same bytes, and so the same digest. A training stopped at an epoch boundary and resumed
ends in the same model as one that ran straight through: the checkpoint holds the weights and the
step counter after the epoch, and the prepared data, in the state directory.

**What is served is what was evaluated.** The metrics of a training are computed by the function
that serves predictions, over the model file as written, never by the classifier in memory.

**A model file is data.** It is JSON: the features, the classes, the scaler, the weights, the
seed, the dataset's digest, the worker's version and the versions of its libraries, and the
metrics. Loading it runs no code. A model whose bytes do not match the digest the task names is
used for nothing: in the task it is rejected before the start, behind a URI the assignment fails
at `load` and produces nothing.

**Prediction carries its confidence.** Every row's class comes with its probability, which a
step's fallback reads (`docs/architecture/methods.md` §2: "confidence < 0.9 → human").

## The contract around it

Everything the reference worker does, it does too: an estimate, a resumable event stream,
consumption in `compute` seconds of its resource class after every step, a boundary and a
checkpoint after every step, a stop that lands on the boundary, refusal of a tool or a host
outside the frame, rejection before the start when the limits do not fit, a halt at the next
boundary when the running total would cross them, the task's command after the work, `503` at
capacity, `404` for an id never received, `409` for one held. Its faults are those of the
reference worker (`--list-faults`), each proven to fail exactly its check
(`tests/conformance/test_worker_v1_mlbench.py`).

Tunables: `--resource-class` (default `cpu.small`), `--max-concurrent` (default 2),
`--estimate-factor` (default 1; below 1 it underestimates, which is how the suite observes the
halt at a limit), `--epoch-floor` (default 0: the seconds an epoch holds its place at least,
which the conformance gate sets so that a stop lands while a training runs), `--max-bytes` (what
a URI may return, default 256 MiB), `--state-dir`. An execution adapter sets `TAKTUS_UNIT_PORT`
and `TAKTUS_UNIT_STATE_DIR`, and the worker takes them as defaults.

Credentials arrive as names. The worker logs whether each is present and nothing else; it sends
none to a dataset host.

## What it does not do yet

Embeddings, neural models and a training run on an accelerator are the second part, issue
#210. A step of method `ml` runs on the bench's `predict` (ADR-0076, #216). Maturation trains a
candidate on the bench and tries it on held-out cases before it proposes a move (ADR-0084,
#217); the move itself is #218. The model hub is
UC-8.6.
