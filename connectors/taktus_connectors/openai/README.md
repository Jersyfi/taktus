# The model costs connector — OpenAI's organisation costs

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over the organisation costs API of OpenAI: what an organisation spent at the model provider per
day, by line item or by project. Everywhere else it is the capability `models.costs`
(ADR-0150, issue #447).

It is product support for any tenant, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.openai --port 9109
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address (default `https://api.openai.com`). `--timeout` is the longest one request may
take, in seconds (default 30). Added to an instance by one entry of `TAKTUS_CONNECTORS`:
`models.costs=http://model-costs-connector:9109/mcp`.

## What it declares

`models.costs.daily`, effect `read`. Each page of the answer is one request.

| Input | Meaning |
|---|---|
| `days` | how many days, from 1 to 92 (default 29: the day judged and four weeks before it) |
| `end` | the day after the last one read, `YYYY-MM-DD` (default today, UTC) |
| `group_by` | `line_item` (default) or `project` |

The output has the shape `billing.costs.daily` has, so that the same statistics read both:

| Field | Meaning |
|---|---|
| `currency` | the currency of every amount, upper case; `null` where no day had one |
| `group_by` | as asked |
| `days` | oldest first, each `{"date", "estimated", "total", "groups"}` |
| `days[].groups` | `{"group", "amount"}`, sorted; a result without the grouping key is `(none)` |
| `days[].total` | the exact sum of the day's amounts, as decimal text |
| `complete` | whether every page of the answer was read |

Every amount is the decimal text the provider gave, read without floating point: a step that
holds a figure `exact` builds it from these (CLAUDE.md §4). `estimated` is always `false`: the
API does not say whether a day is closed. Amounts in more than one currency are `unexpected`.

| Answer | Cause |
|---|---|
| 400, 404, 422 | `invalid` |
| 401 | `unauthenticated` |
| 403 | `forbidden` |
| 429, 5xx, no answer in time | `unavailable`, retryable |
| anything else | `unexpected` |

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `MODEL_COSTS_TOKEN` | actions: the **requesting identity's** administration key of the organisation, which may read its costs | the file `TAKTUS_CREDENTIAL_MODEL_COSTS_TOKEN_FILE` names, read at the moment of each call, never stored |

The contract has no connector without the requesting identity's credential (C-03): a call
that references none is refused. The key goes to the configured address and nowhere else.
`CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9109/mcp --scenario connectors/taktus_connectors/openai/scenario.json
```

[`scenario.json`](scenario.json) reads three days from the fake under
`tests/fakes/model_costs_service.py`, and asks for a period the provider refuses. It names no
write, and C-05 passes as not applicable. `--fault NAME` breaks exactly one check
(`connectors/serving.py`); `tests/conformance/test_connector_v1_business.py` runs every fault.
