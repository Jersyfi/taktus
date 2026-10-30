# The model costs connector — Anthropic's cost report

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over the cost report of Anthropic's Admin API: what an organisation spent at the model provider
per day, by description (the model and the kind of usage) or by workspace. Everywhere else it
is the capability `models.costs` (ADR-0150, issue #447). The other connector of the same
capability, [`openai`](../openai/README.md), answers in the same shape, so a process that reads
`models.costs` reads either.

It is product support for any tenant, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.anthropic --port 9112
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address (default `https://api.anthropic.com`). `--timeout` is the longest one request may
take, in seconds (default 30). Added to an instance by one entry of `TAKTUS_CONNECTORS`:
`models.costs=http://model-costs-connector:9112/mcp`.

## What it declares

`models.costs.daily`, effect `read`. Each page of the answer is one request; the report gives
at most 31 days per page.

| Input | Meaning |
|---|---|
| `days` | how many days, from 1 to 92 (default 29: the day judged and four weeks before it) |
| `end` | the day after the last one read, `YYYY-MM-DD` (default today, UTC) |
| `group_by` | `line_item` (default: the report's description) or `workspace` |

| Field | Meaning |
|---|---|
| `currency` | the currency of every amount, upper case; `null` where no day had one |
| `group_by` | as asked |
| `days` | oldest first, each `{"date", "estimated", "total", "groups"}` |
| `days[].groups` | `{"group", "amount"}`, sorted; the default workspace is `(default)`, a result without the grouping key `(none)` |
| `days[].total` | the exact sum of the day's amounts, as decimal text |
| `complete` | whether every page of the answer was read |

The report gives each amount as decimal text in cents. The connector moves the decimal point
two places, which loses no digit, and reports dollars, as the other `models.costs` connector
does. A step that holds a figure `exact` builds it from these (CLAUDE.md §4). `estimated` is
always `false`: the report does not say whether a day is closed. Amounts in more than one
currency are `unexpected`. How each answer maps to the contract's causes is the table in
[`operations.py`](operations.py).

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `MODEL_COSTS_TOKEN` | actions: the **requesting identity's** Admin API key of the organisation, sent as `x-api-key` | the file `TAKTUS_CREDENTIAL_MODEL_COSTS_TOKEN_FILE` names, read at the moment of each call, never stored |

The provider's Admin API keys carry no scopes: a key that may read the cost report may also
administer the organisation. The key is therefore one only Taktus holds, and the connector only
reads with it. `CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9112/mcp --scenario connectors/taktus_connectors/anthropic/scenario.json
```

[`scenario.json`](scenario.json) reads three days from the fake under
`tests/fakes/cost_report_service.py`, and asks for a period the provider refuses. It names no
write, and C-05 passes as not applicable. `--fault NAME` breaks exactly one check
(`connectors/serving.py`); `tests/conformance/test_connector_v1_business.py` runs every fault.
