# The model costs connector — OpenAI's organisation costs

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over the organisation costs API of OpenAI: what an organisation spent at the model provider per
day, by line item or by project. Everywhere else it is the capability `models.costs`
(ADR-0150, issue #447). Over the models list of the same API it also answers which models a key
may use, the capability `models.catalogue`.

It is product support for any tenant, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.openai --port 9109
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address (default `https://api.openai.com`). `--timeout` is the longest one request may
take, in seconds (default 30). Added to an instance by one entry of `TAKTUS_CONNECTORS`
per capability, both at the same address: `models.costs=http://model-costs-connector:9109/mcp`
and `models.catalogue=http://model-costs-connector:9109/mcp`.

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

`models.catalogue.list`, effect `read`, the capability `models.catalogue`: which models the
referenced key may use.

| Input | Meaning |
|---|---|
| `limit` | the most models answered, from 1 to 1000 (default 1000) |

| Field | Meaning |
|---|---|
| `models` | sorted by `id`, each `{"id", "name", "created_at", "lifecycle", "deprecated_at", "retires_at"}` |
| `models[].name` | always `null`: the API gives no display name |
| `models[].created_at` | the model's `created` moment, Unix seconds, as RFC 3339 UTC |
| `models[].lifecycle` | always `null`: the API states no lifecycle stage, and none is inferred |
| `models[].deprecated_at` | always `null`: the API states no deprecation moment |
| `models[].retires_at` | the model's `shutdown_date`, a date, as the moment that day begins in UTC; `null` while no shutdown is announced |
| `ids` | the identifiers alone, sorted |
| `retiring` | the identifiers, sorted, of the models with a `retires_at` |
| `current` | the identifiers, sorted, of the models listed and not retiring: what a model in use may be switched to, and what B-2.04 leaves out (ADR-0204) |
| `complete` | whether every model was read: no page left and none cut by `limit` |

The list is `GET /v1/models`
([reference](https://developers.openai.com/api/reference/resources/models/methods/list)). It
answers in one page: the reference names no paging. The organisation that owns a model
(`owned_by`) is not copied.

What the catalogue does not say: whether a model is deprecated, and since when. The API
publishes only the shutdown date. A model whose shutdown has passed may already be gone from the
list; the reference does not say.

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `MODEL_COSTS_TOKEN` | actions: the **requesting identity's** administration key of the organisation, which may read its costs | the file `TAKTUS_CREDENTIAL_MODEL_COSTS_TOKEN_FILE` names, read at the moment of each call, never stored |
| `MODELS_TOKEN` | actions: an ordinary **API key** of a project, which may list the models | the file `TAKTUS_CREDENTIAL_MODELS_TOKEN_FILE` names, read at the moment of each call, never stored |

The two operations take two kinds of key. The costs take an administration key. The provider
does not admit an administration key to any other endpoint
([administration](https://developers.openai.com/api/reference/administration/overview)), so the
catalogue takes an ordinary API key. The connector uses whichever credential a call references:
a process names `MODEL_COSTS_TOKEN` for the costs and `MODELS_TOKEN` for the catalogue.

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
