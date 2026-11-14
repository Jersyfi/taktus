# The model catalogue connector — Mistral AI's models list

The connector contract v1 ([`contracts/connector/v1`](../../../contracts/connector/v1/README.md))
over the models list of the Mistral AI API: which models a key may use, and which of them the
provider has set a deprecation for. Everywhere else it is the capability `models.catalogue`
(ADR-0150, ADR-0204, issue #447).

It serves no `models.costs` (ADR-0330). The provider's administration API, offered on
enterprise plans only, answers monthly usage per model in entries whose fields its reference
does not describe, and a list of unit prices; it computes no cost. A cost built from it would
rest on a guess about those fields, so none is built; its spend is read in the provider's
console. No interface states the credit left. A process that watches model costs (B-2.01)
reads them from the providers that publish them.

It is product support for any tenant, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.mistral --port 9115
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address (default `https://api.mistral.ai`). `--timeout` is the longest one request may
take, in seconds (default 30). Added to an instance by one entry of `TAKTUS_CONNECTORS`:
`models.catalogue=http://model-catalogue-connector:9115/mcp`.

## What it declares

`models.catalogue.list`, effect `read`. The list is one request.

| Input | Meaning |
|---|---|
| `limit` | the most models answered, from 1 to 1000 (default 1000) |

| Field | Meaning |
|---|---|
| `models` | sorted by `id`, each `{"id", "name", "created_at", "lifecycle", "deprecated_at", "retires_at"}` |
| `models[].name` | the model's `name` as the provider gives it, or `null` |
| `models[].created_at` | the model's `created` moment, Unix seconds, as RFC 3339 UTC, or `null` |
| `models[].lifecycle` | always `null`: the API states no lifecycle stage, and none is inferred |
| `models[].deprecated_at` | the model's `deprecation`, the moment the provider set, as RFC 3339 UTC; a moment without a zone is read as UTC; `null` while none is set |
| `models[].retires_at` | always `null`: the API states no retirement apart from the deprecation |
| `ids` | the identifiers alone, sorted |
| `retiring` | the identifiers, sorted, of the models with a deprecation set, past or announced |
| `current` | the identifiers, sorted, of the models listed and not retiring: what a model in use may be switched to, and what B-2.04 leaves out (ADR-0204) |
| `complete` | whether every model was read: none cut by `limit` |

The list is `GET /v1/models`
([reference](https://docs.mistral.ai/api/#tag/models/operation/list_models_v1_models_get)). It
answers in one page. The owner, the capabilities, the aliases and the replacement model the
provider names are not copied. The deprecation is not compared with the clock: whether it has
passed is the reader's question.

| Answer | Cause |
|---|---|
| 400, 404, 422 | `invalid` |
| 401 | `unauthenticated` |
| 403 | `forbidden` |
| 429, 5xx, no answer in time | `unavailable`, retryable |
| anything else, a deprecation or creation that is not a moment | `unexpected` |

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `MODELS_TOKEN` | actions: an ordinary **API key** of the requesting identity's workspace, which may list the models | the file `TAKTUS_CREDENTIAL_MODELS_TOKEN_FILE` names, read at the moment of each call, never stored |

The contract has no connector without the requesting identity's credential (C-03): a call that
references none is refused. The key goes to the configured address and nowhere else.
`CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9115/mcp --scenario connectors/taktus_connectors/mistral/scenario.json
```

[`scenario.json`](scenario.json) reads the list from the fake under
`tests/fakes/model_list_service.py`, and asks for a limit the connector refuses. It names no
write, and C-05 passes as not applicable. `--fault NAME` breaks exactly one check
(`connectors/serving.py`); `tests/conformance/test_connector_v1_business.py` runs every fault.
