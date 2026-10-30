# The cloud billing connector — AWS Cost Explorer

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over the cost query of the AWS Cost Explorer API: what an account spent per day, by service,
linked account or region. Everywhere else it is the capability `billing.costs` (ADR-0150,
issue #447).

It is product support for any tenant, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.aws --port 9108
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address (default `https://ce.us-east-1.amazonaws.com`); `--region` the region a request
is signed for (default `us-east-1`, where the API is served). `--timeout` is the longest one
request may take, in seconds (default 30). Added to an instance by one entry of
`TAKTUS_CONNECTORS`: `billing.costs=http://billing-connector:9108/mcp`.

The provider bills every request of this API. One read of 29 days is one request.

## What it declares

`billing.costs.daily`, effect `read`. Each page of the answer is one request.

| Input | Meaning |
|---|---|
| `days` | how many days, from 1 to 92 (default 29: the day judged and four weeks before it) |
| `end` | the day after the last one read, `YYYY-MM-DD` (default today, UTC) |
| `group_by` | `service` (default), `account` or `region` |
| `metric` | `unblended` (default), `amortized` or `net_unblended` |

The output has the shape `models.costs.daily` has, so that the same statistics read both:

| Field | Meaning |
|---|---|
| `currency` | the currency of every amount; `null` where no day had one |
| `group_by`, `metric` | as asked |
| `days` | oldest first, each `{"date", "estimated", "total", "groups"}` |
| `days[].groups` | `{"group", "amount"}`, sorted by group |
| `days[].total` | the exact sum of the day's amounts, as decimal text |
| `days[].estimated` | the provider has not closed the day; its amounts may still change |
| `complete` | whether every page of the answer was read |

Every amount is the decimal text the provider gave, summed without floating point: a step that
holds a figure `exact` builds it from these (CLAUDE.md §4). Amounts in more than one currency
are `unexpected`, because nothing here converts. How each answer maps to the contract's causes
is the table in [`operations.py`](operations.py).

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `BILLING_KEY` | actions: the **requesting identity's** key pair, `<access key id>:<secret access key>`, with `:<session token>` for temporary credentials; it may call `ce:GetCostAndUsage` and nothing else | the file `TAKTUS_CREDENTIAL_BILLING_KEY_FILE` names, read at the moment of each call, never stored |

The secret half signs each request ([`signing.py`](signing.py), Signature Version 4) and never
goes on the wire. The contract has no connector without the requesting identity's credential
(C-03): a call that references none is refused. `CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9108/mcp --scenario connectors/taktus_connectors/aws/scenario.json
```

[`scenario.json`](scenario.json) reads three days from the fake under
`tests/fakes/cloud_billing_service.py`, which recomputes every signature, and asks for a period
the provider refuses. It names no write, and C-05 passes as not applicable. `--fault NAME`
breaks exactly one check (`connectors/serving.py`);
`tests/conformance/test_connector_v1_business.py` runs every fault.
