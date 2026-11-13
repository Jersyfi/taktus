# The evaluation platform connector — Langfuse

The connector contract v1 ([`contracts/connector/v1`](../../../contracts/connector/v1/README.md))
over Langfuse's public HTTP API: an evaluation platform an organisation already uses keeps a
copy of Taktus's evaluations, mirrors the prompts of its process versions, and shows the cost it
computed for a trace (UC-5.8, ADR-0305). Langfuse is open-source under the MIT licence and runs
on an organisation's own servers (NTC-0278). Everywhere else it is the capabilities
`evaluations.records`, `prompts.versions` and `observability.costs`.

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.langfuse --port 9175 --target https://langfuse.example.org
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
platform's address: a self-hosted one, or its cloud by default. `--timeout` is the longest one
request may take, in seconds (default 30). Each capability is switched on by its own entry of
`TAKTUS_CONNECTORS`, for example
`evaluations.records=http://evaluation-platform:9175/mcp,observability.costs=http://evaluation-platform:9175/mcp`;
one not named is off.

The shapes follow the platform's published API reference (`/api/public/`), read on 2026-11-13:
data sets, data set items and data set run items; scores; traces with `totalCost`, `latency`
and their scores; prompts (`/v2/prompts`) with their versions and configuration; HTTP basic
authentication by a project's public and secret key.

## What it declares

| Operation | Effect | What it does |
|---|---|---|
| `observability.costs.read` | `read` | for each of `traces` (at most 20), the cost the platform computed, US dollars as decimal text, and the latency; a trace it does not hold is named absent |
| `evaluations.records.write` | `write`, `marked` | `dataset`, `run`, `items` (`id`, `input`, `expected`) and `results` (`item`, `trace`, `scores` of `name`, `value`, `comment`): the items kept under an identifier of the data set and case, the run's items and every score under an identifier derived from the key; a repeat finds the first score and writes nothing |
| `evaluations.records.read` | `read` | the run `run` of `dataset`: each item with its trace and the scores the platform holds on it |
| `prompts.versions.mirror` | `write`, `marked` | `text` as a new version of the text prompt `name`, its configuration naming `source` and the key's reference; a repeat finds the reference among the ten newest versions and makes none |

| The platform's answer | Cause |
|---|---|
| 400 | `invalid` |
| 401 | `unauthenticated` |
| 403 | `forbidden` |
| 404 on a read (an unknown data set, run or prompt) | `not_found` |
| 429, 5xx, no answer in time, no connection | `unavailable`, retryable; `unknown` effect for a write that was sent |
| anything else | `unexpected` |

The platform's own message stays out of an error's `detail`: it can quote what was sent.

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `EVALUATION_PLATFORM_KEYS` | actions: one project's key pair, `<public key>:<secret key>`, sent by HTTP basic authentication | the file `TAKTUS_CREDENTIAL_EVALUATION_PLATFORM_KEYS_FILE` names, read at the moment of each call, never stored |

The contract has no connector without the requesting identity's credential (C-03).
`CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9175/mcp --scenario connectors/taktus_connectors/langfuse/scenario.json
```

[`scenario.json`](scenario.json) reads the cost of the trace the fake under
`tests/fakes/evaluation_platform_service.py` holds, copies an evaluation and mirrors a prompt as
the writes C-05 repeats, and reads a run of a data set the fake does not hold as the call it must
refuse. `--fault NAME` breaks exactly one check (`connectors/serving.py`);
`tests/conformance/test_connector_v1_business.py` runs every fault.
