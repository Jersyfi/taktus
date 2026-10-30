# The metrics connector — the Prometheus HTTP query API

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over the HTTP query API of Prometheus, which many metrics stores answer too. This directory,
this file and the configuration that points at it are the only places that name it. Everywhere
else it is the capability `metrics.series` (ADR-0111).

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.prometheus --port 9104 --target http://metrics:9090
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
store's base address; point it at the fake under `tests/fakes/metrics_service.py` to run
without a network. Added to an instance by one entry of `TAKTUS_CONNECTORS`:
`metrics.series=http://metrics-connector:9104/mcp`.

## What it declares

| Operation | Effect | Input | Output |
|---|---|---|---|
| `metrics.series.query` | read | `query`, `time` (optional, seconds since the epoch or RFC 3339), `limit` (default 1000) | `result_type`, `series` — each with `labels` and one value — and `complete` |
| `metrics.series.range` | read | `query`, `start`, `end`, `step` in seconds, `limit` | the same, with every value of the range, oldest first |

A value is `{"at", "value", "text"}`: the moment, the number where the store gave a finite one
and `null` otherwise, and the text the store gave, which keeps `NaN` and `+Inf`. A step that
measures a signal reads `value` (ADR-0109). `complete` is false when the answer held more than
`limit` series. Both operations make one request; consumption is counted in `quota` units named
`requests`.

**OpenTelemetry.** A service that sends its metrics by OpenTelemetry sends them to a store. A
store that answers this API is read here. There is no OpenTelemetry receiver: ADR-0111 §7.

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `METRICS_TOKEN` | actions: the **requesting identity's** bearer token for the store; a store that admits anyone ignores it | the file `TAKTUS_CREDENTIAL_METRICS_TOKEN_FILE` names, read at the moment of each call, never stored |

`CREDENTIALS.md` describes it.

## Errors

| Answer | Cause |
|---|---|
| 400 or 422, `status: error`: the query cannot be parsed or executed; an input the connector cannot send | `invalid` |
| 401 | `unauthenticated` |
| 403 | `forbidden` |
| 429, 5xx, no connection, no answer in time | `unavailable`, retryable |
| any other status, a body that is not the API's | `unexpected` |

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9104/mcp --scenario connectors/taktus_connectors/prometheus/scenario.json
```

[`scenario.json`](scenario.json) is written for the fake store; it names no write, because no
operation leaves the system, and C-05 passes as not applicable. `--fault NAME` breaks exactly
one check (`connectors/serving.py`); `tests/conformance/test_connector_v1_open_standards.py`
runs every fault.
